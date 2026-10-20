from __future__ import annotations

import re
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .agents import AgentSet, ModelAgentSet
from .authorship import CandidateHistory, CICommitSigner
from .budgeted_providers import AccountedModelProvider
from .model_transport_records import ModelTransportRecorder
from .additional_providers import AnthropicMessagesProvider, GeminiProvider
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


    def write_encrypted(
        self, artifact_type: str, role: str, content: bytes,
        *, key: bytes, key_id: str,
    ) -> dict[str, Any]:
        """Retain exact controller-owned bytes in this run's artifact directory.

        The caller supplies an external key; this store never persists it.
        This primitive does not capture calls, authorize spend, or prove isolation.
        A public ledger reference may be appended only after this method returns.
        """
        import base64
        import hashlib
        import json
        import os
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        tags = (self.run_id, artifact_type, role, key_id)
        if any(not isinstance(tag, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', tag)
               for tag in tags):
            raise ContractError('encrypted-artifact-identifier')
        if not isinstance(content, bytes):
            raise ContractError('encrypted-artifact-bytes-required')
        if not isinstance(key, bytes) or len(key) != 32:
            raise ContractError('encrypted-artifact-key-required')
        self.sequence += 1
        context = {
            'schema': 'factory-encrypted-artifact/1', 'algorithm': 'AES-256-GCM',
            'run_id': self.run_id, 'sequence': self.sequence,
            'artifact_type': artifact_type, 'role': role, 'key_id': key_id,
            'plaintext_sha256': hashlib.sha256(content).hexdigest(),
            'plaintext_bytes': len(content),
        }
        aad = json.dumps(context, sort_keys=True, separators=(',', ':')).encode('utf-8')
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, content, aad)
        envelope = {
            'context': context, 'nonce_base64': base64.b64encode(nonce).decode('ascii'),
            'ciphertext_base64': base64.b64encode(ciphertext).decode('ascii'),
        }
        encoded = (json.dumps(envelope, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
        name = f'{self.sequence:04d}-{artifact_type}.encrypted.json'
        self.root.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents overwrite, including a pre-existing leaf link.
        # Directory ownership/ACLs remain the controller's responsibility.
        fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        return {
            **context, 'path': f'artifacts/{name}', 'visibility': 'controller-encrypted',
            'ciphertext_sha256': hashlib.sha256(ciphertext).hexdigest(),
            'artifact_sha256': hashlib.sha256(encoded).hexdigest(),
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
        approved_projection=None,
        workspace_read_manifest: dict[str, str] | None = None,
        feedback_vocabulary: dict[str, list[str]] | None = None,
        model_admission=None,
        factory_input_paths=None,
        private_expected_values_path: Path | None = None,
        candidate_signing_paths: tuple[Path, Path] | None = None,
        transport_encryption: tuple[bytes, str] | None = None,
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
        self.approved_projection = approved_projection
        self.workspace_read_manifest = workspace_read_manifest
        self.feedback_vocabulary = feedback_vocabulary
        self.model_admission = model_admission
        self.factory_input_paths = factory_input_paths
        self.private_expected_values_path = private_expected_values_path
        self.candidate_signing_paths = candidate_signing_paths
        self.transport_encryption = transport_encryption
        self.memory_retrieval: dict[str, Any] | None = None

    def run(self, order: WorkOrder, run_id: str | None = None) -> dict[str, Any]:
        self._validate_attempt_budget(order)
        run_id = _run_id(run_id)
        run_dir = self.runs_root / run_id
        if run_dir.exists():
            raise ContractError(f"Factory run already exists: {run_id}")
        run_dir.mkdir(parents=True)
        artifacts = ArtifactStore(run_dir / "artifacts", run_id)
        ledger = RunLedger(run_dir / "events.jsonl")
        workspace = IsolatedWorkspace(
            self.source_root, run_dir / "workspace", order.allowed_paths,
            read_manifest=self.workspace_read_manifest
        )
        state = "ACCEPTED"
        references: list[dict[str, Any]] = []
        attempts = 0
        history = recorder = None
        candidate_end = None
        latest_verification: dict[str, Any] = {"status": "not_run", "gates": []}
        initial_snapshot: dict[str, str] = {}
        final_snapshot: dict[str, str] = {}
        context: dict[str, Any] = {}
        started_at = datetime.now(timezone.utc).isoformat()
        started_monotonic = time.monotonic()

        try:
            if isinstance(self.agents, ModelAgentSet) and self.candidate_signing_paths is None:
                from .providers import ScriptedModelProvider
                from .routing import TaskRouter
                if type(self.agents.provider) is not ScriptedModelProvider:
                    self._verify_runtime_admission(order)
                if self.agents.bounded_provider is not None:
                    raise ContractError('factory-model-agent-reuse')
                runtime_admission=lambda:self._verify_runtime_admission(order)
                if type(self.agents.provider) is TaskRouter:
                    self.agents.bounded_provider=self.agents.provider.bind_order(order,
                        model_admission=self.model_admission,runtime_admission=runtime_admission)
                else:
                    self.agents.bounded_provider=AccountedModelProvider(self.agents.provider,order,
                        model_admission=self.model_admission,runtime_admission=runtime_admission)
                self.agents.order_sha256=order.content_sha256
            if self.execution_context:
                security_binding = self.execution_context.bind(order.content_sha256, started_at)
                ledger.append(state, "hardened_admission_bound", security_binding)
            workspace.create()
            if self.prepare_workspace:
                self.prepare_workspace(workspace, order)
            if self.workspace_read_manifest is not None:
                manifest=workspace.verify_read_boundary()
                ledger.append(state,'workspace_read_manifest',dict(files=manifest,sha256=canonical_hash(manifest)))
                if isinstance(self.agents, ModelAgentSet):
                    self._bind_isolation_scan(workspace, ledger, order)
                self._scan_workspace(workspace, 'initial-workspace')
            self._scan_controller_value('approved-work-order', order.to_dict())
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
            if self.candidate_signing_paths is not None:
                history, recorder = self._bind_candidate_run(order, workspace, run_dir, artifacts, ledger)
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
                    if history is not None:
                        raise ContractError("signed-candidate-build-required")
                    state = "PASSED"
                    ledger.append(state, "acceptance_gates_passed", {"attempt": 0})
                    return self._finish(
                        run_dir, run_id, order, state, attempts, started_at,
                        ledger, references, initial_snapshot, workspace.snapshot(), latest_verification,
                        "The approved state already satisfied every deterministic gate.", context,
                    )
                public_failure = builder_failure_view(latest_verification,self.feedback_vocabulary)
                if self.feedback_vocabulary is not None:ledger.append(state,'verifier_gateway_feedback',public_failure)
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
                public_failure = self._failure_envelope(public_failure, diagnosis, include_diagnosis=self.feedback_vocabulary is None)

            while attempts < order.max_attempts:
                if time.monotonic() - started_monotonic > order.max_elapsed_seconds:
                    raise ContractError("Factory exceeded max_elapsed_seconds")
                attempts += 1
                state = "BUILDING"
                self._authorize("builder", "factory:build")
                if history is not None:
                    parent = history.verify_before_build()
                    if recorder.pending is not None or recorder.failed:
                        raise ContractError('transport-recorder-unavailable')
                    recorder.attempt = attempts
                    response_start = len(ledger.events)
                self._scan_workspace(workspace, 'builder-workspace')
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
                if history is not None:
                    response_ids = self._candidate_response_ids(ledger, response_start, run_id, attempts)
                    if history.verify_before_build() != parent:
                        raise ContractError('candidate-history-parent-changed')
                self._scan_controller_value('patch-tool-input', edits)
                change_set = self._apply_edits(order, workspace, edits)
                self._scan_controller_value('patch-tool-result', change_set)
                self._scan_workspace(workspace, 'patched-workspace')
                if history is not None:
                    candidate_end = history.commit_applied_changes(attempts, parent=parent,
                                                                  change_set=change_set, response_events=response_ids)
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
                public_failure = builder_failure_view(latest_verification,self.feedback_vocabulary)
                if self.feedback_vocabulary is not None:ledger.append(state,'verifier_gateway_feedback',public_failure)
                diagnosis = self.agents.analyze_failure(order, public_failure, attempts)
                self._record_agent_evidence(
                    artifacts, ledger, references, "failure_analyst", "verifier_private"
                )
                diagnosis_ref = artifacts.write(
                    "failure-diagnosis", "failure_analyst", "verifier_private", diagnosis
                )
                references.append(diagnosis_ref)
                ledger.append(state, "failure_diagnosed", diagnosis_ref)
                public_failure = self._failure_envelope(public_failure, diagnosis, include_diagnosis=self.feedback_vocabulary is None)
            else:
                state = "BLOCKED"
                ledger.append(
                    state,
                    "attempt_budget_exhausted",
                    {"max_attempts": order.max_attempts},
                )

            self._scan_workspace(workspace, 'final-candidate-package')
            candidate_authorship = None
            package_check = None
            if history is not None and candidate_end is not None:
                candidate_authorship = history.audit(candidate_end, artifacts)
                if not candidate_authorship['qualifies_for_factory_receipt']:
                    state = 'BLOCKED'
                references.append(artifacts.write('candidate-authorship', 'controller',
                                                   'verifier_private', candidate_authorship))
                if candidate_authorship['qualifies_for_factory_receipt']:
                    package = history.export_verified_package(candidate_end,
                        run_dir/'candidate-package', candidate_authorship, self._isolation_scanner())
                    self._scan_controller_value('candidate-package-manifest', package)
                    references.append(artifacts.write('candidate-package-manifest', 'controller',
                                                       'verifier_private', package))
                    package_check = lambda: history.revalidate_exported_package(
                        candidate_end, run_dir/'candidate-package', package,
                        self._isolation_scanner(), artifacts)
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
                context, candidate_authorship=candidate_authorship, candidate_package_check=package_check,
            )
        except Exception as exc:
            state = "BLOCKED"
            if self.workspace_read_manifest is not None:
                self._record_isolation_failure(run_dir, order, attempts, ledger)
                raise ContractError('factory-isolation-run-refused') from None
            self._record_agent_evidence(artifacts, ledger, references, "controller", "verifier_private")
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

    def _validate_attempt_budget(self, order):
        if self.workspace_read_manifest is not None:
            if type(order.max_attempts) is not int or not 1 <= order.max_attempts <= 3:
                raise ContractError('factory-attempt-budget-refused')

    @staticmethod
    def _record_isolation_failure(run_dir, order, attempts, ledger):
        # No raw exception, drained model evidence, private names, context or paths.
        ledger.append('BLOCKED', 'controller_error', {'reason': 'factory-isolation-run-refused'})
        receipt = {'schema_version': RUN_RECEIPT_SCHEMA_VERSION,
                   'receipt_type': 'lightyear-autonomous-factory-run',
                   'status': 'blocked', 'attempts': attempts,
                   'repair_loops': max(0, attempts-1),
                   'work_order_sha256': order.content_sha256,
                   'ledger_head_sha256': ledger.head_sha256,
                   'qualifies_for_factory_receipt': False,
                   'reason': 'factory-isolation-run-refused'}
        receipt['content_sha256'] = canonical_hash(receipt)
        write_json(receipt, run_dir/'receipt.json')
        write_json({'status': 'blocked', 'attempts': attempts,
                    'receipt_sha256': receipt['content_sha256'],
                    'reason': 'factory-isolation-run-refused'}, run_dir/'summary.json')

    def _verify_runtime_admission(self, order):
        from .model_admission import FactoryModelAdmission
        if type(self.model_admission) is not FactoryModelAdmission or self.execution_context is None:
            raise ContractError('factory-model-runtime-required')
        if self.workspace_read_manifest is None:
            raise ContractError('factory-model-runtime-workspace')
        return self.model_admission.verify_runtime(order,source_root=self.source_root,
            input_paths=self.factory_input_paths,policy=self.execution_context.policy,
            read_manifest=self.workspace_read_manifest)

    def _bind_isolation_scan(self, workspace, ledger, order=None):
        from .isolation_scan import scan
        if self.agents.isolation_scan is not None:
            raise ContractError('isolation-scan-agent-reuse')
        canaries = dict(workspace.canaries)
        def expected_values():
            if self.model_admission is None:
                if self.candidate_signing_paths is not None:
                    raise ContractError('factory-private-expected-values-required')
                return ()  # Offline compatibility does not qualify for a factory receipt.
            if order is None or self.private_expected_values_path is None:
                raise ContractError('factory-private-expected-values-required')
            return self.model_admission.private_expected_values(order, self.private_expected_values_path,
                excluded_roots=(self.runs_root, workspace.root))
        expected_values()  # Refuse missing/unapproved inputs before constructing agent context.
        def inspect(name, raw):
            result = scan([(name, raw)], canaries, expected_values())
            ledger.append('RUNNING', 'model_isolation_scan_passed', result)
        self.agents.isolation_scan = inspect

    def _bind_candidate_run(self, order, workspace, run_dir, artifacts, ledger):
        if (self.workspace_read_manifest is None or type(self.agents) is not ModelAgentSet
                or type(self.agents.provider) not in (AnthropicMessagesProvider, GeminiProvider)
                or self.agents.bounded_provider is not None or self.agents.pending_evidence
                or self.transport_encryption is None or not callable(self.agents.isolation_scan)
                or type(order.max_attempts) is not int
                or not 1 <= order.max_attempts <= 3):
            raise ContractError('candidate-controller-binding-required')
        self._verify_runtime_admission(order)
        key, key_id = self.transport_encryption
        if not isinstance(key, bytes) or len(key) != 32 or not isinstance(key_id, str) or not key_id:
            raise ContractError('candidate-controller-encryption-required')
        signer = CICommitSigner(*self.candidate_signing_paths, workspace.root)
        recorder = ModelTransportRecorder(artifacts, ledger, key=key, key_id=key_id, attempt=1,
                                          isolation_scan=self.agents.isolation_scan,
                                          work_order_sha256=order.content_sha256,
                                          require_model_admission=True)
        self.agents.provider.bind_transport_recorder(recorder)
        self.agents.bounded_provider = AccountedModelProvider(self.agents.provider, order, model_admission=self.model_admission,
            runtime_admission=lambda:self._verify_runtime_admission(order))
        self.agents.order_sha256 = order.content_sha256
        history = CandidateHistory(workspace, run_dir/'candidate-history.git', artifacts.run_id, ledger, signer=signer)
        history.initialize()
        ledger.append('ACCEPTED', 'candidate_controller_bound', dict(run_id=artifacts.run_id,
                      order_sha256=order.content_sha256, encryption_key_id=key_id,
                      candidate_start=history.start_commit))
        return history, recorder

    def _candidate_response_ids(self, ledger, start, run_id, attempt):
        events = [event for event in ledger.events[start:] if event['kind']=='model-transport-finished'
                  and event['payload'].get('role')=='builder']
        last = self.agents.provider.last_transport_record or {}
        if (len(events)!=1 or last.get('end_event_sha256')!=events[0]['event_sha256']
                or events[0]['payload'].get('run_id')!=run_id
                or events[0]['payload'].get('attempt')!=attempt
                or events[0]['payload'].get('status')!='response'
                or events[0]['payload'].get('response_complete') is not True):
            raise ContractError('candidate-controller-builder-response-required')
        return [events[0]['event_sha256']]

    def _authorize(self, role: str, action: str) -> None:
        if self.execution_context:
            self.execution_context.authorize(
                role, action, datetime.now(timezone.utc).isoformat()
            )

    def _isolation_scanner(self):
        if self.workspace_read_manifest is None:
            return None
        scanner = getattr(self.agents, 'isolation_scan', None)
        if not callable(scanner):
            raise ContractError('controller-isolation-scanner-required')
        return scanner

    def _scan_controller_value(self, surface, value):
        scanner = self._isolation_scanner()
        if scanner is not None:
            try:
                scanner(surface, json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8'))
            except Exception:
                raise ContractError('controller-isolation-refused') from None

    def _scan_workspace(self, workspace, surface):
        scanner = self._isolation_scanner()
        if scanner is not None:
            return workspace.scan_contents(scanner, surface)
        return None

    def _run_gates(self, workspace: IsolatedWorkspace, order: WorkOrder) -> dict[str, Any]:
        self._scan_workspace(workspace, 'pre-gate-workspace')
        if self.workspace_read_manifest is not None:workspace.verify_read_boundary()
        report = GateRunner(
            workspace.root,
            allow_network=order.allow_network,
            backend=self.execution_context.backend if self.execution_context else None,
            require_container=self.workspace_read_manifest is not None,
            isolation_scan=self._isolation_scanner(),
        ).run(order.gates)
        self._scan_workspace(workspace, 'post-gate-workspace')
        if self.workspace_read_manifest is not None:workspace.verify_read_boundary()
        if self.execution_context:
            self.execution_context.record_verification(report)
        return report

    def _context(self, order: WorkOrder, workspace_root: Path) -> dict[str, Any]:
        context = GraphContextAssembler(
            self.graph_path,
            self.evidence_path,
            max_nodes=160,
            approved_projection=self.approved_projection,
        ).assemble(order, workspace_root)
        if self.memory_store and context.get("schema_version") != "1.1":
            self.memory_retrieval = self.memory_store.retrieve(
                order,
                context.get("graph_content_sha256"),
                context.get("evidence_pack_sha256"),
            )
            context = GraphContextAssembler.attach_semantic_memory(
                context, self.memory_retrieval, order
            )
        self._scan_controller_value('controller-context', context)
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
            self._scan_controller_value('model-call-evidence', evidence)
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
        public_verification: dict[str, Any], diagnosis: dict[str, Any], include_diagnosis: bool = True
    ) -> dict[str, Any]:
        if not include_diagnosis:return public_verification
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
        candidate_authorship: dict[str, Any] | None = None,
        candidate_package_check: Callable[[], dict[str, Any]] | None = None,
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
            "repair_loops": max(0, attempts-1),
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
        if candidate_authorship is not None:
            receipt['candidate_authorship'] = dict(
                candidate_commit=candidate_authorship['candidate_commit'],
                final_package_tree_sha256=candidate_authorship['final_package_tree_sha256'],
                audit_sha256=candidate_authorship['content_sha256'],
                signature_and_provenance_verified=candidate_authorship['qualifies_for_factory_receipt'])
        if context.get("schema_version") == "1.1":
            receipt["annotation_context"] = dict(annotation_ids=context["annotation_ids"],
                context_sha256=context["content_sha256"], context_projection_sha256=context["context_projection_sha256"])
        if intelligence.get("routing"):
            receipt["routing"] = intelligence["routing"]
        deferred_memory = self.memory_store is not None and (
            candidate_package_check is not None or candidate_authorship is not None
            or self.candidate_signing_paths is not None)
        prepared_memory = None
        self._scan_controller_value('run-receipt-before-memory', receipt)
        if self.memory_store:
            try:
                if deferred_memory:
                    prepared_memory = self.memory_store.prepare_run(
                        run_dir, order, receipt, context, artifacts)
                    self._scan_controller_value('prepared-semantic-memory', prepared_memory)
                    memory_decision = dict(schema_version="1.0", run_id=run_id,
                        disposition="deferred", reason="awaiting-final-receipt-publication",
                        experience_sha256=None)
                    memory_decision["content_sha256"] = canonical_hash(memory_decision)
                else:
                    memory_decision = self.memory_store.observe_run(
                        run_dir, order, receipt, context, artifacts)
            except (ContractError, OSError, ValueError) as exc:
                prepared_memory = None
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
        if candidate_package_check is not None:
            receipt['candidate_package_finalization'] = candidate_package_check()
            receipt['ledger_head_sha256'] = ledger.head_sha256
            receipt['event_count'] = len(ledger.events)
        elif candidate_authorship is not None and candidate_authorship.get('qualifies_for_factory_receipt'):
            raise ContractError('candidate-package-finalization-required')
        if self.candidate_signing_paths is not None:
            from .build_receipt import compute_build_receipt
            from lightyear_execution.integration import HardenedExecutionContext
            from lightyear_execution.backend import OCIContainerBackend
            bound = self.agents.bounded_provider
            transport = getattr(self.agents.provider, 'transport_recorder', None)
            if (type(self.agents) is not ModelAgentSet or type(bound) is not AccountedModelProvider
                    or bound.order is not order or bound.provider is not self.agents.provider
                    or type(transport) is not ModelTransportRecorder
                    or transport.ledger is not ledger or transport.pending is not None or transport.failed
                    or transport.require_model_admission is not True
                    or type(self.execution_context) is not HardenedExecutionContext
                    or type(self.execution_context.backend) is not OCIContainerBackend):
                raise ContractError('factory-build-receipt-controller-binding')
            runtime = self._verify_runtime_admission(order)
            build_receipt = compute_build_receipt(order, ledger, receipt, bound.calls, runtime, run_dir)
            self._scan_controller_value('factory-build-receipt', build_receipt)
            ledger.append('VERIFYING', 'factory_build_receipt_computed', build_receipt)
            receipt['factory_build_receipt'] = build_receipt
            if not build_receipt['qualifies_for_factory_receipt']:
                receipt['status'] = 'blocked'
            receipt['ledger_head_sha256'] = ledger.head_sha256
            receipt['event_count'] = len(ledger.events)
        receipt["content_sha256"] = canonical_hash(receipt)
        summary = {
            "run_id": run_id,
            "status": receipt["status"],
            "attempts": attempts,
            "title": order.title,
            "receipt_sha256": receipt["content_sha256"],
            "intelligence_mode": intelligence.get("mode"),
            "model_calls": intelligence.get("calls", 0),
            "updated_at": receipt["completed_at"],
        }
        self._scan_controller_value('run-receipt', receipt)
        self._scan_controller_value('run-summary', summary)
        write_json(receipt, run_dir / "receipt.json")
        write_json(summary, run_dir / "summary.json")
        if deferred_memory and prepared_memory is not None:
            # Qualification and both receipt files are committed before optional memory
            # delivery. Delivery failures cannot downgrade that immutable final result.
            try:
                memory_decision = self.memory_store.publish_finalized_run(
                    prepared_memory, run_dir, order, receipt,
                    lambda record: self._scan_controller_value('semantic-memory-record', record),
                    require_factory_receipt=self.candidate_signing_paths is not None)
            except Exception as exc:
                memory_decision = dict(schema_version="1.0", run_id=run_id,
                    disposition="quarantined", reason=f"memory-controller-error:{type(exc).__name__}",
                    experience_sha256=None)
            publication = dict(schema_version="1.0", run_id=run_id,
                receipt_sha256=receipt["content_sha256"], decision=memory_decision)
            try:
                publication["content_sha256"] = canonical_hash(publication)
                self._scan_controller_value('semantic-memory-publication', publication)
                write_json(publication, run_dir / "semantic-memory-publication.json")
            except Exception:
                # Receipt still truthfully says deferred; a delivery receipt is optional.
                pass
        return receipt


def _run_id(value: str | None) -> str:
    if value:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{2,80}", value):
            raise ContractError("run_id contains unsupported characters")
        return value
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{stamp}-{secrets.token_hex(4)}"
