"""Synthetic monotonic records for CI only; no native timing evidence."""
from dataclasses import replace
from hashlib import sha256
import json
import unittest

from lightyear_factory.contracts import canonical_hash
from lightyear_factory.journal_metrics import MetricsError
from lightyear_factory.phase_metrics import PhaseBinding, collect_phase_metrics


class PhaseMetricsTests(unittest.TestCase):
    def stream(self, boundaries, change=None):
        events = []
        previous = None
        for sequence, (phase, boundary, tick) in enumerate(boundaries, 1):
            event = dict(schema="factory-monotonic-phase/1", sequence=sequence,
                         previous_sha256=previous, event_id="event-" + str(sequence),
                         exact_e="a" * 40, execution_id="execution-1",
                         attempt_identity_sha256="b" * 64, clock_instance_id="clock-1",
                         phase=phase, boundary=boundary, monotonic_ns=tick)
            if change:
                change(event, sequence)
            event["event_sha256"] = canonical_hash(event)
            previous = event["event_sha256"]
            events.append(event)
        raw = b"".join((json.dumps(e, sort_keys=True, separators=(",", ":")) + "\n").encode()
                       for e in events)
        binding = PhaseBinding("a" * 40, "execution-1", "b" * 64, "clock-1",
                               sha256(raw).hexdigest(), ("build", "verify", "human"))
        return raw, binding

    def test_overlapping_phases_are_not_added_as_elapsed_wall_time(self):
        raw, binding = self.stream([("build", "start", 10), ("verify", "start", 15),
                                    ("build", "end", 30), ("verify", "end", 35)])
        result = collect_phase_metrics(raw, binding)
        self.assertEqual([r["observed_completed_ns"] for r in result["phases"]], [20, 20, 0])
        self.assertIsNone(result["total_elapsed_ns"])
        self.assertFalse(result["cross_phase_sum_permitted"])
        self.assertFalse(result["production_qualification"])
        self.assertFalse(result["receipt_authentication_established"])

    def test_open_and_missing_intervals_stay_unknown(self):
        raw, binding = self.stream([("build", "start", 10)])
        rows = collect_phase_metrics(raw, binding)["phases"]
        self.assertEqual(rows[0]["missing_reason"], "open-interval")
        self.assertEqual(rows[1]["missing_reason"], "no-observations")
        self.assertTrue(all(r["total_phase_ns"] is None for r in rows))
        self.assertTrue(all(not r["complete_coverage"] for r in rows))

    def test_repeated_and_zero_duration_intervals(self):
        raw, binding = self.stream([("build", "start", 10), ("build", "end", 10),
                                    ("build", "start", 20), ("build", "end", 25)])
        row = collect_phase_metrics(raw, binding)["phases"][0]
        self.assertEqual(row["observed_completed_ns"], 5)
        self.assertEqual(row["observed_interval_count"], 2)

    def test_empty_stream_does_not_claim_zero_actual_duration(self):
        raw, binding = self.stream([])
        result = collect_phase_metrics(raw, binding)
        self.assertEqual(result["observed_events"], 0)
        self.assertIsNone(result["total_elapsed_ns"])
        self.assertTrue(all(row["total_phase_ns"] is None for row in result["phases"]))

    def test_cross_execution_attempt_source_and_clock_refused(self):
        for field, value in (("execution_id", "other"), ("exact_e", "c" * 40),
                             ("attempt_identity_sha256", "d" * 64),
                             ("clock_instance_id", "new-process")):
            raw, binding = self.stream([("build", "start", 1)],
                                       lambda e, _: e.update({field: value}))
            with self.subTest(field=field), self.assertRaises(MetricsError):
                collect_phase_metrics(raw, binding)

    def test_bad_boundary_sequences_and_regressions_refused(self):
        cases = [
            [("build", "end", 1)],
            [("build", "start", 1), ("build", "start", 2)],
            [("build", "start", 2), ("build", "end", 1)],
            [("build", "start", 2), ("verify", "start", 1)],
            [("build", "unknown", 1)], [("unknown", "start", 1)],
        ]
        for boundaries in cases:
            with self.subTest(boundaries=boundaries), self.assertRaises(MetricsError):
                collect_phase_metrics(*self.stream(boundaries))

    def test_tick_type_bounds(self):
        for tick in (True, -1, 1.5, "2", 2**63):
            with self.subTest(tick=tick), self.assertRaises(MetricsError):
                collect_phase_metrics(*self.stream([("build", "start", tick)]))

    def test_drift_truncation_and_duplicate_identity_refused(self):
        raw, binding = self.stream([("build", "start", 1)])
        with self.assertRaises(MetricsError):
            collect_phase_metrics(raw + b" ", binding)
        trimmed = raw.rstrip(b"\n")
        with self.assertRaises(MetricsError):
            collect_phase_metrics(trimmed, replace(binding, source_sha256=sha256(trimmed).hexdigest()))
        raw, binding = self.stream([("build", "start", 1), ("build", "end", 2)],
                                   lambda e, _: e.update(event_id="duplicate"))
        with self.assertRaises(MetricsError):
            collect_phase_metrics(raw, binding)

    def test_unexpected_fields_and_duplicate_json_keys_refused(self):
        raw, binding = self.stream([("build", "start", 1)],
                                   lambda e, _: e.update(wall_duration=99))
        with self.assertRaises(MetricsError):
            collect_phase_metrics(raw, binding)
        raw = b'{"schema":"x","schema":"y"}\n'
        with self.assertRaises(MetricsError):
            collect_phase_metrics(raw, replace(binding, source_sha256=sha256(raw).hexdigest()))

    def test_chain_hash_and_sequence_are_not_optional(self):
        for field, replacement in (("previous_sha256", "0" * 64), ("sequence", True)):
            raw, binding = self.stream([("build", "start", 1)],
                                       lambda e, _: e.update({field: replacement}))
            with self.subTest(field=field), self.assertRaises(MetricsError):
                collect_phase_metrics(raw, binding)
        raw, binding = self.stream([("build", "start", 1)])
        event = json.loads(raw)
        event["event_sha256"] = "0" * 64
        raw = (json.dumps(event) + "\n").encode()
        with self.assertRaises(MetricsError):
            collect_phase_metrics(raw, replace(binding, source_sha256=sha256(raw).hexdigest()))


if __name__ == "__main__":
    unittest.main()
