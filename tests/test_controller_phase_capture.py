"""CI-only synthetic controller capture tests; no provider or native proof."""
from dataclasses import replace
from hashlib import sha256
import json
import unittest

from lightyear_factory.controller_phase_capture import CaptureIdentity, ControllerPhaseCapture
from lightyear_factory.human_metrics import encode_human_event
from lightyear_factory.journal_metrics import MetricsError


IDENTITY = CaptureIdentity("e" * 40, "campaign-1", "case-1", "execution-1",
                           "a" * 64, "b" * 64, "clock-1")


def capture(identity=IDENTITY, ticks=(10, 20, 25, 40)):
    values = iter(ticks)
    return ControllerPhaseCapture(identity, clock=lambda: next(values))


def transport(**changes):
    payload = dict(role="builder", run_id="execution-1", attempt=1, status="response",
                   response_complete=True, start_event_sha256="c" * 64,
                   request=dict(artifact_sha256="d" * 64))
    payload.update(changes)
    return dict(kind="model-transport-finished", event_sha256="f" * 64, payload=payload)


class ControllerPhaseCaptureTests(unittest.TestCase):
    def test_complete_fixture_chain_retains_unknown_real_proof(self):
        c = capture()
        c.start("execution-1", "a" * 64, 1)
        c.built()
        c.candidate("1" * 40)
        c.transport([transport()])
        c.verifying()
        c.verified()
        result = c.project()
        self.assertEqual([p["observed_completed_ns"] for p in result["phases"]["phases"]],
                         [10, 15])
        self.assertEqual(result["candidate_commit"], "1" * 40)
        self.assertEqual(result["transport"]["request_artifact_sha256"], "d" * 64)
        self.assertIsNone(result["transport"]["physical_send_id"])
        for name in ("physical_send_proven", "native_cleanup_proven", "complete_coverage",
                     "billing_final", "production_qualification"):
            self.assertFalse(result[name])
        self.assertFalse(result["human_joins"]["executions"][0]["receipt_verified_by_caller"])

    def test_partial_build_is_open_and_no_observation_is_unknown(self):
        c = capture()
        c.start("execution-1", "a" * 64, 1)
        result = c.project()
        self.assertTrue(result["phases"]["phases"][0]["open_interval"])
        self.assertEqual(result["candidate_status"], "unknown")
        self.assertEqual(result["transport_status"], "unknown")

    def test_missing_transport_does_not_invent_physical_send(self):
        c = capture()
        c.start("execution-1", "a" * 64, 1)
        c.built()
        c.transport([])
        self.assertIsNone(c.project()["transport"])

    def test_duplicate_and_out_of_order_events_are_refused(self):
        c = capture()
        with self.assertRaises(MetricsError):
            c.verified()
        c.start("execution-1", "a" * 64, 1)
        with self.assertRaises(MetricsError):
            c.start("execution-1", "a" * 64, 1)
        c.built()
        with self.assertRaises(MetricsError):
            c.built()
        with self.assertRaises(MetricsError):
            c.transport([transport(), transport()])

    def test_bad_initial_identity_consumes_capture_without_retry(self):
        for args in (("other", "a" * 64, 1), ("execution-1", "c" * 64, 1),
                     ("execution-1", "a" * 64, 2)):
            c = capture()
            with self.assertRaises(MetricsError):
                c.start(*args)
            with self.assertRaisesRegex(MetricsError, "consumed"):
                c.start("execution-1", "a" * 64, 1)

    def test_clock_regression_and_mixed_transport_are_refused(self):
        c = capture(ticks=(20, 10))
        c.start("execution-1", "a" * 64, 1)
        with self.assertRaises(MetricsError):
            c.built()
        for changes in (dict(run_id="other"), dict(attempt=2),
                        dict(response_complete=False)):
            c = capture()
            c.start("execution-1", "a" * 64, 1)
            c.built()
            with self.assertRaises(MetricsError):
                c.transport([transport(**changes)])

    def test_receipt_hash_without_authentication_is_refused(self):
        row = dict(schema="factory-metrics-execution-receipt/1", exact_e=IDENTITY.exact_e,
                   campaign_id=IDENTITY.campaign_id, case_id=IDENTITY.case_id,
                   execution_id=IDENTITY.execution_id,
                   attempt_identity_sha256=IDENTITY.attempt_identity_sha256)
        raw = json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
        identity = replace(IDENTITY, receipt_sha256=sha256(raw).hexdigest())
        c = capture(identity)
        c.start("execution-1", "a" * 64, 1)
        with self.assertRaisesRegex(MetricsError, "authenticat"):
            c.project(receipts=(raw,), authenticate_receipt=lambda *_: False)
        event = dict(event_id="event-1", actor_id="operator-1",
                     occurred_at="2026-01-01T10:00:00+00:00",
                     campaign_id=identity.campaign_id, exact_e=identity.exact_e,
                     case_ids=[identity.case_id], execution_ids=[identity.execution_id],
                     action="preparation", evidence_sha256s=[identity.receipt_sha256],
                     supersedes_event_id=None)
        humans = encode_human_event(event, sequence=1, previous_event_sha256=None)
        result = c.project(human_raw=humans, human_source_sha256=sha256(humans).hexdigest(),
                           receipts=(raw,), authenticate_receipt=lambda data, ref:
                           data == raw and ref.receipt_sha256 == sha256(raw).hexdigest())
        self.assertEqual(result["human_joins"]["observed_fully_joined_event_count"], 1)
        self.assertFalse(result["physical_send_proven"])

    def test_missing_transport_observation_is_consumed_once(self):
        c = capture()
        c.start("execution-1", "a" * 64, 1)
        c.built()
        c.transport([])
        with self.assertRaisesRegex(MetricsError, "transport-order"):
            c.transport([])

    def test_real_orchestrator_persists_capture_without_send_proof(self):
        from pathlib import Path
        import tempfile
        from lightyear_factory.agents import LocalAgentSet
        from lightyear_factory.benchmark import benchmark_work_order
        from lightyear_factory.contracts import WorkOrder
        from lightyear_factory.ledger import RunLedger
        from lightyear_factory.orchestrator import FactoryOrchestrator

        root = Path(__file__).resolve().parents[1]
        payload = benchmark_work_order("rounding-mode").to_dict()
        payload.pop("content_sha256", None)
        payload["acceptance"]["max_attempts"] = 1
        payload["acceptance"]["baseline_first"] = False
        order = WorkOrder.from_dict(payload)
        identity = replace(IDENTITY, order_sha256=order.content_sha256)
        c = capture(identity)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            seed = directory / "seed"
            path = seed / "factory" / "benchmarks" / "intcalc_candidate.py"
            path.parent.mkdir(parents=True)
            original = (root / "factory" / "benchmarks" / "intcalc_candidate.py").read_text()
            self.assertEqual(original.count('ROUNDING = "down"'), 1)
            path.write_text(original.replace('ROUNDING = "down"', 'ROUNDING = "half-up"'),
                            encoding="utf-8")
            receipt = FactoryOrchestrator(
                seed, directory / "runs", LocalAgentSet(),
                graph_path=root / "knowledge" / "graph.snapshot.json.gz",
                phase_capture=c).run(order, run_id="execution-1")
            self.assertEqual(receipt["attempts"], 1)
            capture_path = directory / "runs" / "execution-1" / "controller-phase-capture.json"
            output = json.loads(capture_path.read_text())
            self.assertEqual(output["state"], "verified")
            self.assertEqual(output["phases"]["observed_events"], 4)
            self.assertFalse(output["physical_send_proven"])
            self.assertEqual(output["transport_status"], "unknown")
            ledger = RunLedger(capture_path.with_name("events.jsonl"))
            self.assertTrue(ledger.verify())
            records = [row for row in ledger.events
                       if row["kind"] == "controller_phase_capture"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["payload"]["content_sha256"], output["content_sha256"])

    def test_binding_is_read_only(self):
        c = capture()
        with self.assertRaises(AttributeError):
            c.identity = replace(IDENTITY, execution_id="other")
