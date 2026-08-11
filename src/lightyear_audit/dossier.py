from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import canonical_hash


def build_dossier(snapshot: dict[str, Any], release_id: str) -> dict[str, Any]:
    promotion = next(
        (
            item for item in snapshot["decisions"]
            if item["policy_id"] == "release.promotion" and item["subject_id"] == release_id
        ),
        None,
    )
    if promotion is None:
        raise KeyError(release_id)
    runtime_decisions = [
        item for item in snapshot["decisions"] if item["policy_id"].startswith("runtime.")
    ]
    execution_decisions = [
        item for item in snapshot["decisions"] if item["policy_id"].startswith("execution.")
    ]
    execution_passed = bool(execution_decisions) and all(
        item["status"] == "passed" for item in execution_decisions
    )
    evidence = {}
    for event in snapshot["events"]:
        for item in event["evidence"]:
            evidence[item["id"]] = item
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "dossier_type": "lightyear-release-evidence",
        "release_id": release_id,
        "status": promotion["status"],
        "rationale": promotion["rationale"],
        "gaps": promotion["gaps"],
        "promotion_decision": promotion,
        "runtime_decisions": runtime_decisions,
        "execution_decisions": execution_decisions,
        "evidence_inventory": [evidence[key] for key in sorted(evidence)],
        "audit": {
            "ledger_id": snapshot["ledger_id"],
            "ledger_content_sha256": snapshot["content_sha256"],
            "ledger_head_sha256": snapshot["checkpoint"]["ledger_head_sha256"],
            "event_count": snapshot["statistics"]["event_count"],
            "checkpoint_signature_algorithm": snapshot["checkpoint"]["signature_algorithm"],
        },
        "limitations": [
            "The committed canonical checkpoint is unsigned; live environments should configure a signing key.",
            "Simulated and local observations do not establish production mainframe equivalence.",
            (
                "Signed admission, scoped agent actions, and OCI acceptance-gate enforcement were observed."
                if execution_passed
                else "Execution policy conformance or an OCI probe alone is not signed factory-run proof."
            ),
            "This dossier is a deterministic evidence summary, not a substitute for organizational approval policy.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def render_markdown(dossier: dict[str, Any]) -> str:
    decisions = [*dossier["runtime_decisions"], *dossier["execution_decisions"]]
    rows = [
        f"| `{item['policy_id']}` | `{item['subject_id']}` | **{item['status']}** | {len(item['gaps'])} |"
        for item in decisions
    ]
    evidence_rows = [
        f"| `{item['kind']}` | `{item['id']}` | `{item['sha256'][:16]}…` |"
        for item in dossier["evidence_inventory"]
    ]
    return "\n".join([
        "# LIGHTYEAR release evidence dossier",
        "",
        f"**Release:** `{dossier['release_id']}`",
        "",
        f"**Decision:** **{dossier['status'].upper()}**",
        "",
        f"**Dossier identity:** `{dossier['content_sha256']}`",
        "",
        "## Promotion rationale",
        "",
        dossier["rationale"],
        "",
        "## Unresolved gaps",
        "",
        *(f"- `{gap}`" for gap in dossier["gaps"]),
        "" if dossier["gaps"] else "- None",
        "",
        "## Runtime and execution policy decisions",
        "",
        "| Policy | Subject | Status | Gaps |",
        "|---|---|---:|---:|",
        *rows,
        "",
        "## Evidence inventory",
        "",
        "| Kind | Identifier | SHA-256 |",
        "|---|---|---|",
        *evidence_rows,
        "",
        "## Audit checkpoint",
        "",
        f"- Ledger: `{dossier['audit']['ledger_id']}`",
        f"- Events: {dossier['audit']['event_count']}",
        f"- Ledger head: `{dossier['audit']['ledger_head_sha256']}`",
        f"- Signature algorithm: `{dossier['audit']['checkpoint_signature_algorithm']}`",
        "",
        "## Limitations",
        "",
        *(f"- {item}" for item in dossier["limitations"]),
        "",
    ])


def write_dossier(dossier: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(dossier, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(dossier), encoding="utf-8")
