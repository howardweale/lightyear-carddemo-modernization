from __future__ import annotations

import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .agents import AgentSet
from .context import GraphContextAssembler
from .contracts import (
    ARTIFACT_SCHEMA_VERSION,
    RUN_RECEIPT_SCHEMA_VERSION,
    ContractError,
    WorkOrder,
    canonical_hash,
    write_json,
)
from .gates import GateRunner, builder_failure_view
from .ledger import RunLedger
from .memory import SemanticMemoryStore
from .patches import PatchBroker
from .workspace import IsolatedWorkspace


TERMINAL_STATES = {"PASSED", "BLOCKED"}


class ArtifactStore:
    def __init__(self, root: Path, run_id: str) -> None:
        self.root = root
        self.run_id = run_id
        self.sequence = 0

    def write(
        self, artifact_type: str, role: str, visibility: str, content: dict[str, Any]
    ) -> dict[str, Any]:
        self.sequence += 1
        payload = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "artifact_type": artifact_type,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "role": role,
            "visibility": visibility,
            "content": content,
        }
        payload["content_sha256"] = canonical_hash(payload)
        name = f"{self.sequence:04d}-{artifact_type}.json"
        path = self.root / name
        write_json(payload, path)
        return {
            "artifact_type": artifact_type,
            "content_sha256": payload["content_sha256"],
            "path": f"artifacts/{name}",
            "role": role,
            "visibility": visibility,
        }


class FactoryOrchestrator:
    """Deterministic authority around replaceable workers and an independent verifier."""

    def __init__(
        self,
        source_root: Path,
        runs_root: Path,
        agents: AgentSet,
        graph_path: Path | None = None,
        evidence_path: Path | None = None,
        prepare_workspace: Callable[[IsolatedWorkspace, WorkOrder], None] | None = None,
        execution_context: Any | None = None,
        memory_store: SemanticMemoryStore | None = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.runs_root = runs_root.resolve()
        self.agents = agents
        self.graph_path = graph_path.resolve() if graph_path else None
        if evidence_path:
            self.evidence_path = evidence_path.resolve()
        elif self.graph_path:
            self.evidence_path = self.graph_path.parent / "evidence" / "source.pack.json.gz"
        else:
            self.evidence_path = None
        self.prepare_workspace = prepare_workspace
        self.execution_context = execution_context
        self.memory_store = memory_store
        self.memory_retrieval: dict[str, Any] | None = None

    def run(self, order: WorkOrder, run_id: str | None = None) -> dict[str, Any]:
        run_id = _run_id(run_id)
        run_dir = self.runs_root / run_id
        if run_dir.exists():
            raise ContractError(f"Factory run already exists: {run_id}")
        run_dir.mkdir(parents=True)
        artifacts = ArtifactStore(run_dir / "artifacts", run_id)
        ledger = RunLedger(run_dir / "events.jsonl")
        workspace = IsolatedWorkspace(
            self.source_root, run_dir / "workspace", order.allowed_paths
        )
        state = "ACCEPTED"
        references: list[dict[str, Any]] = []
        attempts = 0
        latest_verification: dict[str, Any] = {"status": "not_run", "gates": []}
        initial_snapshot: dict[str, str] = {}
        final_snapshot: dict[str, str] = {}
        context: dict[str, Any] = {}
        started_at = datetime.now(timezone.utc).isoformat()
        started_monotonic = time.monotonic()

        write_json(order.to_dict(), run_dir / "work-order.json")
        ledger.append(
            state,
            "work_order_accepted",
            {
                "work_order_id": order.order_id,
                "work_order_sha256": order.content_sha256,
                "agent_set": self.agents.name,
            },
        )
        try:
            if self.execution_context:
                security_binding = self.execution_context.bind(order.content_sha256, started_at)
                ledger.append(state, "hardened_admission_bound", security_binding)
            workspace.create()
            if self.prepare_workspace:
                self.prepare_workspace(workspace, order)
            initial_snapshot = workspace.snapshot()
            ledger.append(
                state,
                "workspace_isolated",
                {
                    "allowed_paths": list(order.allowed_paths),
                    "initial_snapshot_sha256": canonical_hash(initial_snapshot),
                    "mode": "copy-on-run-plus-oci-gates" if self.execution_context else "copy-on-run",
                },
            )

            context = self._context(order, workspace.root)
            context_ref = artifacts.write(
                "implementer-context", "controller", "implementer", context
            )
            references.append(context_ref)
            state = "PLANNED"
            self._authorize("planner", "factory:plan")
            plan = self.agents.plan(order, context)
            self._record_agent_evidence(
                artifacts, ledger, references, "planner", "implementer"
            )
            self._validate_plan(order, plan, context)
            plan_ref = artifacts.write("plan", "planner", "implementer", plan)
            references.append(plan_ref)
            ledger.append(state, "plan_created", plan_ref)

            public_failure: dict[str, Any] = {"status": "not_run", "gates": []}
            if order.baseline_first:
                state = "VERIFYING"
                self._authorize("verifier", "factory:verify")
                latest_verification = self._run_gates(workspace, order)
                verification_ref = artifacts.write(
                    "verification-report",
                    "controller",
                    "verifier_private",
                    latest_verification,
                )
                references.append(verification_ref)
                ledger.append(
                    state,
                    "baseline_verified",
                    {
                        **verification_ref,
                        "status": latest_verification["status"],
                    },
                )
                if latest_verification["status"] == "passed":
                    state = "PASSED"
                    ledger.append(state, "acceptance_gates_passed", {"attempt": 0})
                    return self._finish(
                        run_dir, run_id, order, state, attempts, started_at,
                        ledger, references, initial_snapshot, workspace.snapshot(), latest_verification,
                        "The approved state already satisfied every deterministic gate.", context,
                    )
                public_failure = builder_failure_view(latest_verification)
                self._authorize("failure_analyst", "factory:analyze-failure")
                diagnosis = self.agents.analyze_failure(order, public_failure, 0)
                self._record_agent_evidence(
                    artifacts, ledger, references, "failure_analyst", "verifier_private"
                )
                diagnosis_ref = artifacts.write(
                    "failure-diagnosis", "failure_analyst", "verifier_private", diagnosis
                )
                references.append(diagnosis_ref)
                ledger.append(state, "failure_diagnosed", diagnosis_ref)
                public_failure = self._failure_envelope(public_failure, diagnosis)

            while attempts < order.max_attempts:
                if time.monotonic() - started_monotonic > order.max_elapsed_seconds:
                    raise ContractError("Factory exceeded max_elapsed_seconds")
                attempts += 1
                state = "BUILDING"
                self._authorize("builder", "factory:build")
                proposal = self.agents.build(
                    order, plan, public_failure, workspace.root, attempts
                )
                self._record_agent_evidence(
                    artifacts, ledger, references, "builder", "implementer"
                )
                proposal_ref = artifacts.write(
                    "build-proposal", "builder", "implementer", proposal
                )
                references.append(proposal_ref)
                ledger.append(state, "build_proposed", proposal_ref)
                edits = proposal.get("edits", [])
                if not edits:
                    state = "BLOCKED"
                    ledger.append(
                        state,
                        "builder_blocked",
                        {"attempt": attempts, "reason": proposal.get("blocked_reason")},
                    )
                    break
                change_set = self._apply_edits(order, workspace, edits)
                change_ref = artifacts.write(
                    "change-set", "controller", "implementer", change_set
                )
                references.append(change_ref)
                ledger.append(state, "changes_applied", change_ref)

                state = "VERIFYING"
                self._authorize("verifier", "factory:verify")
                latest_verification = self._run_gates(workspace, order)
                verification_ref = artifacts.write(
                    "verification-report",
                    "controller",
                    "verifier_private",
                    latest_verification,
                )
                references.append(verification_ref)
                ledger.append(
                    state,
                    "attempt_verified",
                    {
                        **verification_ref,
                        "attempt": attempts,
                        "status": latest_verification["status"],
                    },
                )
                if latest_verification["status"] == "passed":
                    state = "PASSED"
                    ledger.append(state, "acceptance_gates_passed", {"attempt": attempts})
                    break
                self._authorize("failure_analyst", "factory:analyze-failure")
                public_failure = builder_failure_view(latest_verification)
                diagnosis = self.agents.analyze_failure(order, public_failure, attempts)
                self._record_agent_evidence(
                    artifacts, ledger, references, "failure_analyst", "verifier_private"
                )
                diagnosis_ref = artifacts.write(
                    "failure-diagnosis", "failure_analyst", "verifier_private", diagnosis
                )
                references.append(diagnosis_ref)
                ledger.append(state, "failure_diagnosed", diagnosis_ref)
                public_failure = self._failure_envelope(public_failure, diagnosis)
            else:
                state = "BLOCKED"
                ledger.append(
                    state,
                    "attempt_budget_exhausted",
                    {"max_attempts": order.max_attempts},
                )

            if state not in TERMINAL_STATES:
                state = "BLOCKED"
            final_snapshot = workspace.snapshot()
            limitation = (
                str(
                    order.metadata.get(
                        "success_limitation",
                        "All deterministic gates passed. Runtime mainframe parity remains unproven.",
                    )
                )[:1_000]
                if state == "PASSED"
                else "The factory stopped without satisfying all deterministic gates."
            )
            return self._finish(
                run_dir, run_id, order, state, attempts, started_at,
                ledger, references, initial_snapshot, final_snapshot, latest_verification, limitation,
                context,
            )
        except Exception as exc:
            state = "BLOCKED"
            ledger.append(
                state,
                "controller_error",
                {"error_type": type(exc).__name__, "message": str(exc)[:1000]},
            )
            final_snapshot = workspace.snapshot() if workspace.root.is_dir() else {}
            self._finish(
                run_dir, run_id, order, state, attempts, started_at,
                ledger, references, initial_snapshot, final_snapshot, latest_verification,
                f"Controller stopped safely: {type(exc).__name__}", context,
            )
            raise

    def _authorize(self, role: str, action: str) -> None:
        if self.execution_context:
            self.execution_context.authorize(
                role, action, datetime.now(timezone.utc).isoformat()
            )

    def _run_gates(self, workspace: IsolatedWorkspace, order: WorkOrder) -> dict[str, Any]:
        report = GateRunner(
            workspace.root,
            allow_network=order.allow_network,
            backend=self.execution_context.backend if self.execution_context else None,
        ).run(order.gates)
        if self.execution_context:
            self.execution_context.record_verification(report)
        return report

    def _context(self, order: WorkOrder, workspace_root: Path) -> dict[str, Any]:
        context = GraphContextAssembler(
            self.graph_path,
            self.evidence_path,
            max_nodes=160,
        ).assemble(order, workspace_root)
        if self.memory_store:
            self.memory_retrieval = self.memory_store.retrieve(
                order,
                context.get("graph_content_sha256"),
                context.get("evidence_pack_sha256"),
            )
            context = GraphContextAssembler.attach_semantic_memory(
                context, self.memory_retrieval, order
            )
        return context

    @staticmethod
    def _validate_plan(
        order: WorkOrder, plan: dict[str, Any], context: dict[str, Any]
    ) -> None:
        tasks = plan.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise ContractError("Planner must return at least one task")
        known_nodes = {item["id"] for item in context.get("nodes", [])}
        known_capsules = {
            item["capsule_id"] for item in context.get("source_excerpts", [])
        }
        for task in tasks:
            for path in task.get("paths", []):
                if path not in order.allowed_paths:
                    raise ContractError(f"Planner proposed an unauthorized path: {path}")
            for node_id in task.get("graph_node_ids", []):
                if node_id not in known_nodes:
                    raise ContractError(f"Planner selected an unknown graph node: {node_id}")
            for capsule_id in task.get("evidence_capsule_ids", []):
                if capsule_id not in known_capsules:
                    raise ContractError(
                        f"Planner selected an unknown evidence capsule: {capsule_id}"
                    )

    @staticmethod
    def _apply_edits(
        order: WorkOrder, workspace: IsolatedWorkspace, edits: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return PatchBroker().apply(order, workspace, edits)

    def _record_agent_evidence(
        self,
        artifacts: ArtifactStore,
        ledger: RunLedger,
        references: list[dict[str, Any]],
        role: str,
        visibility: str,
    ) -> None:
        drain = getattr(self.agents, "drain_evidence", None)
        if not callable(drain):
            return
        for evidence in drain():
            reference = artifacts.write(
                "model-call-evidence", role, visibility, evidence
            )
            references.append(reference)
            ledger.append(
                {"planner": "PLANNED", "builder": "BUILDING"}.get(role, "VERIFYING"),
                "model_call_recorded",
                reference,
            )

    @staticmethod
    def _failure_envelope(
        public_verification: dict[str, Any], diagnosis: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            **public_verification,
            "diagnosis": {
                "summary": str(diagnosis.get("summary", ""))[:500],
                "failure_codes": [
                    str(item)[:120] for item in diagnosis.get("failure_codes", [])[:20]
                ],
                "builder_guidance": str(diagnosis.get("builder_guidance", ""))[:1_000],
                "risk": str(diagnosis.get("risk", "medium")),
            },
        }

    def _finish(
        self,
        run_dir: Path,
        run_id: str,
        order: WorkOrder,
        state: str,
        attempts: int,
        started_at: str,
        ledger: RunLedger,
        artifacts: list[dict[str, Any]],
        initial_snapshot: dict[str, str],
        final_snapshot: dict[str, str],
        verification: dict[str, Any],
        limitation: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        changed_paths = sorted(
            path
            for path in set(initial_snapshot) | set(final_snapshot)
            if initial_snapshot.get(path) != final_snapshot.get(path)
        )
        required_actions = {
            ("planner", "factory:plan"),
            ("verifier", "factory:verify"),
        }
        if attempts:
            required_actions.add(("builder", "factory:build"))
        if any(item.get("artifact_type") == "failure-diagnosis" for item in artifacts):
            required_actions.add(("failure_analyst", "factory:analyze-failure"))
        execution_security = (
            self.execution_context.summary(required_actions)
            if self.execution_context
            else {
                "status": "advisory",
                "production_ready": False,
                "backend": "host-process",
                "secrets_persisted": False,
                "gaps": ["hardened-execution-not-configured"],
            }
        )
        summary_method = getattr(self.agents, "intelligence_summary", None)
        intelligence = (
            summary_method()
            if callable(summary_method)
            else {
                "mode": "unreported",
                "provider": self.agents.name,
                "calls": 0,
                "limitations": ["Agent set did not emit intelligence provenance."],
            }
        )
        security_limitations = (
            ["Acceptance gates ran inside the admitted OCI security policy."]
            if execution_security.get("production_ready")
            else [
                "Local copy isolation is not an OS container security boundary.",
                "Network-deny is advisory until a live container backend enforces it.",
            ]
        )
        receipt = {
            "schema_version": RUN_RECEIPT_SCHEMA_VERSION,
            "receipt_type": "lightyear-autonomous-factory-run",
            "run_id": run_id,
            "work_order_id": order.order_id,
            "work_order_sha256": order.content_sha256,
            "status": state.lower(),
            "attempts": attempts,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "ledger_head_sha256": ledger.head_sha256,
            "event_count": len(ledger.events),
            "changed_paths": changed_paths,
            "initial_snapshot_sha256": canonical_hash(initial_snapshot),
            "final_snapshot_sha256": canonical_hash(final_snapshot),
            "verification": {
                "status": verification.get("status"),
                "gates": [
                    {
                        "id": item["id"],
                        "status": item["status"],
                        "output_sha256": item["output_sha256"],
                    }
                    for item in verification.get("gates", [])
                ],
            },
            "artifacts": artifacts,
            "execution_security": execution_security,
            "intelligence": intelligence,
            "limitations": [
                limitation,
                *security_limitations,
            ],
        }
        if self.memory_store:
            try:
                memory_decision = self.memory_store.observe_run(
                    run_dir, order, receipt, context, artifacts
                )
            except (ContractError, OSError, ValueError) as exc:
                memory_decision = {
                    "schema_version": "1.0",
                    "memory_type": "lightyear-semantic-memory-decision",
                    "run_id": run_id,
                    "disposition": "quarantined",
                    "reason": f"memory-controller-error:{type(exc).__name__}",
                    "experience_sha256": None,
                }
                memory_decision["content_sha256"] = canonical_hash(memory_decision)
            receipt["semantic_memory"] = {
                "retrieval_sha256": (
                    self.memory_retrieval.get("content_sha256")
                    if self.memory_retrieval else None
                ),
                "retrieved_experiences": (
                    len(self.memory_retrieval.get("cards", []))
                    if self.memory_retrieval else 0
                ),
                "decision": memory_decision,
            }
        receipt["content_sha256"] = canonical_hash(receipt)
        write_json(receipt, run_dir / "receipt.json")
        write_json(
            {
                "run_id": run_id,
                "status": receipt["status"],
                "attempts": attempts,
                "title": order.title,
                "receipt_sha256": receipt["content_sha256"],
                "intelligence_mode": intelligence.get("mode"),
                "model_calls": intelligence.get("calls", 0),
                "updated_at": receipt["completed_at"],
            },
            run_dir / "summary.json",
        )
        return receipt


def _run_id(value: str | None) -> str:
    if value:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{2,80}", value):
            raise ContractError("run_id contains unsupported characters")
        return value
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{stamp}-{secrets.token_hex(4)}"
