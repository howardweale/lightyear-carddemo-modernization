from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextlib import closing
import gzip
import json
from pathlib import Path
import tempfile
import sqlite3
from unittest.mock import patch

from lightyear_data.contracts import seal
from lightyear_workflow.convergence import read_convergence
import unittest

from lightyear_workflow.blast_radius import blast_radius, signature_blocker
from lightyear_workflow.run_index import RunIndex, Retention, summarise

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "control-tower" / "cloudbank-execution.example.json"


def register(files: int = 12, count: int = 14) -> list[dict]:
    return [{"file": f"acct-{i:03d}.cbl", "construct": "decimal canonical text",
             "reason": "exact-decimal", "comparison_count": count}
            for i in range(files)]


class BlastRadiusTests(unittest.TestCase):
    def test_measures_suppressed_comparisons_and_files(self):
        result = blast_radius(r"decimal", register(files=12, count=14))
        self.assertEqual(result["suppressed_comparisons"], 168)
        self.assertEqual(result["affected_files"], 12)
        self.assertEqual(result["suppression_estimate"], "measured")

    def test_an_unmeasured_radius_is_not_reported_as_a_zero(self):
        """A zero and an unknown are different facts and must not share a value."""
        for radius in (blast_radius(r"decimal(", register()),
                       blast_radius(r"decimal", [])):
            self.assertEqual(radius["suppressed_comparisons"], 0)
            self.assertNotEqual(radius["suppression_estimate"], "measured")
            self.assertIsNotNone(signature_blocker(radius))

    def test_signature_is_refused_until_the_radius_is_measured(self):
        self.assertIsNone(signature_blocker(blast_radius(r"decimal", register())))
        self.assertIn("cannot be signed",
                      signature_blocker({"suppression_estimate": "not-assessed"}))

    def test_wide_reach_is_flagged_but_does_not_block(self):
        wide = blast_radius(r"decimal", register(files=80))
        self.assertTrue(wide["wide_reach"])
        self.assertIsNone(signature_blocker(wide))


class SummariseTests(unittest.TestCase):
    def setUp(self):
        self.events = json.loads(JOURNAL.read_text(encoding="utf-8"))["events"]

    def test_summarises_the_committed_journal(self):
        row = summarise("r-0001", "cloudbank", "estate", self.events)
        self.assertEqual(row["actions_completed"], 19)
        self.assertEqual(row["rounds"], 6)
        self.assertEqual(row["awaiting_human"], 1)
        self.assertEqual(row["terminal"], "human-decision-required")

    def test_no_model_call_is_recorded_in_the_verdict_path(self):
        self.assertEqual(summarise("r", "e", "w", self.events)["model_calls"], 0)


class RunIndexTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.journals = self.tmp / "journals"
        self.journals.mkdir()
        self.index = RunIndex(self.tmp / "index.sqlite3")
        self.events = json.loads(JOURNAL.read_text(encoding="utf-8"))["events"]

    def _record(self, count: int, weeks_back: int = 8) -> None:
        start = datetime.now(timezone.utc) - timedelta(weeks=weeks_back)
        for i in range(count):
            events = json.loads(json.dumps(self.events))
            original = datetime.fromisoformat(events[0]["at"])
            shift = start + timedelta(days=i * 1.75) - original
            previous = None
            for event in events:
                event["at"] = (datetime.fromisoformat(event["at"]) + shift).isoformat()
                event["previous_sha256"] = previous
                event.update(seal(event))
                previous = event["content_sha256"]
            path = self.journals / f"r-{i:04d}.json.gz"
            path.write_bytes(gzip.compress(json.dumps(events).encode()))
            self.index.record(f"r-{i:04d}", "cloudbank", "estate", events, path)

    def test_convergence_survives_its_journals_being_pruned(self):
        """The whole point of the split: the trend outlives the evidence."""
        self._record(24)
        weeks_before = self.index.convergence("cloudbank")
        pruned = self.index.prune(self.journals, Retention(journal_days=28))
        self.assertGreater(pruned["pruned"], 0)
        with patch("gzip.open", side_effect=AssertionError("Convergence opened a journal")), patch.object(Path, "read_bytes", side_effect=AssertionError("Convergence read a file")):
            self.assertEqual(self.index.convergence("cloudbank"), weeks_before)

    def test_pruning_never_removes_an_index_row(self):
        self._record(24)
        before = self.index.storage()["runs"]
        self.index.prune(self.journals, Retention(journal_days=28))
        self.assertEqual(self.index.storage()["runs"], before)

    def test_a_pruned_journal_is_a_recorded_gap_not_a_silent_one(self):
        self._record(24)
        self.index.prune(self.journals, Retention(journal_days=28))
        self.assertGreater(self.index.storage()["pruned_runs"], 0)

    def test_a_dry_run_removes_nothing(self):
        self._record(24)
        held = self.index.storage()["journal_bytes"]
        report = self.index.prune(self.journals, Retention(journal_days=28), dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertEqual(self.index.storage()["journal_bytes"], held)

    def test_every_index_row_is_derivable_from_its_journal(self):
        """A corrupt index is recoverable while the journals survive."""
        self._record(6)
        with closing(self.index._db()) as db, db:
            expected = [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY run_id")]
        (self.tmp / "index.sqlite3").unlink()
        rebuilt = RunIndex(self.tmp / "index.sqlite3")
        for path in sorted(self.journals.glob("*.json.gz")):
            events = json.loads(gzip.decompress(path.read_bytes()))
            rebuilt.record(path.name.split(".")[0], "cloudbank", "estate", events, path)
        with closing(rebuilt._db()) as db, db:
            actual = [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY run_id")]
        self.assertEqual(actual, expected)


class ReviewRegressionTests(unittest.TestCase):
    setUp = RunIndexTests.setUp
    _record = RunIndexTests._record
    def test_raw_ms70_register_cannot_become_a_measured_zero(self):
        entries = json.loads((ROOT / "factory/idempiere-divergence-audit/stage4-indeterminate-register.json").read_text())["entries"]
        self.assertEqual(len(entries), 1077)
        radius = blast_radius("decimal", entries)
        self.assertEqual(radius["suppression_estimate"], "invalid-register")
        self.assertIsNotNone(signature_blocker(radius))

    def test_invalid_counts_and_partial_registers_remain_unmeasured(self):
        for count in (-1, 0, True, "14", None):
            records = register()
            records[-1]["comparison_count"] = count
            radius = blast_radius("decimal", records)
            self.assertEqual(radius["suppression_estimate"], "invalid-register")
            self.assertIsNotNone(signature_blocker(radius))
        for pattern in (None, "", " "):
            self.assertEqual(blast_radius(pattern, register())["suppression_estimate"], "invalid-pattern")

    def test_valid_nonmatching_register_is_a_measured_zero(self):
        radius = blast_radius("unmatched", register())
        self.assertEqual(radius["suppressed_comparisons"], 0)
        self.assertEqual(radius["suppression_estimate"], "measured")
        self.assertIsNone(signature_blocker(radius))

    def test_counts_are_explicitly_action_events_not_resolved_findings(self):
        self._record(2)
        weeks = self.index.convergence("cloudbank")
        self.assertEqual(sum(w["actions_completed"] for w in weeks), 38)
        self.assertTrue(all("resolved" not in w for w in weeks))

    def test_path_traversal_and_absolute_run_ids_are_refused(self):
        sentinel = self.tmp / "sentinel.json.gz"
        sentinel.write_bytes(b"untouched")
        for run_id in ("../sentinel", "..\\sentinel", str(sentinel), "a/b", "a:b", ""):
            with self.assertRaises(ValueError):
                self.index.record(run_id, "cloudbank", "estate", self.events, sentinel)
        self.assertEqual(sentinel.read_bytes(), b"untouched")
        self.assertEqual(self.index.storage()["runs"], 0)

    def test_prune_refuses_corrupt_index_run_id(self):
        self._record(1)
        sentinel = self.tmp / "sentinel.json.gz"
        sentinel.write_bytes(b"untouched")
        with closing(self.index._db()) as db, db:
            db.execute("UPDATE runs SET run_id='../sentinel'")
        with self.assertRaises(ValueError):
            self.index.prune(self.journals, Retention(journal_days=1))
        self.assertEqual(sentinel.read_bytes(), b"untouched")
        self.assertTrue((self.journals / "r-0000.json.gz").exists())

    def test_wrong_retention_root_cannot_delete_same_named_file(self):
        self._record(1)
        other = self.tmp / "other"
        other.mkdir()
        copy = other / "r-0000.json.gz"
        copy.write_bytes((self.journals / copy.name).read_bytes())
        with self.assertRaisesRegex(ValueError, "recorded retention directory"):
            self.index.prune(other, Retention(journal_days=1))
        self.assertTrue(copy.exists())
        self.assertEqual(self.index.storage()["pruned_runs"], 0)

    def test_changed_or_missing_journal_is_not_reported_as_pruned(self):
        self._record(1)
        journal = self.journals / "r-0000.json.gz"
        journal.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.index.prune(self.journals, Retention(journal_days=1))
        self.assertTrue(journal.exists())
        journal.unlink()
        with self.assertRaises(FileNotFoundError):
            self.index.prune(self.journals, Retention(journal_days=1))
        self.assertEqual(self.index.storage()["pruned_runs"], 0)

    def test_retention_uses_completion_time_and_records_actual_policy_time(self):
        self._record(1)
        with closing(self.index._db()) as db, db:
            before = dict(db.execute("SELECT * FROM runs").fetchone())
        ended = datetime.fromisoformat(before["ended_at"])
        policy = Retention(journal_days=28)
        self.assertEqual(self.index.prune(self.journals, policy, now=ended + timedelta(days=27))["pruned"], 0)
        now = ended + timedelta(days=29)
        self.index.prune(self.journals, policy, now=now)
        with closing(self.index._db()) as db, db:
            after = dict(db.execute("SELECT * FROM runs").fetchone())
        self.assertEqual(after["journal_sha256"], before["journal_sha256"])
        self.assertEqual(after["journal_pruned_at"], now.isoformat())

    def test_run_identity_cannot_be_replaced_or_double_counted(self):
        self._record(1)
        path = self.journals / "r-0000.json.gz"
        events = json.loads(gzip.decompress(path.read_bytes()))
        self.index.record("r-0000", "cloudbank", "estate", events, path)
        self.assertEqual(self.index.storage()["runs"], 1)
        with self.assertRaisesRegex(ValueError, "different journal"):
            self.index.record("r-0000", "other-estate", "estate", events, path)
        self.assertEqual(self.index.storage()["runs"], 1)

    def test_tampered_or_unfinished_events_are_refused(self):
        events = json.loads(json.dumps(self.events))
        events[1]["payload"]["untrusted"] = True
        for candidate in (events, self.events[:-1], []):
            with self.assertRaises(ValueError):
                summarise("r", "cloudbank", "estate", candidate)

    def test_projection_never_initializes_missing_empty_or_corrupt_index(self):
        root = self.tmp / "project"
        root.mkdir()
        self.assertEqual(read_convergence(root)["reason"], "no-runs-recorded")
        self.assertEqual(list(root.iterdir()), [])
        path = root / "control-tower/run-index.sqlite3"
        path.parent.mkdir()
        for data in (b"", b"not sqlite"):
            path.write_bytes(data)
            self.assertEqual(read_convergence(root)["reason"], "invalid-run-index")
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual([p.name for p in path.parent.iterdir()], [path.name])

    def test_read_only_projection_survives_pruning_without_writes(self):
        self._record(2)
        self.index.prune(self.journals, Retention(journal_days=1))
        before = self.index.path.read_bytes()
        with patch("lightyear_workflow.convergence.INDEX_RELATIVE", Path("index.sqlite3")):
            value = read_convergence(self.tmp)
        self.assertEqual(value["metric_unit"], "action-events")
        self.assertEqual(sum(w["actions_completed"] for w in value["weeks"]), 38)
        self.assertEqual(self.index.path.read_bytes(), before)
        reader = RunIndex(self.index.path, read_only=True)
        with self.assertRaises(ValueError):
            reader.prune(self.journals, Retention())
        with closing(reader._db()) as db, db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM runs")

    def test_invalid_retention_policies_cannot_remove_index_rows(self):
        self.assertEqual(Retention().journal_days, 396)
        for days in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                Retention(journal_days=days)
        with self.assertRaises(ValueError):
            Retention(index_forever=False)

    def test_handler_reads_history_before_refreshing_live_graph(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from lightyear_knowledge_graph.explorer import ExplorerRequestHandler
        handler = object.__new__(ExplorerRequestHandler)
        handler.server = SimpleNamespace(project_root=self.tmp, refresh_live_projections=Mock(side_effect=AssertionError("Graph refresh")))
        handler._json = Mock()
        handler._api("/api/workflow/convergence", {"estate": ["cloudbank"], "weeks": ["12"]})
        self.assertEqual(handler._json.call_args.args[0]["reason"], "no-runs-recorded")
        handler.server.refresh_live_projections.assert_not_called()
        with self.assertRaises(ValueError):
            handler._api("/api/workflow/convergence", {"weeks": ["invalid"]})


if __name__ == "__main__":
    unittest.main()
