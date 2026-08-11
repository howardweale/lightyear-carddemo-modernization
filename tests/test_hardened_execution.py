from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_execution.admission import (
    AdmissionNonceStore,
    sign_work_order,
    verify_work_order,
)
from lightyear_execution.backend import ExecutionResult, LocalProcessBackend, OCIContainerBackend
from lightyear_execution.conformance import build_conformance_receipt
from lightyear_execution.contracts import ExecutionContractError, ExecutionPolicy
from lightyear_execution.contracts import canonical_hash as execution_hash
from lightyear_execution.evidence import normalize_execution_evidence
from lightyear_execution.identity import IdentityAuthority
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_execution.secrets import SecretBroker
from lightyear_factory.contracts import WorkOrder
from lightyear_factory.agents import LocalAgentSet
from lightyear_factory.orchestrator import FactoryOrchestrator


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "factory" / "execution" / "policy.json"
WORK_ORDER_PATH = ROOT / "factory" / "work-orders" / "intcalc-repair.example.json"
SIGNING_KEY = b"admission-test-key-that-is-at-least-thirty-two-bytes"
IDENTITY_KEY = b"identity-test-key-that-is-at-least-thirty-two-bytes"
ISSUED = "2026-08-11T00:00:00Z"
EXPIRES = "2026-08-11T00:15:00Z"
NOW = "2026-08-11T00:01:00Z"


def envelope(policy: ExecutionPolicy, order: WorkOrder, nonce: str = "nonce-test-one") -> dict:
    return sign_work_order(
        order,
        policy,
        "operator:release",
        "lightyear-release-operator",
        SIGNING_KEY,
        ISSUED,
        EXPIRES,
        nonce,
    )


class HardenedExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ExecutionPolicy.load(POLICY_PATH)
        self.order = WorkOrder.load(WORK_ORDER_PATH)

    def test_policy_rejects_weakened_isolation_controls(self) -> None:
        payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        for field, value in (
            ("network_mode", "bridge"),
            ("read_only_root", False),
            ("workspace_read_only", False),
            ("cap_drop_all", False),
            ("no_new_privileges", False),
            ("run_as_user", "0:0"),
        ):
            weakened = copy.deepcopy(payload)
            weakened["isolation"][field] = value
            with self.assertRaises(ExecutionContractError, msg=field):
                ExecutionPolicy.from_dict(weakened)

    def test_container_invocation_is_pinned_networkless_non_root_and_secret_free(self) -> None:
        backend = OCIContainerBackend(self.policy, "docker", execute=False)
        invocation, plan = backend.build_invocation(
            ("python3", "-m", "lightyear_factory.private_benchmark"),
            ROOT,
            {
                "PYTHONPATH": str(ROOT / "src"),
                "LIGHTYEAR_FACTORY_WORKSPACE": str(ROOT),
                "LIGHTYEAR_NETWORK_POLICY": "deny",
                "OPENAI_API_KEY": "never-render-this-secret",
            },
        )
        joined = " ".join(invocation)
        for value in (
            "--network none",
            "--read-only",
            "--cap-drop ALL",
            "no-new-privileges:true",
            "--user 65532:65532",
            "readonly",
            "@sha256:",
        ):
            self.assertIn(value, joined)
        self.assertNotIn("never-render-this-secret", joined)
        self.assertNotIn("OPENAI_API_KEY", plan["environment_names"])
        self.assertEqual("/workspace/src", joined.split("PYTHONPATH=", 1)[1].split()[0])
        self.assertEqual(
            "/workspace",
            joined.split("LIGHTYEAR_FACTORY_WORKSPACE=", 1)[1].split()[0],
        )
        self.assertNotIn(str(ROOT), joined.split("LIGHTYEAR_FACTORY_WORKSPACE=", 1)[1].split()[0])

    def test_conformance_receipt_is_deterministic_and_not_false_proof(self) -> None:
        first = build_conformance_receipt(self.policy)
        second = build_conformance_receipt(self.policy)
        self.assertEqual(first, second)
        self.assertEqual("passed", first["status"])
        self.assertEqual("simulated", first["assurance"])
        self.assertFalse(first["production_ready"])
        self.assertIn("container-runtime-enforcement-not-observed", first["gaps"])
        self.assertTrue(all(first["checks"].values()))
        normalized = normalize_execution_evidence(first)
        self.assertFalse(normalized["hardened_execution_ready"])
        self.assertEqual("policy-conformance-simulation", normalized["evidence_class"])

    def test_live_runtime_probe_cannot_impersonate_signed_factory_evidence(self) -> None:
        execution = {
            "backend": "oci-docker",
            "assurance": "enforced",
            "enforced": True,
        }
        execution["content_sha256"] = execution_hash(execution)
        probe = {
            "schema_version": "1.0",
            "receipt_type": "lightyear-live-execution-probe",
            "status": "passed",
            "assurance": "enforced",
            "runtime_ready": True,
            "production_ready": False,
            "execution_policy_sha256": self.policy.content_sha256,
            "runtime": "docker",
            "exit_code": 0,
            "timed_out": False,
            "output_sha256": "a" * 64,
            "execution": execution,
            "gaps": ["signed-factory-work-order-not-observed"],
            "limitations": ["Runtime proof only."],
        }
        probe["content_sha256"] = execution_hash(probe)
        normalized = normalize_execution_evidence(probe)
        self.assertTrue(normalized["checks"]["runtime_enforced"])
        self.assertFalse(normalized["hardened_execution_ready"])
        self.assertIn("signed-factory-work-order-not-observed", normalized["gaps"])

        tampered = copy.deepcopy(probe)
        tampered["gaps"] = []
        with self.assertRaisesRegex(ExecutionContractError, "receipt hash"):
            normalize_execution_evidence(tampered)

    def test_signed_admission_detects_tampering_expiry_wrong_key_and_replay(self) -> None:
        signed = envelope(self.policy, self.order)
        with tempfile.TemporaryDirectory() as directory:
            store = AdmissionNonceStore(Path(directory) / "nonces.sha256")
            admitted, receipt = verify_work_order(
                signed,
                self.policy,
                {"lightyear-release-operator": SIGNING_KEY},
                NOW,
                store,
            )
            self.assertEqual(self.order.content_sha256, admitted.content_sha256)
            self.assertEqual("passed", receipt["status"])
            with self.assertRaisesRegex(ExecutionContractError, "already been consumed"):
                verify_work_order(
                    signed,
                    self.policy,
                    {"lightyear-release-operator": SIGNING_KEY},
                    NOW,
                    store,
                )
        tampered = copy.deepcopy(signed)
        tampered["work_order"]["goal"] = "Silently widen the goal"
        with self.assertRaisesRegex(ExecutionContractError, "envelope hash"):
            verify_work_order(
                tampered,
                self.policy,
                {"lightyear-release-operator": SIGNING_KEY},
                NOW,
            )
        with self.assertRaisesRegex(ExecutionContractError, "signature"):
            verify_work_order(
                signed,
                self.policy,
                {"lightyear-release-operator": b"wrong-key-that-is-still-at-least-thirty-two-bytes"},
                NOW,
            )
        with self.assertRaisesRegex(ExecutionContractError, "currently valid"):
            verify_work_order(
                signed,
                self.policy,
                {"lightyear-release-operator": SIGNING_KEY},
                "2026-08-11T00:16:00Z",
            )

    def test_agent_credentials_are_role_action_work_order_and_time_scoped(self) -> None:
        authority = IdentityAuthority(self.policy, IDENTITY_KEY)
        token, receipt = authority.issue(
            "builder", self.order.content_sha256, ISSUED, "credential:test-builder"
        )
        claims = authority.verify(token, "factory:build", self.order.content_sha256, NOW)
        self.assertEqual("builder", claims["role"])
        self.assertNotIn(token, json.dumps(receipt))
        with self.assertRaisesRegex(ExecutionContractError, "authorize"):
            authority.verify(token, "factory:verify", self.order.content_sha256, NOW)
        with self.assertRaisesRegex(ExecutionContractError, "different work order"):
            authority.verify(token, "factory:build", "f" * 64, NOW)
        with self.assertRaisesRegex(ExecutionContractError, "expired"):
            authority.verify(
                token, "factory:build", self.order.content_sha256, "2026-08-11T00:16:00Z"
            )

    def test_secret_broker_is_allowlisted_one_use_and_never_persists_values(self) -> None:
        authority = IdentityAuthority(self.policy, IDENTITY_KEY)
        token, _ = authority.issue(
            "provider", self.order.content_sha256, ISSUED, "credential:test-provider"
        )
        broker = SecretBroker(
            self.policy, authority, {"OPENAI_API_KEY": "highly-sensitive-test-value"}
        )
        lease, receipt = broker.lease(
            token, "OPENAI_API_KEY", self.order.content_sha256, NOW
        )
        encoded = json.dumps(receipt)
        self.assertNotIn("highly-sensitive-test-value", encoded)
        self.assertFalse(receipt["value_persisted"])
        self.assertEqual("highly-sensitive-test-value", lease.consume())
        with self.assertRaisesRegex(ExecutionContractError, "already been consumed"):
            lease.consume()
        with self.assertRaisesRegex(ExecutionContractError, "not allowed"):
            broker.lease(token, "UNAPPROVED_SECRET", self.order.content_sha256, NOW)

    def test_execution_context_reports_simulation_without_claiming_enforcement(self) -> None:
        _, admission = verify_work_order(
            envelope(self.policy, self.order, "nonce-context"),
            self.policy,
            {"lightyear-release-operator": SIGNING_KEY},
            NOW,
        )
        context = HardenedExecutionContext(
            self.policy,
            OCIContainerBackend(self.policy, "docker", execute=False),
            admission,
            IDENTITY_KEY,
        )
        binding = context.bind(self.order.content_sha256, ISSUED)
        context.authorize("planner", "factory:plan", NOW)
        self.assertEqual(5, len(binding["identity_receipts"]))
        context.record_verification({
            "gates": [{"execution": {"content_sha256": "a" * 64, "enforced": False}}]
        })
        summary = context.summary()
        self.assertEqual("simulated", summary["status"])
        self.assertFalse(summary["production_ready"])

    def test_orchestrator_binds_admission_identities_and_enforced_gate_evidence(self) -> None:
        class TestEnforcedBackend:
            backend_id = "oci-test-enforced"

            def execute(self, command, workspace, environment, timeout):
                result = LocalProcessBackend().execute(command, workspace, environment, timeout)
                return ExecutionResult(
                    result.exit_code,
                    result.timed_out,
                    result.duration_ms,
                    result.stdout,
                    result.stderr,
                    {
                        "backend": self.backend_id,
                        "assurance": "enforced",
                        "enforced": True,
                    },
                )

        _, admission = verify_work_order(
            envelope(self.policy, self.order, "nonce-orchestrator"),
            self.policy,
            {"lightyear-release-operator": SIGNING_KEY},
            NOW,
        )
        context = HardenedExecutionContext(
            self.policy,
            TestEnforcedBackend(),
            admission,
            IDENTITY_KEY,
        )
        with tempfile.TemporaryDirectory() as directory:
            receipt = FactoryOrchestrator(
                ROOT,
                Path(directory),
                LocalAgentSet(),
                graph_path=ROOT / "knowledge" / "graph.snapshot.json.gz",
                execution_context=context,
            ).run(self.order, "hardened-integration-test")
            events = [
                json.loads(line)
                for line in (Path(directory) / "hardened-integration-test" / "events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
        self.assertEqual("passed", receipt["status"])
        self.assertTrue(receipt["execution_security"]["production_ready"])
        self.assertEqual("enforced", receipt["execution_security"]["status"])
        self.assertIn("hardened_admission_bound", [item["kind"] for item in events])
        self.assertFalse(receipt["execution_security"]["secrets_persisted"])
        normalized = normalize_execution_evidence(receipt)
        self.assertTrue(normalized["hardened_execution_ready"])
        self.assertEqual("signed-admitted-oci-factory-run", normalized["evidence_class"])
        self.assertTrue(normalized["checks"]["signed_admission_bound"])
        self.assertTrue(normalized["checks"]["agent_actions_authorized"])
        self.assertEqual([], normalized["gaps"])
        partial = copy.deepcopy(receipt)
        partial["execution_security"]["authorized_agent_actions"] = []
        partial["execution_security"]["content_sha256"] = execution_hash(
            partial["execution_security"], {"content_sha256"}
        )
        partial["content_sha256"] = execution_hash(partial, {"content_sha256"})
        downgraded = normalize_execution_evidence(partial)
        self.assertFalse(downgraded["hardened_execution_ready"])
        self.assertIn("required-agent-actions-not-authorized", downgraded["gaps"])

    def test_execution_schemas_are_versioned(self) -> None:
        names = {
            "execution-policy.schema.json",
            "signed-work-order.schema.json",
            "execution-conformance.schema.json",
            "execution-evidence.schema.json",
        }
        for name in names:
            schema = json.loads((ROOT / "factory" / "schema" / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertIn("1.0", schema["$id"])


if __name__ == "__main__":
    unittest.main()
