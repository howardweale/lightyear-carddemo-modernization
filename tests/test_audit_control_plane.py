from __future__ import annotations

import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from lightyear_audit.builder import build_canonical_audit
from lightyear_audit.contracts import AuditContractError, EventDraft, ExceptionGrant
from lightyear_audit.dossier import build_dossier, render_markdown
from lightyear_audit.ledger import (
    AppendOnlyAuditLog,
    build_snapshot,
    validate_snapshot,
)
from lightyear_audit.policy import AuditPolicyEngine
from lightyear_audit.store import AuditStore
from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph
from lightyear_execution.contracts import canonical_hash as execution_hash


ROOT = Path(__file__).resolve().parents[1]
GRAPH_RECEIPT = ROOT / "knowledge" / "graph.receipt.json"
EVIDENCE_RECEIPT = ROOT / "knowledge" / "evidence" / "source.receipt.json"
RUNTIMES = [
    ROOT / "knowledge" / "runtime" / "runtime.snapshot.json.gz",
    ROOT / "knowledge" / "runtime" / "zosmf" / "intcalc.runtime.snapshot.json.gz",
]
WORK_ORDER = ROOT / "factory" / "work-orders" / "intcalc-repair.example.json"
POLICY = ROOT / "audit" / "policies" / "promotion.json"
EXECUTION = ROOT / "factory" / "execution" / "conformance.receipt.json"


def canonical_snapshot(signing_key: bytes | None = None) -> dict:
    return build_canonical_audit(
        GRAPH_RECEIPT,
        EVIDENCE_RECEIPT,
        RUNTIMES,
        WORK_ORDER,
        POLICY,
        signing_key,
        EXECUTION,
    )


def draft(sequence: int = 1, visibility: str = "shared") -> EventDraft:
    return EventDraft.from_dict({
        "occurred_at": f"2022-07-18T00:00:0{sequence}.000Z",
        "actor": {"id": "system:test", "kind": "service", "role": "system"},
        "action": "test.event_recorded",
        "subject": {"id": f"test:subject:{sequence}", "kind": "test_subject"},
        "evidence": [{"id": f"test:evidence:{sequence}", "kind": "test", "sha256": "a" * 64}],
        "details": {"sequence": sequence},
        "visibility": visibility,
    })


class AuditControlPlaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_graph(ROOT / "knowledge" / "graph.snapshot.json.gz")

    def test_canonical_ledger_is_deterministic_and_blocks_unproven_promotion(self) -> None:
        first = canonical_snapshot()
        second = canonical_snapshot()
        self.assertEqual(first["content_sha256"], second["content_sha256"])
        self.assertEqual(15, first["statistics"]["event_count"])
        self.assertEqual({"blocked": 5, "passed": 3}, first["statistics"]["decisions"])
        self.assertEqual(0, first["statistics"]["active_exceptions"])
        promotion = AuditStore(first).summary()["promotion_decisions"][0]
        self.assertEqual("blocked", promotion["status"])
        self.assertEqual(
            ["hardened-execution-enforcement", "mainframe-equivalence"], promotion["gaps"]
        )
        errors, warnings = validate_snapshot(first, self.graph["content_sha256"])
        self.assertEqual([], errors)
        self.assertTrue(any("unsigned" in item for item in warnings))

    def test_audit_json_schemas_match_runtime_contracts(self) -> None:
        schema_dir = ROOT / "audit" / "schema"
        names = {
            "audit-event.schema.json",
            "audit-snapshot.schema.json",
            "policy-decision.schema.json",
            "exception.schema.json",
            "policy-set.schema.json",
            "release-dossier.schema.json",
        }
        schemas = {
            name: json.loads((schema_dir / name).read_text(encoding="utf-8"))
            for name in names
        }
        for name, schema in schemas.items():
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"], name)
            self.assertTrue(schema["$id"].endswith(name), name)
        self.assertEqual("1.0", schemas["audit-event.schema.json"]["properties"]["schema_version"]["const"])
        self.assertEqual("1.0", schemas["audit-snapshot.schema.json"]["properties"]["schema_version"]["const"])
        self.assertEqual("1.0", schemas["policy-set.schema.json"]["properties"]["schema_version"]["const"])

    def test_deletion_reordering_and_mutation_are_detected(self) -> None:
        payload = canonical_snapshot()
        deleted = copy.deepcopy(payload)
        del deleted["events"][3]
        errors, _ = validate_snapshot(deleted, self.graph["content_sha256"])
        self.assertTrue(any("sequence" in item or "chain" in item for item in errors))
        self.assertTrue(any("checkpoint" in item for item in errors))
        reordered = copy.deepcopy(payload)
        reordered["events"][3], reordered["events"][4] = (
            reordered["events"][4], reordered["events"][3]
        )
        errors, _ = validate_snapshot(reordered, self.graph["content_sha256"])
        self.assertTrue(any("chain" in item or "sequence" in item for item in errors))
        mutated = copy.deepcopy(payload)
        mutated["decisions"][0]["status"] = "passed"
        errors, _ = validate_snapshot(mutated, self.graph["content_sha256"])
        self.assertIn("audit decision projection is stale", errors)

    def test_signed_checkpoint_verifies_and_wrong_key_fails(self) -> None:
        payload = canonical_snapshot(b"correct-signing-key")
        errors, warnings = validate_snapshot(
            payload, self.graph["content_sha256"], b"correct-signing-key"
        )
        self.assertEqual([], errors)
        self.assertEqual([], warnings)
        errors, _ = validate_snapshot(payload, self.graph["content_sha256"], b"wrong-key")
        self.assertIn("audit checkpoint signature is invalid", errors)

    def test_append_only_log_uses_expected_head_and_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            log = AppendOnlyAuditLog(path)
            first = log.append(draft(1))
            second = log.append(draft(2), expected_head=first["event_sha256"])
            self.assertEqual(2, second["sequence"])
            with self.assertRaisesRegex(AuditContractError, "head changed"):
                log.append(draft(3), expected_head="0" * 64)
            lines = path.read_text(encoding="utf-8").splitlines()
            item = json.loads(lines[0])
            item["details"]["sequence"] = 99
            lines[0] = json.dumps(item)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(AuditContractError, "hash"):
                log.read()

    def test_secrets_and_builder_policy_decisions_are_rejected(self) -> None:
        unsafe = draft().to_dict()
        unsafe["details"] = {"authorization": "Bearer should-never-be-recorded"}
        with self.assertRaisesRegex(AuditContractError, "Sensitive field"):
            EventDraft.from_dict(unsafe)
        decision = draft().to_dict()
        decision["action"] = "policy.decision_recorded"
        decision["actor"] = {"id": "agent:builder", "kind": "agent", "role": "builder"}
        with self.assertRaisesRegex(AuditContractError, "cannot record policy decisions"):
            EventDraft.from_dict(decision)

    def test_exception_requires_human_approval_controls_and_valid_expiry(self) -> None:
        payload = json.loads(
            (ROOT / "audit" / "examples" / "exception.example.json").read_text(encoding="utf-8")
        )
        grant = ExceptionGrant.from_dict(payload, now="2026-08-11T00:00:00Z")
        self.assertEqual("approver", grant.approved_by.role)
        expired = copy.deepcopy(payload)
        expired["expires_at"] = "2026-08-01T00:00:00Z"
        with self.assertRaisesRegex(AuditContractError, "expired"):
            ExceptionGrant.from_dict(expired, now="2026-08-11T00:00:00Z")
        agent_approved = copy.deepcopy(payload)
        agent_approved["approved_by"]["kind"] = "agent"
        with self.assertRaisesRegex(AuditContractError, "human approver"):
            ExceptionGrant.from_dict(agent_approved, now="2026-08-11T00:00:00Z")

    def test_mainframe_promotion_policy_cannot_be_overridden(self) -> None:
        engine = AuditPolicyEngine.load(POLICY)
        snapshot = canonical_snapshot()
        exception = json.loads(
            (ROOT / "audit" / "examples" / "exception.example.json").read_text(encoding="utf-8")
        )
        exception["policy_id"] = "release.promotion"
        exception["subject_id"] = "release:carddemo-intcalc:v0.10-demo"
        runtime = [item for item in snapshot["decisions"] if item["policy_id"].startswith("runtime.")]
        with self.assertRaisesRegex(AuditContractError, "cannot be overridden"):
            engine.promotion_decision(
                "release:carddemo-intcalc:v0.10-demo",
                runtime,
                self.graph["content_sha256"],
                "b" * 64,
                "2026-08-11T00:00:00Z",
                exception,
            )

    def test_release_dossier_is_content_addressed_and_explains_the_block(self) -> None:
        dossier = build_dossier(canonical_snapshot(), "release:carddemo-intcalc:v0.11.2-demo")
        self.assertEqual("blocked", dossier["status"])
        self.assertIn("mainframe-equivalence", dossier["gaps"])
        self.assertIn("hardened-execution-enforcement", dossier["gaps"])
        self.assertEqual(1, len(dossier["execution_decisions"]))
        self.assertGreaterEqual(len(dossier["evidence_inventory"]), 6)
        markdown = render_markdown(dossier)
        self.assertIn("LIGHTYEAR release evidence dossier", markdown)
        self.assertIn("BLOCKED", markdown)
        self.assertIn(dossier["content_sha256"], markdown)

    def test_only_signed_factory_execution_can_pass_hardened_readiness(self) -> None:
        policy_sha = json.loads(EXECUTION.read_text(encoding="utf-8"))[
            "execution_policy_sha256"
        ]
        runtime_evidence = {
            "backend": "oci-docker",
            "assurance": "enforced",
            "enforced": True,
        }
        runtime_evidence["content_sha256"] = execution_hash(runtime_evidence)
        probe = {
            "schema_version": "1.0",
            "receipt_type": "lightyear-live-execution-probe",
            "status": "passed",
            "assurance": "enforced",
            "runtime_ready": True,
            "production_ready": False,
            "execution_policy_sha256": policy_sha,
            "runtime": "docker",
            "exit_code": 0,
            "timed_out": False,
            "output_sha256": "a" * 64,
            "execution": runtime_evidence,
            "gaps": ["signed-factory-work-order-not-observed"],
            "limitations": ["Runtime proof only."],
        }
        probe["content_sha256"] = execution_hash(probe)

        order_sha = "b" * 64
        required = ["planner:factory:plan", "verifier:factory:verify"]
        security = {
            "evidence_class": "signed-admitted-oci-factory-run",
            "status": "enforced",
            "production_ready": True,
            "backend": "oci-docker",
            "work_order_sha256": order_sha,
            "execution_policy_sha256": policy_sha,
            "admission_receipt_sha256": "c" * 64,
            "identity_receipt_sha256": ["d" * 64, "e" * 64],
            "authorization_receipt_sha256": ["f" * 64, "1" * 64],
            "required_agent_actions": required,
            "authorized_agent_actions": required,
            "gate_execution_sha256": ["2" * 64],
            "secret_lease_sha256": [],
            "secrets_persisted": False,
            "gaps": [],
        }
        security["content_sha256"] = execution_hash(security)
        factory = {
            "schema_version": "1.0",
            "receipt_type": "lightyear-autonomous-factory-run",
            "run_id": "signed-factory-audit-test",
            "work_order_sha256": order_sha,
            "status": "passed",
            "verification": {"status": "passed", "gates": []},
            "execution_security": security,
        }
        factory["content_sha256"] = execution_hash(factory)

        with tempfile.TemporaryDirectory() as directory:
            receipt_path = Path(directory) / "execution.json"
            receipt_path.write_text(json.dumps(probe), encoding="utf-8")
            probe_snapshot = build_canonical_audit(
                GRAPH_RECEIPT, EVIDENCE_RECEIPT, RUNTIMES, WORK_ORDER, POLICY,
                execution_receipt_path=receipt_path,
            )
            receipt_path.write_text(json.dumps(factory), encoding="utf-8")
            factory_snapshot = build_canonical_audit(
                GRAPH_RECEIPT, EVIDENCE_RECEIPT, RUNTIMES, WORK_ORDER, POLICY,
                execution_receipt_path=receipt_path,
            )

        probe_summary = AuditStore(probe_snapshot).summary()
        factory_summary = AuditStore(factory_snapshot).summary()
        self.assertEqual("blocked", probe_summary["trust_posture"]["execution_status"])
        self.assertEqual("passed", factory_summary["trust_posture"]["execution_status"])
        self.assertEqual(
            ["mainframe-equivalence"],
            factory_summary["promotion_decisions"][0]["gaps"],
        )

    def test_auditor_private_events_are_hidden_from_implementers(self) -> None:
        payload = build_snapshot(
            [draft(1), draft(2, "auditor_private")],
            self.graph["content_sha256"],
            "2022-07-18T00:00:03.000Z",
        )
        store = AuditStore(payload)
        self.assertEqual(1, store.events("implementer")["total"])
        self.assertEqual(2, store.events("auditor")["total"])

    def test_control_tower_http_api_and_ui_are_read_only_projections(self) -> None:
        store = AuditStore(canonical_snapshot())
        server = ExplorerServer(
            ("127.0.0.1", 0),
            GraphExplorerIndex(self.graph),
            ROOT / "knowledge" / "viewer",
            audit_store=store,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(f"{base}/api/audit/summary", timeout=3) as response:
                summary = json.load(response)
            self.assertEqual(15, summary["statistics"]["event_count"])
            self.assertEqual("blocked", summary["trust_posture"]["execution_status"])
            with urlopen(
                f"{base}/api/audit/events?{urlencode({'audience': 'implementer'})}", timeout=3
            ) as response:
                events = json.load(response)
            self.assertEqual(15, events["total"])
            release = summary["promotion_decisions"][0]["subject_id"]
            with urlopen(
                f"{base}/api/audit/dossier?{urlencode({'release': release})}", timeout=3
            ) as response:
                dossier = json.load(response)
            self.assertEqual("blocked", dossier["status"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        html = (ROOT / "knowledge" / "viewer" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "knowledge" / "viewer" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="audit-tab"', html)
        self.assertIn("hash-chained audit ledger is authoritative", html)
        self.assertIn("/api/audit/summary", script)
        self.assertIn("loadAuditDossier", script)
        self.assertIn('id="audit-execution"', html)
        self.assertIn("renderFactorySecurity", script)
        self.assertIn("Evidence class:", script)


if __name__ == "__main__":
    unittest.main()
