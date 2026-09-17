"""MS74: real engine admission, durable archive retries, and read-only history."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_data.contracts import seal
from lightyear_workflow.cloudbank import observe
from lightyear_workflow.convergence import INDEX_RELATIVE, read_convergence
from lightyear_workflow.execution import execute, read_execution
from lightyear_workflow.history import HISTORY_PATH, record_finished, read_runs, read_selected
from lightyear_workflow.run_index import Retention, RunIndex
from lightyear_workflow.run_store import RunStore
from tests import test_cloudbank_workflow_execution as execution_tests


class WorkflowHistoryTests(unittest.TestCase):
    setUp = execution_tests.CloudBankWorkflowTests.setUp
    policy = execution_tests.CloudBankWorkflowTests.policy

    def run_engine(self, **kwargs):
        with patch("lightyear_workflow.execution.run_worker",
                   side_effect=lambda root, action, *_: observe(root, action["service"], action["lane"])):
            return execute(self.root, self.directory, **kwargs)

    def index(self):
        return RunIndex(self.root / INDEX_RELATIVE, read_only=True)

    def test_pause_has_no_history_then_terminal_resume_is_recorded_once(self):
        self.run_engine(max_steps=2)
        self.assertFalse((self.root / INDEX_RELATIVE).exists())
        self.assertFalse((self.root / HISTORY_PATH).exists())
        result = self.run_engine()
        self.assertEqual(result["halt_reason"], "human-decision-required")
        archives = list((self.root / HISTORY_PATH).glob("*.json.gz"))
        self.assertEqual(len(archives), 1)
        archive = json.loads(gzip.decompress(archives[0].read_bytes()))
        self.assertEqual(archive["events"], RunStore(self.directory, read_only=True).events())
        self.assertEqual(archive["estate"], "cloudbank")
        row = self.index().lookup(archive["run_id"])
        self.assertEqual((row["actions_completed"], row["rounds"], row["awaiting_human"]), (19, 6, 1))
        self.assertEqual(row["terminal"], result["halt_reason"])
        self.assertEqual(self.run_engine(), result)
        self.assertEqual(self.index().storage()["runs"], 1)
        before = (self.root / INDEX_RELATIVE).read_bytes()
        self.assertEqual(sum(w["actions_completed"] for w in read_convergence(self.root)["weeks"]), 19)
        read_execution(self.root, self.directory)
        self.assertEqual((self.root / INDEX_RELATIVE).read_bytes(), before)

    def test_archive_published_before_index_failure_is_reused_on_retry(self):
        self.policy(max_actions=1)
        with patch.object(RunIndex, "record", side_effect=OSError("disk unavailable")):
            with self.assertRaisesRegex(OSError, "disk unavailable"):
                self.run_engine()
        archive = next((self.root / HISTORY_PATH).glob("*.json.gz"))
        before = archive.read_bytes()
        self.assertEqual(self.run_engine()["halt_reason"], "budget")
        self.assertEqual(before, archive.read_bytes())
        self.assertEqual(self.index().storage()["runs"], 1)

    def test_pruning_is_not_undone_by_repeating_a_finished_run(self):
        self.policy(max_actions=1)
        self.run_engine()
        index = RunIndex(self.root / INDEX_RELATIVE)
        index.prune(self.root / HISTORY_PATH, Retention(), datetime.now(timezone.utc) + timedelta(days=500))
        self.run_engine()
        self.assertEqual(list((self.root / HISTORY_PATH).glob("*.json.gz")), [])
        self.assertEqual(index.storage()["pruned_runs"], 1)

    def test_changed_archive_is_never_replaced(self):
        self.policy(max_actions=1)
        self.run_engine()
        archive = next((self.root / HISTORY_PATH).glob("*.json.gz"))
        archive.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "archive differs"):
            self.run_engine()
        self.assertEqual(archive.read_bytes(), b"changed")

    def test_resealed_invented_completion_cannot_enter_history(self):
        self.run_engine(max_steps=1)
        events = RunStore(self.directory, read_only=True).events()
        events[-1]["type"] = "halted"
        events[-1]["payload"] = {"reason": "completed"}
        events[-1] = seal(events[-1])
        with self.assertRaisesRegex(ValueError, "Unsupported convergence"):
            record_finished(self.root, events, self.root / HISTORY_PATH)
        self.assertFalse((self.root / INDEX_RELATIVE).exists())

    def test_changed_inputs_and_paused_journals_cannot_enter_history(self):
        self.run_engine(max_steps=1)
        events = RunStore(self.directory, read_only=True).events()
        with self.assertRaisesRegex(ValueError, "terminal"):
            record_finished(self.root, events, self.root / HISTORY_PATH)
        self.policy(max_actions=2)
        with self.assertRaisesRegex(ValueError, "inputs, implementation or policy changed"):
            self.run_engine()
        self.assertFalse((self.root / INDEX_RELATIVE).exists())

    def test_two_runs_have_distinct_ids_and_customer_archive_location(self):
        self.policy(max_actions=1)
        journals = self.root / "work/customer-archives"
        self.run_engine(history_dir=journals)
        self.directory = self.root / "work/workflow/another-run"
        self.run_engine(history_dir=journals)
        self.assertEqual(len(list(journals.glob("*.json.gz"))), 2)
        self.assertEqual(self.index().storage()["runs"], 2)
        with closing(self.index()._db()) as db:
            self.assertEqual({row[0] for row in db.execute("SELECT terminal FROM runs")}, {"budget"})

    def test_archive_scope_is_checked_before_execution(self):
        with self.assertRaisesRegex(ValueError, "work directory"):
            self.run_engine(history_dir=self.root / "outside-work")
        self.assertFalse(self.directory.exists())

    def test_selected_run_replays_and_is_bound_to_estate_without_writes(self):
        self.policy(max_actions=1)
        self.run_engine()
        rows = read_runs(self.root)["runs"]
        self.assertEqual(len(rows), 1)
        self.assertNotIn("journal_path", rows[0])
        before = (self.root / INDEX_RELATIVE).read_bytes()
        run_id = rows[0]["run_id"]
        selected = read_selected(self.root, "cloudbank", run_id)
        self.assertEqual(selected["status"], "halted")
        self.assertEqual(selected["run_id"], run_id)
        self.assertEqual(selected["events"], RunStore(self.directory, read_only=True).events())
        self.assertEqual(read_selected(self.root, "carddemo", run_id)["status"], "unavailable")
        self.assertEqual(read_selected(self.root, "cloudbank", "missing")["status"], "unavailable")
        self.assertEqual(read_runs(self.root, "carddemo")["runs"], [])
        self.assertEqual(before, (self.root / INDEX_RELATIVE).read_bytes())

    def test_list_survives_pruning_and_corrupt_archive_clears_selected_details(self):
        self.policy(max_actions=1)
        self.run_engine()
        row = read_runs(self.root)["runs"][0]
        path = next((self.root / HISTORY_PATH).glob("*.json.gz"))
        original = path.read_bytes()
        path.write_bytes(b"corrupt")
        self.assertEqual(read_selected(self.root, "cloudbank", row["run_id"])["status"], "invalid")
        with patch.object(gzip, "open", side_effect=AssertionError("List must not read journals")):
            self.assertEqual(len(read_runs(self.root)["runs"]), 1)
        path.write_bytes(original)
        RunIndex(self.root / INDEX_RELATIVE).prune(self.root / HISTORY_PATH, Retention(), datetime.now(timezone.utc) + timedelta(days=500))
        self.assertIn("pruned", read_selected(self.root, "cloudbank", row["run_id"])["reason"])

    def test_absent_run_list_does_not_create_index(self):
        self.assertEqual(read_runs(self.root)["runs"], [])
        self.assertFalse((self.root / INDEX_RELATIVE).exists())
