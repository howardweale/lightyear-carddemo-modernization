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
    memory_event = next(
        (
            item for item in reversed(snapshot["events"])
            if item["action"] == "factory.memory_snapshot_published"
        ),
        None,
    )
    portfolio_event = next(
        (
            item for item in reversed(snapshot["events"])
            if item["action"] == "factory.portfolio_plan_published"
        ),
        None,
    )
    durable_event = next(
        (
            item for item in reversed(snapshot["events"])
            if item["action"] == "factory.durable_policy_published"
        ),
        None,
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
        "semantic_memory": (
            {
                "status": "verified",
                "snapshot_sha256": memory_event["evidence"][0]["sha256"],
                "experience_count": memory_event["details"]["statistics"]["experience_count"],
                "outcomes": memory_event["details"]["statistics"]["outcomes"],
                "policy_sha256": memory_event["details"]["policy_sha256"],
            }
            if memory_event is not None else {
                "status": "not_recorded",
                "snapshot_sha256": None,
                "experience_count": 0,
                "outcomes": {},
                "policy_sha256": None,
            }
        ),
        "portfolio_plan": (
            {
                "status": "approval_required"
                if portfolio_event["details"]["approval_required"] else "ready",
                "plan_sha256": portfolio_event["evidence"][0]["sha256"],
                "orders": portfolio_event["details"]["orders"],
                "waves": portfolio_event["details"]["waves"],
                "conflicts": portfolio_event["details"]["conflicts"],
                "approval_authority": portfolio_event["details"]["approval_authority"],
            }
            if portfolio_event is not None else {
                "status": "not_recorded",
                "plan_sha256": None,
                "orders": 0,
                "waves": 0,
                "conflicts": 0,
                "approval_authority": None,
            }
        ),
        "durable_control_plane": (
            {
                "status": "contract_published",
                "policy_sha256": durable_event["evidence"][0]["sha256"],
                "backend": durable_event["details"]["backend"],
                "approval_consumption": durable_event["details"]["approval_consumption"],
                "event_integrity": durable_event["details"]["event_integrity"],
                "production_adapter": durable_event["details"]["production_adapter"],
                "conformance_status": durable_event["details"]["conformance"]["status"],
            }
            if durable_event is not None else {
                "status": "not_recorded",
                "policy_sha256": None,
                "backend": None,
                "approval_consumption": None,
                "event_integrity": None,
                "production_adapter": None,
                "conformance_status": "not_recorded",
            }
        ),
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
        "## Verified semantic memory",
        "",
        f"- Status: `{dossier['semantic_memory']['status']}`",
        f"- Experiences: {dossier['semantic_memory']['experience_count']}",
        f"- Snapshot: `{dossier['semantic_memory']['snapshot_sha256'] or 'not recorded'}`",
        "",
        "## Modernization portfolio",
        "",
        f"- Status: `{dossier['portfolio_plan']['status']}`",
        f"- Work cells: {dossier['portfolio_plan']['orders']}",
        f"- Execution waves: {dossier['portfolio_plan']['waves']}",
        f"- Detected conflicts: {dossier['portfolio_plan']['conflicts']}",
        f"- Approval authority: `{dossier['portfolio_plan']['approval_authority'] or 'not recorded'}`",
        f"- Plan: `{dossier['portfolio_plan']['plan_sha256'] or 'not recorded'}`",
        "",
        "## Audit checkpoint",
        "",
        f"- Ledger: `{dossier['audit']['ledger_id']}`",
        f"- Events: {dossier['audit']['event_count']}",
        f"- Ledger head: `{dossier['audit']['ledger_head_sha256']}`",
        f"- Signature algorithm: `{dossier['audit']['checkpoint_signature_algorithm']}`",
        "",
        "## Durable recovery control plane",
        "",
        f"- Status: `{dossier['durable_control_plane']['status']}`",
        f"- Reference backend: `{dossier['durable_control_plane']['backend'] or 'not recorded'}`",
        f"- Approval consumption: `{dossier['durable_control_plane']['approval_consumption'] or 'not recorded'}`",
        f"- Event integrity: `{dossier['durable_control_plane']['event_integrity'] or 'not recorded'}`",
        f"- Production adapter: `{dossier['durable_control_plane']['production_adapter'] or 'not recorded'}`",
        f"- Crash-recovery conformance: `{dossier['durable_control_plane']['conformance_status']}`",
        f"- Policy: `{dossier['durable_control_plane']['policy_sha256'] or 'not recorded'}`",
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
