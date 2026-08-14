from __future__ import annotations

import json
import gzip
from pathlib import Path
from typing import Any

from lightyear_runtime.engine import load_snapshot as load_runtime_snapshot
from lightyear_execution.evidence import normalize_execution_evidence

from .contracts import EventDraft, canonical_hash
from .ledger import build_snapshot
from .policy import AuditPolicyEngine


DEFAULT_EPOCH = "2022-07-18T00:00:00.000Z"


def build_canonical_audit(
    graph_receipt_path: Path,
    evidence_receipt_path: Path,
    runtime_paths: list[Path],
    work_order_path: Path,
    policy_path: Path,
    signing_key: bytes | None = None,
    execution_receipt_path: Path | None = None,
    memory_snapshot_path: Path | None = None,
    release_id: str = "release:carddemo-intcalc:v0.14-demo",
) -> dict[str, Any]:
    graph = json.loads(graph_receipt_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_receipt_path.read_text(encoding="utf-8"))
    work_order = json.loads(work_order_path.read_text(encoding="utf-8"))
    policy = AuditPolicyEngine.load(policy_path)
    drafts: list[EventDraft] = []
    drafts.append(_draft(
        "2022-07-18T00:00:00.000Z",
        "system:graph-builder", "system", "graph.snapshot_published",
        "knowledge_graph", graph["graph_id"],
        [{"id": graph["graph_id"], "kind": "graph_snapshot", "sha256": graph["content_sha256"]}],
        {"statistics": graph["statistics"], "receipt_type": graph["receipt_type"]},
    ))
    drafts.append(_draft(
        "2022-07-18T00:00:00.100Z",
        "system:evidence-builder", "system", "evidence.pack_published",
        "source_evidence_pack", "evidence:source-pack",
        [{"id": "evidence:source-pack", "kind": "source_evidence_pack", "sha256": evidence["content_sha256"]}],
        {"statistics": evidence["statistics"], "graph_content_sha256": evidence["graph_content_sha256"]},
    ))
    if memory_snapshot_path is not None and memory_snapshot_path.is_file():
        with gzip.open(memory_snapshot_path, "rt", encoding="utf-8") as handle:
            memory = json.load(handle)
        if canonical_hash(memory, {"content_sha256"}) != memory.get("content_sha256"):
            raise ValueError("Semantic memory snapshot failed content hash validation")
        drafts.append(_draft(
            "2022-07-18T00:00:00.150Z",
            "system:memory-controller", "system", "factory.memory_snapshot_published",
            "semantic_memory", "memory:verified-experiences",
            [{
                "id": "memory:verified-experiences",
                "kind": "semantic_memory_snapshot",
                "sha256": memory["content_sha256"],
            }],
            {
                "statistics": memory["statistics"],
                "policy_sha256": memory["policy_sha256"],
                "graph_content_sha256": memory.get("graph_content_sha256", []),
                "evidence_pack_sha256": memory.get("evidence_pack_sha256", []),
            },
        ))
    work_order_sha = canonical_hash(work_order)
    drafts.append(_draft(
        "2022-07-18T00:00:00.200Z",
        "human:demo-operator", "operator", "factory.work_order_registered",
        "work_order", work_order["id"],
        [{"id": work_order["id"], "kind": "work_order", "sha256": work_order_sha}],
        {
            "title": work_order["title"],
            "goal": work_order["goal"],
            "allow_network": work_order["policy"]["allow_network"],
            "gate_ids": [item["id"] for item in work_order["acceptance"]["gates"]],
        },
        actor_kind="human",
    ))

    execution_decisions = []
    tick = 300
    if execution_receipt_path is not None:
        source_execution = json.loads(execution_receipt_path.read_text(encoding="utf-8"))
        execution = normalize_execution_evidence(source_execution)
        drafts.append(_draft(
            "2022-07-18T00:00:00.250Z",
            "system:execution-controller", "system", "execution.evidence_recorded",
            "execution_policy", "execution:carddemo-hardened-plane",
            [{
                "id": "execution:carddemo-hardened-plane",
                "kind": execution["evidence_class"],
                "sha256": execution["source_receipt_sha256"],
            }],
            {
                "evidence_class": execution["evidence_class"],
                "source_receipt_type": execution["source_receipt_type"],
                "assurance": execution["assurance"],
                "hardened_execution_ready": execution["hardened_execution_ready"],
                "checks": execution["checks"],
                "gaps": execution["gaps"],
                "execution_policy_sha256": execution["execution_policy_sha256"],
                "bindings": execution["bindings"],
            },
        ))
        decision = policy.execution_decision(execution, _tick(tick))
        tick += 100
        execution_decisions.append(decision)
        drafts.append(_decision_draft(decision, execution["source_receipt_sha256"]))

    runtime_decisions = []
    seen_runtime_sha: set[str] = set()
    for runtime_path in runtime_paths:
        snapshot = load_runtime_snapshot(runtime_path)
        for run in snapshot["runs"]:
            if run["content_sha256"] in seen_runtime_sha:
                continue
            seen_runtime_sha.add(run["content_sha256"])
            captured_at = _tick(tick)
            tick += 100
            drafts.append(_draft(
                captured_at,
                "system:runtime-collector", "system", "runtime.capture_recorded",
                "runtime_run", f"runtime-run:{run['run_id']}",
                [{"id": f"runtime-run:{run['run_id']}", "kind": "runtime_receipt", "sha256": run["content_sha256"]}],
                {
                    "adapter_id": run["adapter_id"],
                    "source_system": run["source_system"],
                    "source_captured_at": run["captured_at"],
                    "event_count": run["event_count"],
                    "evidence_classes": sorted({event["evidence_class"] for event in run["events"]}),
                },
            ))
            for policy_name in ("development_readiness", "mainframe_equivalence"):
                evaluated_at = _tick(tick)
                tick += 100
                decision = policy.runtime_decision(run, policy_name, evaluated_at)
                runtime_decisions.append(decision)
                drafts.append(_decision_draft(decision, run["content_sha256"]))

    promotion_at = _tick(tick)
    promotion = policy.promotion_decision(
        release_id,
        runtime_decisions,
        graph["content_sha256"],
        evidence["content_sha256"],
        promotion_at,
        execution_decisions=execution_decisions,
    )
    drafts.append(_decision_draft(promotion, graph["content_sha256"]))
    checkpoint_at = _tick(tick + 100)
    return build_snapshot(drafts, graph["content_sha256"], checkpoint_at, signing_key)


def _decision_draft(decision: dict[str, Any], evidence_sha256: str) -> EventDraft:
    return _draft(
        decision["evaluated_at"],
        "system:policy-engine", "verifier", "policy.decision_recorded",
        "policy_decision", decision["id"],
        [{"id": decision["subject_id"], "kind": "decision_input", "sha256": evidence_sha256}],
        {"decision": decision},
    )


def _draft(
    occurred_at: str,
    actor_id: str,
    actor_role: str,
    action: str,
    subject_kind: str,
    subject_id: str,
    evidence: list[dict[str, Any]],
    details: dict[str, Any],
    visibility: str = "shared",
    actor_kind: str = "service",
) -> EventDraft:
    return EventDraft.from_dict({
        "occurred_at": occurred_at,
        "actor": {"id": actor_id, "role": actor_role, "kind": actor_kind},
        "action": action,
        "subject": {"kind": subject_kind, "id": subject_id},
        "evidence": evidence,
        "details": details,
        "visibility": visibility,
    })


def _tick(milliseconds: int) -> str:
    seconds, millis = divmod(milliseconds, 1000)
    return f"2022-07-18T00:00:{seconds:02d}.{millis:03d}Z"
