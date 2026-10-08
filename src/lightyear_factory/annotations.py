"""Signed, append-only node memory. Outcome association is correlation, not cause."""

import json
import os
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from lightyear_control_tower.decisions import canonical, digest, verify_envelope, ZERO
from .knowledge_trust import approve, sealed

SCOPES = ("node", "subtree", "workload", "customer")
TYPES = {"convention", "pitfall", "review-finding", "decision", "preference"}
SOURCES = {
    "human-review",
    "code-review",
    "tower-decision",
    "judge-outcome",
    "factory-run",
    "agent-proposed",
}
PROVENANCE = {"observed", "asserted", "inferred", "verified"}


def annotation(body):
    body = json.loads(canonical(body))
    body.pop("id", None)
    required = {
        "customer_id",
        "anchors",
        "scope",
        "type",
        "text",
        "source",
        "provenance",
        "evidence",
        "visibility",
        "portable",
        "review_after",
        "created_by",
    }
    if set(body) != required:
        raise ValueError("annotation fields differ")
    if (
        not isinstance(body["text"], str)
        or not 1 <= len(body["text"]) <= 600
        or any(ord(c) < 32 and c not in "\n\t" for c in body["text"])
        or not body["customer_id"]
        or body["scope"] not in SCOPES
        or body["type"] not in TYPES
        or body["source"] not in SOURCES
        or body["provenance"] not in PROVENANCE
        or body["visibility"] not in {"implementer", "inspector_private"}
        or type(body["portable"]) is not bool
        or not body["anchors"]
        or not all(isinstance(a, str) and 0 < len(a) <= 512 for a in body["anchors"])
    ):
        raise ValueError("invalid annotation")
    if body["created_by"] != "operator" and not body["created_by"].startswith("agent:"):
        raise ValueError("invalid proposer")
    for e in body["evidence"]:
        if set(e) != {"kind", "sha256"} or e["kind"] not in {
            "receipt",
            "pr-review",
            "tower-decision",
            "run",
        }:
            raise ValueError("invalid evidence")
        if len(e["sha256"]) != 64 or any(
            c not in "0123456789abcdef" for c in e["sha256"]
        ):
            raise ValueError("invalid evidence hash")
    date.fromisoformat(body["review_after"])
    body["anchors"] = sorted(set(body["anchors"]))
    return {"id": "ann:" + digest(body), **body}


def leak_certificate(
    item,
    protected_values,
    signer,
    *,
    inventory_sha256,
    portable_terms=(),
    publish_portable=False,
):
    """Judge-side check; never emit protected values, match locations or counts."""
    from lightyear_judge.graph_projection import strings, tainted

    texts = [text for _, text in strings(item)]
    blocked = tainted(item) or any(
        v and any(v in text for text in texts)
        for v in (*protected_values, *portable_terms)
    )
    return signer.sign(
        dict(
            schema="annotation-leak/1",
            annotation=digest(item),
            customer_id=item["customer_id"],
            portable=publish_portable,
            inventory_sha256=inventory_sha256,
            eligible=not blocked,
        )
    )


def outcome_summary(state):
    runs = list(state["outcomes"].values())
    passes = sum(r["status"] == "passed" for r in runs)
    failures = sum(r["status"] == "failed" for r in runs)
    return dict(
        annotation=state["annotation"]["id"],
        runs=len(runs),
        passes=passes,
        failures=failures,
        failure_after_apply_rate=failures / len(runs) if runs else None,
        eligible_for_verified=passes >= 5 and failures == 0,
        flagged=failures >= 2 and failures / len(runs) >= 0.4,
        outcome_hashes=sorted(digest(r) for r in runs),
        attribution="correlation-not-causation",
    )


class AnnotationLedger:
    def __init__(
        self, path, ledger_key, *, tower_key, judge_key, scope, inventory_sha256
    ):
        self.path = Path(path)
        self.ledger_key, self.tower_key, self.judge_key = (
            ledger_key,
            tower_key,
            judge_key,
        )
        self.scope, self.inventory_sha256 = scope, inventory_sha256

    def events(self):
        if not self.path.exists():
            return []
        raw = self.path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise ValueError("incomplete annotation event")
        return [json.loads(line) for line in raw.splitlines()]

    def replay(self, events=None):
        states, previous = {}, ZERO
        for sequence, event in enumerate(
            self.events() if events is None else events, 1
        ):
            if (
                not verify_envelope(event, self.ledger_key)
                or event.get("schema") != "annotation-event/1"
                or event.get("sequence") != sequence
                or event.get("previous_sha256") != previous
            ):
                raise ValueError("annotation signature or chain")
            previous = event["content_sha256"]
            now = datetime.fromisoformat(event["time"])
            if now.tzinfo is None:
                raise ValueError("event timezone required")
            op, p = event["event"], event["payload"]
            if op == "create":
                a = annotation(p["annotation"])
                if (
                    a != p["annotation"]
                    or a["id"] in states
                    or a["portable"]
                    or a["provenance"] not in {"observed", "inferred"}
                ):
                    raise ValueError("proposal cannot grant trust")
                if (
                    a["created_by"].startswith("agent:")
                    and a["provenance"] != "inferred"
                ):
                    raise ValueError("agent proposal must be inferred")
                states[a["id"]] = dict(
                    annotation=a, status="proposed", outcomes={}, decisions=[]
                )
                continue
            if op == 'revocation-subscription':
                if set(p) != {'directory','projection_sha256','annotation_ids'} or not p['directory'] or len(p['projection_sha256']) != 64 or not set(p['annotation_ids']) <= set(states):
                    raise ValueError('invalid revocation subscription')
                continue
            s = states[p["id"]]
            if op == "outcome":
                r = p["receipt"]
                if (
                    s["status"] != "approved"
                    or not verify_envelope(r, self.judge_key)
                    or r.get("schema") != "annotation-outcome/1"
                    or sealed(r)
                    or r.get("evaluation_class") not in {"public-calibration", "customer-factory"}
                    or r.get("independently_replayed") is not True
                    or r.get("customer_id") != s["annotation"]["customer_id"]
                    or p["id"] not in r["context"]["annotation_ids"]
                    or digest(r["context"]) != r["context_sha256"]
                    or r["status"] not in {"passed", "failed"}
                ):
                    raise ValueError("unverified annotation outcome")
                # One result per distinct run; no repeated attempts or duplicate imports.
                if r["run_id"] in s["outcomes"]:
                    raise ValueError("duplicate outcome run")
                if set(r["anchors"]) & set(s["annotation"]["anchors"]):
                    s["outcomes"][r["run_id"]] = r
                continue
            if op not in {"approve", "reject", "retire", "supersede"}:
                raise ValueError("unknown annotation event")
            trust = dict(
                tower_key=self.tower_key.decode(),
                trusted_head=p["trusted_head"],
                scope=self.scope,
            )
            verified = p.get("verified", False)
            kind = "graph-annotation-verified" if verified else "graph-annotation"
            binding = {"annotation": digest(s["annotation"])}
            if verified:
                summary = outcome_summary(s)
                if s["status"] != "approved" or not summary["eligible_for_verified"]:
                    raise ValueError("annotation not eligible")
                binding["outcome_summary"] = digest(summary)
            else:
                cert = p["leak_check"]
                if (
                    not verify_envelope(cert, self.judge_key)
                    or cert.get("schema") != "annotation-leak/1"
                    or cert["annotation"] != binding["annotation"]
                    or cert["customer_id"] != s["annotation"]["customer_id"]
                    or cert["inventory_sha256"] != self.inventory_sha256
                    or op == "approve"
                    and cert["eligible"] is not True
                ):
                    raise ValueError("annotation leak check refused")
                binding["leak_check"] = digest(cert)
                if "outcome_summary" in p:
                    if p["outcome_summary"] != outcome_summary(s):
                        raise ValueError("review outcome summary changed")
                    binding["outcome_summary"] = digest(p["outcome_summary"])
            expected = (
                "verified"
                if verified and op == "approve"
                else {
                    "approve": "approved",
                    "reject": "rejected",
                    "retire": "retired",
                    "supersede": "retired",
                }[op]
            )
            d = approve(p["proof"], trust, kind, binding, [expected], now=now)
            if not verified and (not d.get("named_owner") or not d.get("review_after")):
                raise ValueError("owner and review date required")
            if op == "supersede" and (
                p.get("replacement") not in states or p["replacement"] == p["id"]
            ):
                raise ValueError("replacement proposal required")
            if op == "approve":
                s["status"] = "approved"
                s["provenance"] = "verified" if verified else "asserted"
                if not verified:
                    s["review_after"] = d["review_after"]
                    # Portable publication must be a separate, freshly scanned proposal.
                    s["portable"] = bool(
                        cert["portable"]
                        and "publish-portable:" + binding["annotation"] in d["reason"]
                    )
            else:
                s["status"] = "retired" if op in {"retire", "supersede"} else "rejected"
            s["decisions"].append(p["proof"]["decision_sha256"])
        return states

    def append(self, event, payload, signer, *, now=None, expected_head=None):
        if event in {"approve", "reject", "retire", "supersede"} and (
            not expected_head or payload["trusted_head"] != expected_head
        ):
            raise ValueError("host-pinned fresh Tower head required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        # Single writer across processes. Never break a lock or recover a partial line silently.
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            events = self.events()
            row = signer.sign(
                dict(
                    schema="annotation-event/1",
                    sequence=len(events) + 1,
                    previous_sha256=events[-1]["content_sha256"] if events else ZERO,
                    time=(now or datetime.now(timezone.utc)).isoformat(),
                    event=event,
                    payload=payload,
                )
            )
            self.replay([*events, row])
            registry=self.path.with_suffix('.revocation-subscriptions.json')
            from .revocations import subscriptions_for
            subscriptions=subscriptions_for(self,events)
            if event == 'revocation-subscription' and payload not in subscriptions:
                subscriptions.append(payload)
                from .revocations import replace
                replace(registry,subscriptions)
            if subscriptions:
                from .revocations import replace,binding
                for subscription in subscriptions:
                    replace(Path(subscription['directory'])/'head.json',signer.sign(dict(
                        schema='annotation-live-head/1',channel=binding(self)['channel'],
                        **__import__('lightyear_factory.revocations',fromlist=['validity']).validity(now),
                        sequence=row['sequence'],ledger_head=row['content_sha256'])))
            with self.path.open("ab") as f:
                f.write(canonical(row) + b"\n")
                f.flush()
                os.fsync(f.fileno())
            if subscriptions:
                from .revocations import publish
                publish(self,signer,subscriptions,now=now)
            return row
        finally:
            os.close(fd)
            lock.unlink()


def ancestors(roots, edges):
    found = set(roots)
    while True:
        more = {
            e["source"]
            for e in edges
            if e["relation"] == "CONTAINS" and e["target"] in found
        }
        if more <= found:
            return found
        found |= more


def descendants(roots, edges):
    """Shortest containment distance, bounded even for malformed cyclic graphs."""
    distances={r:0 for r in roots}
    todo=list(roots)
    children={}
    for edge in edges:
        if edge['relation']=='CONTAINS':children.setdefault(edge['source'],[]).append(edge['target'])
    for node in todo:
        for child in children.get(node,[]):
            if child not in distances:
                distances[child]=distances[node]+1;todo.append(child)
    return distances


def retrieve(
    states, roots, edges, customer_id, *, now=None, include_inferred=False, cap=4096
):
    today = (now or datetime.now(timezone.utc)).date()
    roots = set(roots)
    parents = ancestors(roots, edges)
    below = descendants(roots, edges)
    selected = []
    for s in states.values():
        a = s["annotation"]
        provenance = s.get("provenance", a["provenance"])
        if s["status"] != "approved" and not (
            include_inferred and s["status"] == "proposed" and provenance == "inferred"
        ):
            continue
        summary = outcome_summary(s)
        if (
            a["visibility"] != "implementer"
            or summary["flagged"]
            or date.fromisoformat(s.get("review_after", a["review_after"])) <= today
            or a["customer_id"] != customer_id
            and not s.get("portable", False)
        ):
            continue
        eligible = (set(below) if a['type']=='pitfall' else roots) if a["scope"] == "node" else parents
        if not set(a["anchors"]) & eligible:
            continue
        selected.append(
            dict(
                a,
                provenance=provenance,
                review_after=s.get("review_after", a["review_after"]),
                portable=s.get("portable", False),
                outcome_strength=summary["passes"] - summary["failures"],
            )
        )
    selected.sort(
        key=lambda a: (
            min((below.get(n, 1000000) for n in a['anchors']), default=1000000),
            SCOPES.index(a["scope"]),
            {"verified": 0, "asserted": 1, "inferred": 2, "observed": 3}[
                a["provenance"]
            ],
            -a["outcome_strength"],
            a["id"],
        )
    )
    result = dict(items=[], truncated=False)
    for a in selected:
        if len(canonical(dict(items=[*result["items"], a], truncated=True))) > cap:
            result["truncated"] = True
            break
        result["items"].append(a)
    return result


def health(states, *, now=None):
    today = (now or datetime.now(timezone.utc)).date()
    rows = []
    for s in states.values():
        a = s["annotation"]
        rows.append(
            dict(
                id=a["id"],
                anchors=a["anchors"],
                source=a["source"],
                evidence=a["evidence"],
                status=s["status"],
                provenance=s.get("provenance", a["provenance"]),
                expires_in_days=(
                    date.fromisoformat(s.get("review_after", a["review_after"])) - today
                ).days,
                **outcome_summary(s),
            )
        )
    return dict(
        items=rows,
        by_status=dict(Counter(r["status"] for r in rows)),
        by_provenance=dict(Counter(r["provenance"] for r in rows)),
    )
