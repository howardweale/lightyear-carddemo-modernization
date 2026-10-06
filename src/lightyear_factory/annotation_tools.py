"""Factory/operator proposal entry points. Never registered on Verify MCP."""

import json
import re
import subprocess
from datetime import datetime, timezone, date
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest
from lightyear_control_tower.requests import identifier
from lightyear_control_tower.status_export import atomic_new
from .annotations import annotation, outcome_summary
from .knowledge_trust import approve

CATEGORIES = {
    "candidate-runtime-exception",
    "posting-sequence-misuse",
    "divergent-field",
}


def propose(
    ledger,
    signer,
    body,
    *,
    execution_kind="factory",
    evaluation_class="public-calibration",
):
    if execution_kind != "factory" or evaluation_class != "public-calibration":
        raise ValueError("annotation proposals are factory public-calibration only")
    body = {**body, "provenance": "inferred", "portable": False}
    item = annotation(body)
    return ledger.append("create", {"annotation": item}, signer)


def repair_proposal(ledger, signer, body, category, *, receipt, judge_key):
    from lightyear_control_tower.decisions import verify_envelope

    if (
        category not in CATEGORIES
        or not verify_envelope(receipt, judge_key)
        or receipt.get("schema") != "annotation-outcome/1"
        or receipt.get("independently_replayed") is not True
        or receipt.get("status") != "passed"
        or category not in receipt.get("resolved_categories", [])
        or not set(body["anchors"]) <= set(receipt["anchors"])
        or body["customer_id"] != receipt["customer_id"]
    ):
        raise ValueError("repair outcome not verified")
    return propose(
        ledger,
        signer,
        dict(
            body,
            type="pitfall",
            source="judge-outcome",
            text="A verified run resolved the closed category "
            + category
            + "; review this condition before editing.",
            evidence=[dict(kind="receipt", sha256=receipt["content_sha256"])],
        ),
        evaluation_class=receipt["evaluation_class"],
    )


def tower_proposal(
    ledger, signer, body, proof, trust, kind, bindings, *, protected_values, now=None
):
    if kind not in {"normalization", "verify-normalization", "verify-attempt-review"}:
        raise ValueError("unsupported annotation source decision")
    d = approve(
        proof,
        trust,
        kind,
        bindings,
        ["continue"] if kind == "verify-attempt-review" else ["approved"],
        now=now,
    )
    text = d["reason"]
    if any(v and v in text for v in protected_values):
        raise ValueError("decision reason failed leak check")
    return propose(
        ledger,
        signer,
        dict(
            body,
            type="decision",
            source="tower-decision",
            text=text,
            evidence=[dict(kind="tower-decision", sha256=proof["decision_sha256"])],
        ),
    )


def import_reviews(ledger, signer, graph, comments, body, *, source_commit):
    """Map only comments at the bound commit and modernized file/line ranges."""
    rows = []
    for comment in comments:
        if comment.get("commit_id") != source_commit or comment.get("side") != "RIGHT":
            continue
        anchors = []
        for node in graph["nodes"]:
            for s in node.get("source", node.get("evidence", [])):
                if (
                    s.get("path") == comment.get("path")
                    and type(comment.get("line")) is int
                    and s.get("line_start", 0)
                    <= comment["line"]
                    <= s.get("line_end", -1)
                ):
                    anchors.append(node["id"])
        if anchors:
            rows.append(
                propose(
                    ledger,
                    signer,
                    dict(
                        body,
                        anchors=anchors,
                        type="review-finding",
                        source="code-review",
                        text=comment["body"],
                        evidence=[dict(kind="pr-review", sha256=digest(comment))],
                    ),
                )
            )
    return rows


def github_comments(repository, number):
    if (
        not re.fullmatch(r"[\w.-]+/[\w.-]+", repository)
        or type(number) is not int
        or number < 1
    ):
        raise ValueError("invalid GitHub review target")
    # Read only; imported text remains untrusted inferred material.
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/pulls/{number}/comments",
            "--paginate",
            "--slurp",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    return [comment for page in json.loads(result.stdout) for comment in page]


def review_request(root, scope, kind, assets, *, proposer="factory-agent"):
    root = Path(root)
    identifier(scope)
    identifier(proposer)
    bound = {k: digest(v) for k, v in assets.items()}
    evidence = {k: "evidence/graph-memory/" + h + ".json" for k, h in bound.items()}
    for k, relative in evidence.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = canonical(assets[k])
        if target.exists():
            if target.read_bytes() != raw:
                raise ValueError("immutable evidence conflict")
        else:
            with target.open("xb") as f:
                f.write(raw)
    name = "memory-" + digest([kind, bound])[:32]
    request = dict(
        schema="tower-request/1",
        id=name,
        scope=scope,
        kind=kind,
        bound=bound,
        evidence=evidence,
        proposed_by=proposer,
        authored_by=[proposer],
        summary="Review graph memory evidence. Operator review; not independent attestation.",
    )
    target = root / "work/control-tower/requests" / scope / (name + ".json")
    if not target.exists():
        atomic_new(target, request)
    return request


def governor_requests(ledger, root, scope, leak_checks):
    requests = []
    for s in ledger.replay().values():
        a = s["annotation"]
        summary = outcome_summary(s)
        if (
            s["status"] == "approved"
            and summary["eligible_for_verified"]
            and s.get("provenance") != "verified"
        ):
            requests.append(
                review_request(
                    root,
                    scope,
                    "graph-annotation-verified",
                    dict(annotation=a, outcome_summary=summary),
                )
            )
        elif s["status"] == "proposed" or (
            s["status"] == "approved"
            and (
                summary["flagged"]
                or date.fromisoformat(s.get("review_after", a["review_after"]))
                <= datetime.now(timezone.utc).date()
            )
        ):
            cert = leak_checks.get(a["id"])
            if cert:
                assets = dict(annotation=a, leak_check=cert)
                if s["status"] != "proposed":
                    assets["outcome_summary"] = summary
                requests.append(review_request(root, scope, "graph-annotation", assets))
    return requests
