from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lightyear_knowledge_graph.explorer import GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph

from .agents import AgentSet
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
    """Deterministic authority around replaceable planner, builder, and verifier workers."""

    def __init__(
        self,
        source_root: Path,
        runs_root: Path,
        agents: AgentSet,
        graph_path: Path | None = None,
        prepare_workspace: Callable[[IsolatedWorkspace, WorkOrder], None] | None = None,
        execution_context: Any | None = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.runs_root = runs_root.resolve()
        self.agents = agents
        self.graph_path = graph_path.resolve() if graph_path else None
        self.prepare_workspace = prepare_workspace
        self.execution_context = execution_context

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
        started_at = datetime.now(timezone.utc).isoformat()

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

            context = self._context(order)
            context_ref = artifacts.write(
                "implementer-context", "controller", "implementer", context
            )
            references.append(context_ref)
            state = "PLANNED"
            self._authorize("planner", "factory:plan")
            plan = self.agents.plan(order, context)
            self._validate_plan(order, plan)
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
                        "The approved state already satisfied every deterministic gate.",
                    )
                public_failure = builder_failure_view(latest_verification)
                self._authorize("verifier", "factory:verify")
                diagnosis = self.agents.diagnose(order, latest_verification, 0)
                diagnosis_ref = artifacts.write(
                    "failure-diagnosis", "verifier", "verifier_private", diagnosis
                )
                references.append(diagnosis_ref)
                ledger.append(state, "failure_diagnosed", diagnosis_ref)

            while attempts < order.max_attempts:
                attempts += 1
                state = "BUILDING"
                self._authorize("builder", "factory:build")
                proposal = self.agents.build(
                    order, plan, public_failure, workspace.root, attempts
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
                self._authorize("verifier", "factory:verify")
                diagnosis = self.agents.diagnose(order, latest_verification, attempts)
                diagnosis_ref = artifacts.write(
                    "failure-diagnosis", "verifier", "verifier_private", diagnosis
                )
                references.append(diagnosis_ref)
                ledger.append(state, "failure_diagnosed", diagnosis_ref)
                public_failure = builder_failure_view(latest_verification)
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
                "All deterministic gates passed. Runtime mainframe parity remains unproven."
                if state == "PASSED"
                else "The factory stopped without satisfying all deterministic gates."
            )
            return self._finish(
                run_dir, run_id, order, state, attempts, started_at,
                ledger, references, initial_snapshot, final_snapshot, latest_verification, limitation,
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
                f"Controller stopped safely: {type(exc).__name__}",
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

    def _context(self, order: WorkOrder) -> dict[str, Any]:
        if not self.graph_path or not self.graph_path.is_file():
            return {
                "audience": "implementer",
                "graph_content_sha256": None,
                "nodes": [],
                "edges": [],
                "limitations": ["No knowledge graph was supplied to this run."],
            }
        payload = load_graph(self.graph_path)
        index = GraphExplorerIndex(payload, max_nodes=160)
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        for node_id in order.graph_node_ids:
            selection = index.neighborhood(node_id, 2, "implementer", 80)
            for node in selection.nodes:
                nodes[node["id"]] = {
                    "id": node["id"],
                    "kind": node["kind"],
                    "name": node["name"],
                    "properties": node.get("properties", {}),
                }
            for edge in selection.edges:
                edges[edge["id"]] = {
                    "id": edge["id"],
                    "source": edge["source"],
                    "relation": edge["relation"],
                    "target": edge["target"],
                }
        serialized = json.dumps({"nodes": nodes, "edges": edges})
        if "inspector_private" in serialized:
            raise ContractError("Implementer context contains verifier-private content")
        return {
            "audience": "implementer",
            "graph_content_sha256": payload["content_sha256"],
            "nodes": [nodes[item] for item in sorted(nodes)],
            "edges": [edges[item] for item in sorted(edges)],
            "limitations": [
                "Context is bounded to approved graph roots and two relationship hops."
            ],
        }

    @staticmethod
    def _validate_plan(order: WorkOrder, plan: dict[str, Any]) -> None:
        tasks = plan.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise ContractError("Planner must return at least one task")
        for task in tasks:
            for path in task.get("paths", []):
                if path not in order.allowed_paths:
                    raise ContractError(f"Planner proposed an unauthorized path: {path}")

    @staticmethod
    def _apply_edits(
        order: WorkOrder, workspace: IsolatedWorkspace, edits: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not isinstance(edits, list):
            raise ContractError("Builder edits must be an array")
        paths = {str(item.get("path", "")) for item in edits}
        if len(paths) > order.max_files_changed:
            raise ContractError("Builder exceeded max_files_changed")
        total_patch_bytes = 0
        changes = []
        for edit in edits:
            relative = str(edit.get("path", ""))
            find = edit.get("find")
            replace = edit.get("replace")
            if not isinstance(find, str) or not find or not isinstance(replace, str):
                raise ContractError("Every edit requires non-empty find text and replacement text")
            path = workspace.resolve(relative)
            if not path.is_file():
                raise ContractError(f"Builder target is not a file: {relative}")
            current = path.read_text(encoding="utf-8")
            occurrences = current.count(find)
            if occurrences != 1:
                raise ContractError(
                    f"Edit for {relative} expected one exact match; found {occurrences}"
                )
            total_patch_bytes += len(find.encode("utf-8")) + len(replace.encode("utf-8"))
            if total_patch_bytes > order.max_patch_bytes:
                raise ContractError("Builder exceeded max_patch_bytes")
            before_sha = canonical_hash({"text": current})
            updated = current.replace(find, replace, 1)
            path.write_text(updated, encoding="utf-8")
            changes.append(
                {
                    "path": relative,
                    "before_sha256": before_sha,
                    "after_sha256": canonical_hash({"text": updated}),
                    "rationale": str(edit.get("rationale", ""))[:1000],
                }
            )
        return {"changes": changes, "patch_bytes": total_patch_bytes}

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
            "limitations": [
                limitation,
                *security_limitations,
            ],
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
