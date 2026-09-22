"""Agent transport must not change evidence meaning or decision authority."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Event
import unittest
from unittest.mock import patch
import uuid

from lightyear_agent.cli import exit_code
from lightyear_agent.service import Workflow, initialize
from lightyear_control_tower.decisions import DecisionService, initialize_authority
from lightyear_data.contracts import seal
from lightyear_workflow.cloudbank_extensions import ENTRY_ID, WORKLOAD
from lightyear_workflow.history import read_selected
from lightyear_workflow.run_store import RunStore
from lightyear_workflow.execution import WorkerFailure, execute, replay, run_worker
from tests.agent_support import fixture, finish_local


class AgentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root, self.project = fixture(self)
        self.dispatched = []
        self.workflow = Workflow(self.project, dispatcher=self.dispatched.append)

    def start(self, request_id=None):
        plan = self.workflow.invoke("plan")
        self.assertTrue(plan["ok"], plan)
        result = self.workflow.invoke("start", plan_sha256=plan["plan_sha256"], request_id=request_id or str(uuid.uuid4()))
        self.assertTrue(result["ok"], result)
        return result["run_id"], plan

    def test_external_project_discovery_and_plan_do_not_execute_or_write(self):
        capabilities = self.workflow.invoke("capabilities")
        plan = self.workflow.invoke("plan")
        self.assertTrue(capabilities["ok"])
        self.assertTrue(plan["ok"], plan)
        self.assertFalse(capabilities["cloud_execution"])
        self.assertEqual(0, plan["incremental_cloud_cost_usd"])
        self.assertFalse(self.workflow.directory.exists())
        self.assertEqual([], self.dispatched)
        self.assertNotEqual(self.root, self.project.parent)

    @unittest.skipUnless(os.name == "nt", "Windows host job containment")
    def test_windows_start_requires_independent_worker_before_accepting_run(self):
        workflow = Workflow(self.project)
        plan = workflow.invoke("plan")
        result = workflow.invoke("start", plan_sha256=plan["plan_sha256"], request_id=str(uuid.uuid4()))
        self.assertEqual("worker-required", result["error"]["code"])
        with closing(workflow._db()) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def test_concurrent_duplicate_start_dispatches_once_and_conflicts_fail(self):
        plan = self.workflow.invoke("plan")["plan_sha256"]
        request = str(uuid.uuid4())
        def start(_):
            return Workflow(self.project, dispatcher=self.dispatched.append).invoke("start", plan_sha256=plan, request_id=request)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(start, range(4)))
        self.assertTrue(all(r["ok"] for r in results), results)
        self.assertEqual(1, sum(r["new_dispatch"] for r in results))
        self.assertEqual(1, len(set(r["run_id"] for r in results)))
        self.assertEqual(1, len(self.dispatched))
        conflict = self.workflow.invoke("start", plan_sha256="0" * 64, request_id=request)
        self.assertEqual("request-conflict", conflict["error"]["code"])

    def test_stale_plan_and_changed_configuration_do_not_dispatch(self):
        plan = self.workflow.invoke("plan")["plan_sha256"]
        path = self.root / "control-tower/execution-policy.json"
        policy = json.loads(path.read_text()); policy["max_actions"] -= 1
        path.write_text(json.dumps(policy))
        result = self.workflow.invoke("start", plan_sha256=plan, request_id=str(uuid.uuid4()))
        self.assertEqual("plan-changed", result["error"]["code"])
        config = json.loads(self.project.read_text()); config["project_id"] = "switched-project"
        self.project.write_text(json.dumps(config))
        self.assertEqual("configuration-changed", self.workflow.invoke("capabilities")["error"]["code"])
        self.assertFalse(self.dispatched)

    def test_execution_package_must_match_bound_checkout(self):
        path = self.root / "src/lightyear_agent/__init__.py"
        path.write_text(path.read_text() + "\n# Different implementation\n")
        result = self.workflow.invoke("plan")
        self.assertEqual("implementation-mismatch", result["error"]["code"])

    def test_full_run_halts_for_human_and_tower_reads_identical_journal(self):
        run_id, _ = self.start()
        finish_local(self.workflow, run_id)
        result = self.workflow.invoke("verify", run_id=run_id)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["verified"])
        self.assertFalse(result["workflow_completed"])
        self.assertEqual("human-decision-required", result["status"])
        self.assertEqual(19, result["summary"]["actions_executed"])
        self.assertEqual(0, result["boundary"]["ledger_entries_applied"])
        self.assertEqual(3, exit_code(result))
        tower = read_selected(self.root, "cloudbank", result["tower"]["run_id"])
        self.assertEqual(result["journal_head_sha256"], tower["journal_head_sha256"])
        self.assertEqual(result["summary"], tower["summary"])
        exported = self.workflow.invoke("export", run_id=run_id)
        self.assertTrue(exported["ok"], exported)
        raw = Path(exported["path"]).read_bytes()
        self.assertEqual(exported["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(exported, self.workflow.invoke("export", run_id=run_id))
        self.assertFalse(json.loads(raw)["independent_signature"])
        self.assertFalse(self.workflow.invoke("resume", run_id=run_id)["new_dispatch"])
        before = self.workflow._verified(run_id)[1]
        cancelled = self.workflow.invoke("cancel", run_id=run_id)
        self.assertEqual("human-decision-required", cancelled["status"])
        self.assertFalse(cancelled["new_request"])
        self.assertIsNone(cancelled["cancellation_requested_at"])
        self.assertEqual(before, self.workflow._verified(run_id)[1])

    def test_queued_cancel_is_terminal_idempotent_and_never_dispatches_actions(self):
        request_id = str(uuid.uuid4())
        run_id, plan = self.start(request_id)
        # Older project databases are readable; cancellation adds its own table
        # on the first write without replacing or migrating the run records.
        with closing(self.workflow._db(write=True)) as db, db:
            db.execute("DROP TABLE cancellation_requests")
        self.assertIsNone(self.workflow.invoke("status", run_id=run_id)["cancellation_requested_at"])
        with closing(self.workflow._db()) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='cancellation_requests'").fetchone())
        with patch("lightyear_workflow.execution.run_worker") as worker:
            cancelled = self.workflow.invoke("cancel", run_id=run_id)
            worker.assert_not_called()
        self.assertTrue(cancelled["ok"], cancelled)
        self.assertEqual("cancelled", cancelled["status"])
        self.assertTrue(cancelled["terminal"])
        self.assertTrue(cancelled["new_request"])
        self.assertEqual(0, cancelled["summary"]["actions_executed"])
        self.assertEqual(5, exit_code(cancelled))
        before = self.workflow._verified(run_id)[1]
        self.assertEqual(["started", "halted"], [e["type"] for e in before])
        for operation in ("cancel", "resume", "verify"):
            result = self.workflow.invoke(operation, run_id=run_id)
            self.assertEqual("cancelled", result["status"], result)
            self.assertEqual(before, self.workflow._verified(run_id)[1])
        self.assertFalse(self.workflow.invoke("verify", run_id=run_id)["workflow_completed"])
        duplicate = self.workflow.invoke("start", plan_sha256=plan["plan_sha256"], request_id=request_id)
        self.assertFalse(duplicate["new_dispatch"])
        self.assertEqual([run_id], self.dispatched)
        export = self.workflow.invoke("export", run_id=run_id)
        self.assertTrue(export["ok"], export)
        self.assertEqual("cancelled", json.loads(Path(export["path"]).read_text())["halt_reason"])
        tower = read_selected(self.root, "cloudbank", cancelled["tower"]["run_id"])
        self.assertEqual("cancelled", tower["halt_reason"])
        self.assertFalse(tower["summary"]["converged_within_scope"])

    def test_active_cancel_survives_reconnect_and_discards_uncommitted_result(self):
        from lightyear_workflow.cloudbank import observe
        run_id, _ = self.start()
        entered, release = Event(), Event()
        def worker(root, action, *args, **kwargs):
            entered.set()
            if not release.wait(15):
                raise RuntimeError("Test did not release active worker")
            return observe(root, action["service"], action["lane"])
        with patch("lightyear_workflow.execution.run_worker", side_effect=worker), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.workflow.work, run_id)
            try:
                self.assertTrue(entered.wait(15))
                reconnect = Workflow(self.project, dispatcher=self.dispatched.append)
                request = reconnect.invoke("cancel", run_id=run_id)
                self.assertEqual("cancel-requested", request["status"], request)
                self.assertFalse(request["terminal"])
                self.assertEqual(4, exit_code(request))
                repeated = reconnect.invoke("cancel", run_id=run_id)
                self.assertFalse(repeated["new_request"])
                self.assertEqual(request["cancellation_requested_at"], repeated["cancellation_requested_at"])
                self.assertFalse(reconnect.invoke("resume", run_id=run_id)["new_dispatch"])
            finally:
                release.set()
            future.result(timeout=15)
        result = self.workflow.invoke("verify", run_id=run_id)
        self.assertEqual("cancelled", result["status"], result)
        self.assertFalse(result["workflow_completed"])
        events = self.workflow._verified(run_id)[1]
        self.assertEqual(1, sum(e["type"] == "attempt" for e in events))
        self.assertFalse(any(e["type"] == "result" for e in events))
        self.assertEqual("cancelled", events[-2]["payload"]["reason"])
        self.assertEqual([run_id], self.dispatched)

    def test_cancelled_worker_process_is_terminated_and_reaped(self):
        entered, cancel = Event(), Event()
        processes = []
        popen = subprocess.Popen
        def blocking_worker(command, **kwargs):
            process = popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
            processes.append(process)
            entered.set()
            return process
        with patch("lightyear_workflow.execution.subprocess.Popen", side_effect=blocking_worker), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_worker, self.root, {"service": "account", "lane": "contract"},
                                 {"max_output_bytes": 65536}, 30, cancel_requested=cancel.is_set)
            try:
                self.assertTrue(entered.wait(10))
                cancel.set()
                with self.assertRaisesRegex(WorkerFailure, "^cancelled$"):
                    future.result(timeout=10)
                self.assertIsNotNone(processes[0].returncode)
                self.assertNotEqual(0, processes[0].returncode)
            finally:
                cancel.set()
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=10)

    def test_resume_settles_retained_cancellation_without_repeating_actions(self):
        from lightyear_workflow.cloudbank import observe
        run_id, _ = self.start()
        journal = self.workflow._run_directory(run_id) / "journal"
        with patch("lightyear_workflow.execution.run_worker", side_effect=lambda root, action, *_: observe(root, action["service"], action["lane"])):
            execute(self.root, journal, max_steps=2)
        before = self.workflow._verified(run_id)[1]
        lease = RunStore(self.workflow._run_directory(run_id) / "lease")
        try:
            self.assertEqual("cancel-requested", self.workflow.invoke("cancel", run_id=run_id)["status"])
        finally:
            lease.close()
        with patch("lightyear_workflow.execution.run_worker") as worker:
            result = Workflow(self.project, dispatcher=self.dispatched.append).invoke("resume", run_id=run_id)
            worker.assert_not_called()
        self.assertEqual("cancelled", result["status"], result)
        self.assertFalse(result["new_dispatch"])
        self.assertEqual(before, self.workflow._verified(run_id)[1][:-1])
        self.assertEqual(2, result["summary"]["actions_executed"])

    def test_cancelled_attempt_cannot_resume_actions_even_without_adapter_callback(self):
        run_id, _ = self.start()
        journal = self.workflow._run_directory(run_id) / "journal"
        append = RunStore.append
        def interrupted(store, kind, payload):
            if kind == "halted":
                raise OSError("Synthetic interruption before cancellation halt")
            return append(store, kind, payload)
        with patch("lightyear_workflow.execution.run_worker", side_effect=WorkerFailure("cancelled")), patch.object(RunStore, "append", interrupted):
            with self.assertRaisesRegex(OSError, "Synthetic interruption"):
                execute(self.root, journal)
        with patch("lightyear_workflow.execution.run_worker") as worker:
            result = execute(self.root, journal)
            worker.assert_not_called()
        self.assertEqual("cancelled", result["halt_reason"])
        events = RunStore(journal, read_only=True).events()
        forged = events[:-1] + [seal({**events[-1], "type": "paused", "payload": {}})]
        with self.assertRaisesRegex(ValueError, "continued after cancellation"):
            replay(self.root, forged)

    def test_broker_lease_contention_does_not_overwrite_cancelling_worker_state(self):
        run_id, _ = self.start()
        self.workflow._set_dispatch(run_id, "queued")
        stop = Event()
        guard = self.workflow._guard
        def checked_guard():
            if stop.is_set():
                raise KeyboardInterrupt
            guard()
        def busy(_):
            stop.set()
            raise ValueError("Another headless engine owns this run")
        with patch.object(self.workflow, "_guard", side_effect=checked_guard), patch.object(self.workflow, "work", side_effect=busy), patch.object(self.workflow, "_set_dispatch") as dispatch, patch("lightyear_agent.service.time.sleep"):
            with self.assertRaises(KeyboardInterrupt):
                self.workflow.serve_worker()
            dispatch.assert_not_called()
        self.assertEqual("queued", self.workflow._row(run_id)["dispatch_state"])

    @unittest.skipUnless(importlib.util.find_spec("cryptography"), "Install .[agent]; mandatory in local-agent CI")
    def test_signed_human_decision_is_consumed_not_created(self):
        authority = self.root / "work/control-tower/test-authority.json"
        credential = initialize_authority(authority, "synthetic-operator", "Synthetic test operator", workload_id=WORKLOAD)
        service = DecisionService(self.root, authority)
        self.addCleanup(service.close)
        token = service.login(credential.read_text().strip())["token"]
        item = service.review(token, ENTRY_ID)
        service.decide(token, {"entry_id": ENTRY_ID, "entry_sha256": item["entry_sha256"],
            "ledger_sha256": item["ledger_sha256"], "previous_decision_sha256": None,
            "outcome": "approved", "reason": "Synthetic test only; not a real customer approval",
            "owner": "Synthetic test owner", "review_after": (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat(),
            "request_id": str(uuid.uuid4())})
        with service.connect() as db:
            before = db.execute("SELECT envelope FROM events ORDER BY sequence").fetchall()
        run_id, _ = self.start()
        finish_local(self.workflow, run_id)
        result = self.workflow.invoke("verify", run_id=run_id)
        self.assertEqual("completed", result["status"], result)
        self.assertEqual(20, result["summary"]["actions_executed"])
        self.assertEqual(1, result["boundary"]["ledger_entries_applied"])
        self.assertEqual(0, exit_code(result))
        before_cancel = self.workflow._verified(run_id)[1]
        self.assertEqual("completed", self.workflow.invoke("cancel", run_id=run_id)["status"])
        self.assertEqual(before_cancel, self.workflow._verified(run_id)[1])
        with service.connect() as db:
            self.assertEqual(before, db.execute("SELECT envelope FROM events ORDER BY sequence").fetchall())

    def test_tampered_journal_cannot_be_verified_or_exported(self):
        run_id, _ = self.start()
        finish_local(self.workflow, run_id)
        path = self.workflow._run_directory(run_id) / "journal/events.sqlite3"
        with closing(sqlite3.connect(path)) as db, db:
            event = json.loads(db.execute("SELECT envelope FROM events WHERE sequence=2").fetchone()[0])
            event["payload"]["forged"] = True
            db.execute("UPDATE events SET envelope=? WHERE sequence=2", (json.dumps(event),))
        for operation in ("status", "events", "verify", "export", "cancel"):
            with self.subTest(operation=operation):
                self.assertFalse(self.workflow.invoke(operation, run_id=run_id)["ok"])
        self.assertFalse((self.workflow._run_directory(run_id) / "evidence.json").exists())

    def test_actual_comparison_failure_is_not_a_human_block_or_pass(self):
        path = next((self.root / "factory/cloudbank/transaction-core").glob("*.json"))
        path.write_text("{}")
        run_id, _ = self.start()
        finish_local(self.workflow, run_id)
        result = self.workflow.invoke("verify", run_id=run_id)
        self.assertTrue(result["verified"])
        self.assertEqual("comparison-failed", result["status"])
        self.assertEqual(1, result["summary"]["divergent"])
        self.assertEqual(1, exit_code(result))
        self.assertTrue(self.workflow.invoke("export", run_id=run_id)["ok"])

    def test_resume_repairs_terminal_archive_after_publication_failure(self):
        run_id, _ = self.start()
        with patch("lightyear_workflow.execution.record_finished", side_effect=OSError("interrupted publish")):
            with self.assertRaises(OSError):
                finish_local(self.workflow, run_id)
        result = self.workflow.invoke("status", run_id=run_id)
        self.assertTrue(result["terminal"])
        self.assertFalse(result["tower"]["available_in_history"])
        before = self.workflow._verified(run_id)[1]
        self.assertEqual("resume-requested", self.workflow.invoke("resume", run_id=run_id)["status"])
        finish_local(self.workflow, run_id)
        self.assertEqual(before, self.workflow._verified(run_id)[1])
        self.assertTrue(self.workflow.invoke("status", run_id=run_id)["tower"]["available_in_history"])

    def test_existing_export_is_not_overwritten(self):
        run_id, _ = self.start()
        finish_local(self.workflow, run_id)
        path = self.workflow._run_directory(run_id) / "evidence.json"
        path.write_text("existing unrelated content")
        result = self.workflow.invoke("export", run_id=run_id)
        self.assertEqual("export-conflict", result["error"]["code"])
        self.assertEqual("existing unrelated content", path.read_text())

    def test_verification_checks_installed_implementation_not_only_checkout(self):
        run_id, _ = self.start()
        finish_local(self.workflow, run_id)
        # Point runtime inspection at the isolated copy, then alter one module.
        path = self.root / "src/lightyear_agent/__init__.py"
        path.write_text(path.read_text() + "\n# Different verifier implementation\n")
        with patch("lightyear_agent.service.SOURCE", self.root / "src"):
            result = self.workflow.invoke("verify", run_id=run_id)
        self.assertEqual("implementation-mismatch", result["error"]["code"])

    def test_project_isolation_paths_pagination_and_unknown_operation(self):
        run_id, _ = self.start()
        other = self.project.with_name("other.json")
        initialize(other, self.root, "other-project")
        result = Workflow(other).invoke("status", run_id=run_id)
        self.assertEqual("run-not-found", result["error"]["code"])
        self.assertEqual("run-not-found", Workflow(other).invoke("cancel", run_id=run_id)["error"]["code"])
        for value in ("../../secrets", "agent-" + "a" * 33, ""):
            self.assertEqual("invalid-run-id", self.workflow.invoke("status", run_id=value)["error"]["code"])
            self.assertEqual("invalid-run-id", self.workflow.invoke("cancel", run_id=value)["error"]["code"])
        for after, limit in ((-1, 1), (True, 1), (0, 26), (0, 0)):
            self.assertEqual("invalid-page", self.workflow.invoke("events", run_id=run_id, after=after, limit=limit)["error"]["code"])
        self.assertEqual("unsupported-operation", self.workflow.invoke("approve")["error"]["code"])
        self.assertEqual("run-not-terminal", self.workflow.invoke("export", run_id=run_id)["error"]["code"])

    def test_dispatch_failure_retains_run_and_explicit_recovery(self):
        self.workflow.dispatcher = lambda _: (_ for _ in ()).throw(OSError("private diagnostic"))
        run_id, plan = self.start()
        result = self.workflow.invoke("status", run_id=run_id)
        self.assertEqual("dispatch-unconfirmed", result["status"])
        self.assertEqual(4, exit_code(result))
        self.workflow.dispatcher = self.dispatched.append
        self.assertEqual("resume-requested", self.workflow.invoke("resume", run_id=run_id)["status"])
        finish_local(self.workflow, run_id)
        self.assertTrue(self.workflow.invoke("verify", run_id=run_id)["verified"])

    def test_worker_lock_and_interrupted_journal_resume_without_duplicate_results(self):
        from lightyear_workflow.execution import execute
        from lightyear_workflow.cloudbank import observe
        run_id, _ = self.start()
        lease = RunStore(self.workflow._run_directory(run_id) / "lease")
        try:
            with self.assertRaisesRegex(ValueError, "owns this run"):
                self.workflow.work(run_id)
        finally:
            lease.close()
        journal = self.workflow._run_directory(run_id) / "journal"
        with patch("lightyear_workflow.execution.run_worker", side_effect=lambda root, action, *_: observe(root, action["service"], action["lane"])):
            execute(self.root, journal, max_steps=2)
        before = RunStore(journal, read_only=True).events()
        finish_local(self.workflow, run_id)
        after = RunStore(journal, read_only=True).events()
        self.assertEqual(before, after[:len(before)])
        results = [e["payload"]["action"]["id"] for e in after if e["type"] == "result"]
        self.assertEqual(19, len(results))
        self.assertEqual(len(results), len(set(results)))
        cursor = 0
        collected = []
        while True:
            page = self.workflow.invoke("events", run_id=run_id, after=cursor, limit=7)
            self.assertTrue(page["ok"], page)
            collected.extend(page["events"])
            cursor = page["next_cursor"]
            if not page["has_more"]:
                break
        self.assertEqual(after, collected)


if __name__ == "__main__":
    unittest.main()
