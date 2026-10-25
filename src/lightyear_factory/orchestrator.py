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
        self._receipt_started = time.monotonic()
        self._receipt_transports = []
        self._receipt_pending = False
        self._receipt_journal = None
        lease = None
        try:
            if self.model_admission is not None:
                run_id = _run_id(run_id)
                lease = _ControllerAttemptLease(self.runs_root, run_id, create=True).__enter__()
            return self._run(order, run_id)
        except Exception:
            # Cover allocation/constructor failures and errors writing a blocked receipt.
            # No new persistence is attempted when the failure recorder itself failed.
            if self.workspace_read_manifest is not None:
                raise ContractError('factory-isolation-run-refused') from None
            raise
        finally:
            if lease is not None:
                lease.__exit__()

    def _run(self, order: WorkOrder, run_id: str | None = None) -> dict[str, Any]:
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
            self._begin_reconciliation_evidence(run_dir, run_id, order)
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

            from .graph_tools import graph_policy, FactoryGraphSession
            policy = graph_policy(order)
            if policy["mode"] in ("on-demand", "plain-search") and (
                    type(self.agents) is not ModelAgentSet or self.workspace_read_manifest is None):
                raise ContractError("factory-graph-controller-boundary-required")
            if policy["mode"] == "plain-search":
                from .plain_search import plain_context, FactoryPlainSession
                if self.memory_store is not None:
                    raise ContractError("factory-plain-memory-forbidden")
                context = plain_context(order)
                self._scan_controller_value("controller-context", context)
            else:
                context = self._context(order, workspace.root)
            if policy["mode"] in ("on-demand", "plain-search"):
                if self.agents.graph_session is not None:
                    raise ContractError("factory-graph-agent-reuse")
                if policy["mode"] == "plain-search":
                    self.agents.graph_session = FactoryPlainSession(order, run_id, ledger, context,
                        self.workspace_read_manifest, self._isolation_scanner(), workspace.root)
                else:
                    self.agents.graph_session = FactoryGraphSession(order, run_id, ledger, context,
                        self.approved_projection, self.workspace_read_manifest,
                        self._isolation_scanner(), workspace.root)
            else:
                ledger.append("PLANNED", "graph_policy_bound",
                    dict(policy, run_id=run_id, work_order_sha256=order.content_sha256))
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
            plan["graph"] = dict(policy)
            # Query expansion is controller-validated and retained for Builder citations.
            if policy["mode"] in ("on-demand", "plain-search"):
                references.append(artifacts.write(
                    "queried-implementer-context", "controller", "implementer", context))
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

    def _failure_accounting(self):
        """Allowlisted accounting only; unknown transport outcomes are not zeroes."""
        import math
        from .routing import RoutedBudget
        from .providers import BoundedModelProvider
        from .budgeted_providers import AccountedModelProvider as AccountingProvider
        bound = getattr(self.agents, 'bounded_provider', None)
        if type(bound) is RoutedBudget:
            bound = bound.budget
        # Accounting a refused base-wrapper mutation does not authorize that path.
        # The controller integration test separately requires AccountingProvider.
        if bound is not None and type(bound) not in (AccountingProvider, BoundedModelProvider):
            raise ContractError('reconciliation-accounting-provider')
        calls = [] if bound is None else bound.calls
        hashes = []
        for call in calls:
            row = {}
            for name in ('request_sha256', 'response_sha256'):
                value = call.get(name)
                if value is not None and not re.fullmatch('[0-9a-f]{64}', value):
                    raise ContractError('reconciliation-accounting-hash')
                row[name] = value
            hashes.append(row)
        numbers = {name: 0 if bound is None else getattr(bound, name)
                   for name in ('input_tokens', 'output_tokens')}
        cost = 0.0 if bound is None else bound.estimated_cost_usd
        if (any(type(v) is not int or v < 0 for v in numbers.values())
                or type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
            raise ContractError('reconciliation-accounting-number')
        return dict(schema='factory-sanitized-accounting/1', calls=len(calls),
                    **numbers, estimated_cost_usd=cost,
                    duration_ms=max(0, int((time.monotonic()-self._receipt_started)*1000)),
                    call_hashes=hashes,
                    scanned_transports=[dict(row) for row in getattr(self, '_receipt_transports', [])],
                    in_flight_final_usage='unknown' if getattr(self, '_receipt_pending', False) else 'none',
                    duration_basis='observed-through-checkpoint', billing_final=False)


    def _begin_reconciliation_evidence(self, run_dir, run_id, order):
        if self.model_admission is None:
            return
        from hashlib import sha256
        from .model_admission import _bounded_regular_bytes
        admission = self.execution_context.admission_receipt
        if (admission.get('status') != 'passed'
                or admission.get('work_order_sha256') != order.content_sha256
                or admission.get('content_sha256') != canonical_hash(admission, {'content_sha256'})
                or not re.fullmatch('[0-9a-f]{64}', admission.get('nonce_sha256', ''))):
            raise ContractError('reconciliation-admission-binding')
        source = Path(self.factory_input_paths['workspace'])
        if not source.is_absolute():
            source = self.source_root/source
        raw = _bounded_regular_bytes(source, 8*1024*1024, 'reconciliation-workspace')
        if json.loads(raw) != self.workspace_read_manifest:
            raise ContractError('reconciliation-workspace-binding')
        identity = dict(schema='factory-attempt-identity/1', attempt_id=run_id,
            work_order_sha256=order.content_sha256,
            admission_receipt_sha256=admission['content_sha256'],
            consumed_nonce_sha256=admission['nonce_sha256'],
            sealed_workspace_sha256=sha256(raw).hexdigest(),
            workspace_inventory_sha256=canonical_hash(self.workspace_read_manifest))
        identity['content_sha256'] = canonical_hash(identity)
        with (run_dir/'attempt-identity.json').open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(identity, sort_keys=True, separators=(',', ':'))+'\n')
            stream.flush()
            __import__('os').fsync(stream.fileno())
        self._receipt_identity = identity
        self._receipt_journal = RunLedger(run_dir/'attempt-accounting.jsonl')
        self._checkpoint_accounting()

    def _checkpoint_accounting(self, name=None, raw=None):
        if getattr(self, '_receipt_journal', None) is None:
            return
        from hashlib import sha256
        if name is not None:
            role, separator, phase = name.rpartition('-')
            if role not in ('planner', 'builder', 'failure_analyst') or phase not in ('prompt', 'response'):
                return
            if phase == 'prompt':
                self._receipt_transports.append(dict(role=role, prompt_sha256=sha256(raw).hexdigest(), response_sha256=None))
                self._receipt_pending = True
            else:
                if not self._receipt_pending or self._receipt_transports[-1]['role'] != role:
                    raise ContractError('reconciliation-transport-order')
                self._receipt_transports[-1]['response_sha256'] = sha256(raw).hexdigest()
                self._receipt_pending = False
        accounting = self._failure_accounting()
        _validate_reconciliation_accounting(accounting)
        self._receipt_journal.append('OBSERVED', 'sanitized_accounting', dict(
            attempt_identity_sha256=self._receipt_identity['content_sha256'],
            accounting=accounting))
        with self._receipt_journal.path.open('ab') as stream:
            __import__('os').fsync(stream.fileno())

    @staticmethod
    def reconcile_interrupted(runs_root, run_id, *, work_order_sha256,
                              consumed_nonce_sha256, sealed_workspace_sha256):
        """Abort-only: no admission, provider, retry, resume, or signing interface."""
        import os
        from .model_admission import _bounded_regular_bytes
        run_id = _run_id(run_id)
        for value in (work_order_sha256, consumed_nonce_sha256, sealed_workspace_sha256):
            if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
                raise ContractError('reconciliation-binding-required')
        root = Path(runs_root)
        with _ControllerAttemptLease(root, run_id, create=False):
            run_dir = root/run_id
            identity = json.loads(_bounded_regular_bytes(run_dir/'attempt-identity.json', 16384, 'reconciliation-identity'))
            expected = dict(attempt_id=run_id, work_order_sha256=work_order_sha256,
                consumed_nonce_sha256=consumed_nonce_sha256,
                sealed_workspace_sha256=sealed_workspace_sha256)
            identity_fields = {'schema','attempt_id','work_order_sha256','consumed_nonce_sha256',
                'sealed_workspace_sha256','admission_receipt_sha256','workspace_inventory_sha256','content_sha256'}
            if (not isinstance(identity, dict) or set(identity) != identity_fields
                    or any(not isinstance(identity[k],str) or not re.fullmatch('[0-9a-f]{64}',identity[k])
                           for k in identity_fields-{'schema','attempt_id'})
                    or identity.get('schema') != 'factory-attempt-identity/1'
                    or identity.get('content_sha256') != canonical_hash(identity, {'content_sha256'})
                    or any(identity.get(k) != v for k,v in expected.items())):
                raise ContractError('reconciliation-identity-binding')
            nonces = _bounded_regular_bytes(root/'admission-nonces.sha256', 8*1024*1024, 'reconciliation-nonce-store').decode('ascii')
            if (not nonces.endswith('\n') or consumed_nonce_sha256 not in nonces.splitlines()
                    or any(not re.fullmatch('[0-9a-f]{64}', x) for x in nonces.splitlines())):
                raise ContractError('reconciliation-consumed-nonce-required')
            for name in ('events.jsonl', 'attempt-accounting.jsonl'):
                data = _bounded_regular_bytes(run_dir/name, 32*1024*1024, 'reconciliation-ledger')
                if not data or not data.endswith(b'\n') or any(not line.strip() for line in data.splitlines()):
                    raise ContractError('reconciliation-incomplete-ledger')
            ledger = RunLedger(run_dir/'events.jsonl')
            checkpoints = RunLedger(run_dir/'attempt-accounting.jsonl')
            if (any((run_dir/name).exists() or (run_dir/name).is_symlink() for name in ('receipt.json','summary.json'))
                    or any(e['state'] in ('PASSED', 'BLOCKED', 'INTERRUPTED') for e in ledger.events)):
                raise ContractError('reconciliation-terminal-attempt-refused')
            if (not any(e['kind']=='work_order_accepted' and e['payload'].get('work_order_sha256')==work_order_sha256 for e in ledger.events)
                    or not any(e['kind']=='hardened_admission_bound' and e['payload'].get('admission_receipt_sha256')==identity['admission_receipt_sha256'] for e in ledger.events)
                    or not any(e['kind']=='workspace_read_manifest' and e['payload'].get('sha256')==identity['workspace_inventory_sha256'] for e in ledger.events)):
                raise ContractError('reconciliation-run-ledger-binding')
            if not checkpoints.events or any(
                    e['state'] != 'OBSERVED' or e['kind'] != 'sanitized_accounting'
                    or set(e['payload']) != {'attempt_identity_sha256','accounting'}
                    or e['payload'].get('attempt_identity_sha256') != identity['content_sha256']
                    for e in checkpoints.events):
                raise ContractError('reconciliation-accounting-binding')
            accounting = checkpoints.events[-1]['payload']['accounting']
            _validate_reconciliation_accounting(accounting)
            payload = dict(schema='factory-interrupted-attempt/1', **expected,
                status='interrupted; awaiting human attestation',
                admission_receipt_sha256=identity['admission_receipt_sha256'],
                attempt_identity_sha256=identity['content_sha256'],
                accounting_ledger_head_sha256=checkpoints.head_sha256,
                accounting=accounting, unsigned=True, human_attestation=None,
                qualifies_for_factory_receipt=False, resume_allowed=False,
                retry_allowed=False, new_admission_allowed=False)
            event = ledger.append('INTERRUPTED', 'interrupted_attempt', payload)
            with ledger.path.open('ab') as stream:
                os.fsync(stream.fileno())
            return event

    def _validate_attempt_budget(self, order):
        if self.workspace_read_manifest is not None:
            if type(order.max_attempts) is not int or not 1 <= order.max_attempts <= 3:
                raise ContractError('factory-attempt-budget-refused')

    def _record_isolation_failure(self, run_dir, order, attempts, ledger):
        # No raw exception, drained model evidence, private names, context or paths.
        self._checkpoint_accounting()
        ledger.append('BLOCKED', 'controller_error', {'reason': 'factory-isolation-run-refused'})
        receipt = {'schema_version': RUN_RECEIPT_SCHEMA_VERSION,
                   'receipt_type': 'lightyear-autonomous-factory-run',
                   'status': 'blocked', 'attempts': attempts,
                   'repair_loops': max(0, attempts-1),
                   'work_order_sha256': order.content_sha256,
                   'ledger_head_sha256': ledger.head_sha256,
                   'qualifies_for_factory_receipt': False,
                   'reason': 'factory-isolation-run-refused',
                   'failure_accounting': self._failure_accounting()}
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
            self._checkpoint_accounting(name, raw)
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
        if state == "BLOCKED":
            self._checkpoint_accounting()
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
        if state == "BLOCKED":
            receipt["failure_accounting"] = self._failure_accounting()
        from .graph_tools import graph_summary
        receipt["graph"] = graph_summary(order, ledger, run_id)
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

class _ControllerAttemptLease:
    """Separate OS lease; closing/killing releases it without deleting its inode."""
    def __init__(self, root, run_id, *, create):
        self.root, self.run_id, self.create = Path(root), run_id, create
        self.stream = None

    def __enter__(self):
        import os
        import stat
        try:
            directory = self.root/'.controller-leases'
            path = directory/(self.run_id+'.lock')
            for parent in (path, *path.parents):
                if parent.exists() or parent.is_symlink():
                    info = parent.lstat()
                    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0)&0x400:
                        raise ContractError('reconciliation-link-refused')
            if self.create:
                directory.mkdir(parents=True, exist_ok=True)
            flags = os.O_RDWR | (os.O_CREAT if self.create else 0) | getattr(os, 'O_NOFOLLOW', 0)
            fd = os.open(path, flags, 0o600)
            self.stream = os.fdopen(fd, 'r+b')
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ContractError('reconciliation-lease-file')
            if info.st_size == 0:
                if not self.create:
                    raise ContractError('reconciliation-lease-incomplete')
                self.stream.write(b'0');self.stream.flush()
            elif info.st_size != 1:
                raise ContractError('reconciliation-lease-shape')
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self
        except Exception:
            if self.stream is not None:self.stream.close()
            raise ContractError('reconciliation-controller-live-or-lease-refused') from None

    def __exit__(self, *_):
        self.stream.close()


def _validate_reconciliation_accounting(value):
    import math
    required = {'schema','calls','input_tokens','output_tokens','estimated_cost_usd',
                'duration_ms','duration_basis','call_hashes','scanned_transports','in_flight_final_usage','billing_final'}
    if not isinstance(value, dict) or set(value) != required or value['schema'] != 'factory-sanitized-accounting/1':
        raise ContractError('reconciliation-accounting-shape')
    if any(type(value[k]) is not int or value[k] < 0 for k in ('calls','input_tokens','output_tokens','duration_ms')):
        raise ContractError('reconciliation-accounting-counts')
    cost=value['estimated_cost_usd']
    if type(cost) not in (int,float) or not math.isfinite(cost) or cost<0 or value['billing_final'] is not False:
        raise ContractError('reconciliation-accounting-cost')
    if value['duration_basis'] != 'observed-through-checkpoint':
        raise ContractError('reconciliation-accounting-duration')
    if value['in_flight_final_usage'] not in ('unknown','none') or not isinstance(value['call_hashes'],list) or len(value['call_hashes']) != value['calls']:
        raise ContractError('reconciliation-accounting-calls')
    if not isinstance(value['scanned_transports'], list):
        raise ContractError('reconciliation-accounting-transports')
    for row in value['call_hashes']:
        if not isinstance(row,dict) or set(row) != {'request_sha256','response_sha256'}:
            raise ContractError('reconciliation-accounting-hashes')
        if any(v is not None and (not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v)) for v in row.values()):
            raise ContractError('reconciliation-accounting-hash')
    for row in value['scanned_transports']:
        if not isinstance(row,dict) or set(row) != {'role','prompt_sha256','response_sha256'} or row['role'] not in ('planner','builder','failure_analyst'):
            raise ContractError('reconciliation-accounting-transport')
        if not isinstance(row['prompt_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['prompt_sha256']):
            raise ContractError('reconciliation-accounting-prompt')
        if row['response_sha256'] is not None and (not isinstance(row['response_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['response_sha256'])):
            raise ContractError('reconciliation-accounting-response')
