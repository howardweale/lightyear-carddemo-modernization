"""Disposable human-event data only; no human signatures or coverage claims."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lightyear_factory.human_metrics import collect_human_events, encode_human_event
from lightyear_factory.journal_metrics import MetricsError
from tools.report_attempt_metrics import render_inventory

E = "b" * 40
CASES = [f"case-{number:02}" for number in range(19)]


def fields(identity="event-1", **changes):
    row = dict(event_id=identity, actor_id="operator-1", occurred_at="2026-01-01T10:00:00+00:00",
               campaign_id="campaign-1", exact_e=E, case_ids=CASES[:2], execution_ids=[],
               action="preparation", evidence_sha256s=["c"*64], supersedes_event_id=None)
    row.update(changes)
    return row


def stream(*rows):
    raw, previous = b"", None
    for sequence, row in enumerate(rows, 1):
        line = encode_human_event(row, sequence=sequence, previous_event_sha256=previous)
        raw += line
        previous = json.loads(line)["content_sha256"]
    return raw


def collect(raw, **changes):
    args = dict(source_sha256=sha256(raw).hexdigest(), exact_e=E,
                campaign_id="campaign-1", case_ids=CASES)
    args.update(changes)
    return collect_human_events(raw, **args)


class HumanMetricsTests(unittest.TestCase):
    def test_shared_event_counts_once_globally(self):
        result = collect(stream(fields()))
        self.assertEqual(result["observed_event_count"], 1)
        self.assertEqual([r["observed_event_count"] for r in result["cases"][:3]], [1, 1, 0])
        self.assertIsNone(result["actual_intervention_count"])
        self.assertFalse(result["coverage_attested"])

    def test_empty_stream_is_not_zero_actual_interventions(self):
        result = collect(b"")
        self.assertEqual(result["observed_event_count"], 0)
        self.assertEqual(len(result["cases"]), 19)
        self.assertIsNone(result["cases"][0]["actual_intervention_count"])

    def test_correction_replaces_contribution_but_preserves_history(self):
        raw = stream(fields(), fields("event-2", supersedes_event_id="event-1",
                                      action="manual-transfer", case_ids=[CASES[2]]))
        result = collect(raw)
        self.assertEqual(result["recorded_rows"], 2)
        self.assertEqual(result["correction_rows"], 1)
        self.assertEqual(result["observed_event_count"], 1)
        self.assertEqual(result["cases"][0]["observed_event_count"], 0)
        self.assertEqual(result["cases"][2]["observed_event_ids"], ["event-2"])
        self.assertEqual(result["effective_events"][0]["root_event_id"], "event-1")
        self.assertEqual(collect(raw), result)

    def test_correction_forks_unknown_ids_and_duplicate_ids_refused(self):
        cases = [
            [fields(), fields()],
            [fields("event-2", supersedes_event_id="missing")],
            [fields(), fields("event-2", supersedes_event_id="event-1"),
             fields("event-3", supersedes_event_id="event-1")],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                with self.assertRaises(MetricsError):
                    collect(stream(*rows))

    def test_cross_campaign_source_and_case_scope_refused(self):
        for row in [fields(campaign_id="other"), fields(exact_e="f"*40),
                    fields(case_ids=["unknown-case"])]:
            with self.subTest(row=row):
                with self.assertRaisesRegex(MetricsError, "cross-scope"):
                    collect(stream(row))

    def test_tamper_truncation_reordering_and_source_drift_refused(self):
        raw = stream(fields(), fields("event-2"))
        with self.assertRaisesRegex(MetricsError, "source-drift"):
            collect(raw, source_sha256="f"*64)
        with self.assertRaisesRegex(MetricsError, "truncated"):
            collect(raw[:-1])
        lines = raw.splitlines(keepends=True)
        with self.assertRaisesRegex(MetricsError, "chain"):
            collect(b"".join(reversed(lines)))
        changed = raw.replace(b"operator-1", b"operator-2")
        with self.assertRaisesRegex(MetricsError, "event-digest"):
            collect(changed)

    def test_emitter_refuses_free_text_private_fields_and_naive_time(self):
        for row in [fields(pin="forbidden"), fields(notes="forbidden"),
                    fields(action="unbounded-free-text"), fields(evidence_sha256s=[]),
                    fields(occurred_at="2026-01-01T10:00:00"), fields(case_ids=[])]:
            with self.subTest(row=row):
                with self.assertRaises(MetricsError):
                    encode_human_event(row, sequence=1, previous_event_sha256=None)

    def test_inventory_includes_observed_human_counts_without_attestation(self):
        raw = stream(fields())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"humans.jsonl").write_bytes(raw)
            inventory = dict(schema="factory-metrics-inventory/1", case_ids=CASES,
                             exact_e=E, journals=[], human_events=dict(
                                 path="humans.jsonl", source_sha256=sha256(raw).hexdigest(),
                                 campaign_id="campaign-1"))
            (root/"inventory.json").write_text(json.dumps(inventory))
            render_inventory(root/"inventory.json", root/"report.json")
            report = json.loads((root/"report.json").read_bytes())
            self.assertEqual(report["human_observations"]["observed_event_count"], 1)
            self.assertIsNone(report["human_interventions"])
            self.assertFalse(report["human_observations"]["coverage_attested"])


if __name__ == "__main__":
    unittest.main()
