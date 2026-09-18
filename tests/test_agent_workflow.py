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
import unittest
from unittest.mock import patch
import uuid

from lightyear_agent.cli import exit_code
from lightyear_agent.service import Workflow, initialize
from lightyear_control_tower.decisions import DecisionService, initialize_authority
from lightyear_workflow.cloudbank_extensions import ENTRY_ID, WORKLOAD
from lightyear_workflow.history import read_selected
from lightyear_workflow.run_store import RunStore
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
        for operation in ("status", "events", "verify", "export"):
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
        for value in ("../../secrets", "agent-" + "a" * 33, ""):
            self.assertEqual("invalid-run-id", self.workflow.invoke("status", run_id=value)["error"]["code"])
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
