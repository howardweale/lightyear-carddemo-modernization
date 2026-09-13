"""Adversarial boundaries and real process/restart evidence for MS72 Step 2."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from lightyear_data.contracts import seal
from lightyear_data.cloudbank_publication import BUNDLE
from lightyear_workflow.cloudbank import action_for, build_execution_plan, observe
from lightyear_workflow.execution import WorkerFailure, execute, read_execution, replay, run_worker
from lightyear_workflow.execution_policy import default_execution_policy, parse_execution_policy
from lightyear_workflow.policy import default_policy
from lightyear_workflow.run_store import RunStore

ROOT = Path(__file__).resolve().parents[1]


class CloudBankWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in ("src", "factory/cloudbank", "reference-estates/cloudbank", BUNDLE.as_posix()):
            shutil.copytree(ROOT / name, self.root / name, ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "control-tower").mkdir()
        for name in ("workflow-policy.json", "execution-policy.json"):
            shutil.copyfile(ROOT / "control-tower" / name, self.root / "control-tower" / name)
        self.directory = self.root / "work/workflow/cloudbank"

    def policy(self, **changes):
        path = self.root / "control-tower/execution-policy.json"
        value = json.loads(path.read_text())
        value.update(changes)
        path.write_text(json.dumps(value))

    def test_real_workers_complete_five_kinds_and_gate_sixth_after_resume(self):
        first = execute(self.root, self.directory, max_steps=3)
        self.assertEqual("paused", first["status"])
        self.assertEqual(3, first["summary"]["actions_executed"])
        result = execute(self.root, self.directory)
        self.assertEqual("human-decision-required", result["halt_reason"])
        self.assertEqual(8, result["summary"]["resolved"])
        self.assertEqual(19, result["summary"]["actions_executed"])
        self.assertEqual(5, result["summary"]["action_kinds_executed"])
        self.assertEqual(6, result["summary"]["iterations"])
        events = RunStore(self.directory, read_only=True).events()
        self.assertEqual(result, execute(self.root, self.directory))
        self.assertEqual(events, RunStore(self.directory, read_only=True).events())
        self.assertFalse(result["boundary"]["fresh_cloud_execution"])
        self.assertEqual(0, result["boundary"]["semantic_verdicts_changed"])

    def test_interrupted_attempt_consumes_budget_and_only_unfinished_work_retries(self):
        execute(self.root, self.directory, max_steps=1)
        store = RunStore(self.directory)
        state = replay(self.root, store.events())
        action = state["queue"][0]
        store.append("attempt", {"action": action, "attempt": 1})
        store.close()
        with patch("lightyear_workflow.execution.run_worker", side_effect=lambda root, action, *_: observe(root, action["service"], action["lane"])):
            result = execute(self.root, self.directory)
        self.assertEqual(20, result["summary"]["actions_executed"])
        self.assertEqual(1, result["summary"]["worker_failures"])
        self.assertEqual("interrupted", result["failures"][0]["reason"])
        self.assertEqual(8, result["summary"]["resolved"])

    def test_transient_workers_exhaust_bounded_retries_without_false_resolution(self):
        with patch("lightyear_workflow.execution.run_worker", side_effect=WorkerFailure("worker-timeout")):
            result = execute(self.root, self.directory)
        self.assertEqual("no-permitted-action", result["halt_reason"])
        self.assertEqual(16, result["summary"]["actions_executed"])
        self.assertEqual(0, result["summary"]["resolved"])
        self.assertFalse(result["summary"]["converged_within_scope"])

    def test_action_and_iteration_budgets_survive_restart(self):
        self.policy(max_actions=2)
        execute(self.root, self.directory, max_steps=1)
        result = execute(self.root, self.directory)
        self.assertEqual("budget", result["halt_reason"])
        self.assertEqual(2, result["summary"]["actions_executed"])
        self.assertEqual(result, execute(self.root, self.directory))

    def test_iteration_cap_does_not_claim_contract_checks_are_retained_execution(self):
        self.policy(max_iterations=1)
        with patch("lightyear_workflow.execution.run_worker", side_effect=lambda root, action, *_: observe(root, action["service"], action["lane"])):
            result = execute(self.root, self.directory)
        self.assertEqual("budget", result["halt_reason"])
        self.assertEqual({"contract-verified"}, {i["status"] for i in result["items"]})
        self.assertEqual(0, result["summary"]["resolved"])

    def test_worker_cannot_promote_a_claim_or_supply_its_own_verdict(self):
        def forged(root, action, *_):
            result = observe(root, action["service"], action["lane"])
            result["production_ready"] = True
            return result
        with patch("lightyear_workflow.execution.run_worker", side_effect=forged):
            result = execute(self.root, self.directory)
        self.assertEqual("untrusted-worker", result["halt_reason"])
        self.assertEqual(0, result["summary"]["resolved"])

    def test_malformed_worker_output_is_a_persistent_stop(self):
        with patch("lightyear_workflow.execution.run_worker", side_effect=ValueError("Invalid JSON")):
            result = execute(self.root, self.directory)
        self.assertEqual("untrusted-worker", result["halt_reason"])
        self.assertEqual(result, execute(self.root, self.directory))

    def test_input_mutation_during_worker_never_commits_success(self):
        def drift(root, action, *_):
            result = observe(root, action["service"], action["lane"])
            path = root / "src/lightyear_workflow/__init__.py"
            path.write_text(path.read_text() + "\n")
            return result
        with patch("lightyear_workflow.execution.run_worker", side_effect=drift), self.assertRaisesRegex(ValueError, "inputs changed"):
            execute(self.root, self.directory)
        events = RunStore(self.directory, read_only=True).events()
        self.assertEqual({"reason": "scope-boundary"}, events[-1]["payload"])
        self.assertFalse(any(e["type"] == "result" for e in events))

    def test_resealed_receipt_cannot_hide_divergence_or_upgrade_a_result(self):
        execute(self.root, self.directory, max_steps=1)
        events = RunStore(self.directory, read_only=True).events()
        previous = None
        for event in events:
            if event["type"] == "result":
                event["payload"]["after"] = "retained-evidence-verified"
                event["payload"] = seal(event["payload"])
            event["previous_sha256"] = previous
            event.update(seal(event))
            previous = event["content_sha256"]
        with self.assertRaisesRegex(ValueError, "verdict transition"):
            replay(self.root, events)

    def test_changed_inputs_block_resume_and_read_projection(self):
        execute(self.root, self.directory, max_steps=1)
        # Use a real declared input even if the artifact naming evolves.
        path = next((self.root / "factory/cloudbank/transaction-core").glob("*.json"))
        path.write_text(path.read_text() + "\n")
        before = RunStore(self.directory, read_only=True).events()
        with self.assertRaisesRegex(ValueError, "inputs, implementation or policy changed"):
            execute(self.root, self.directory)
        self.assertEqual("invalid", read_execution(self.root, self.directory)["status"])
        self.assertEqual(before, RunStore(self.directory, read_only=True).events())

    def test_missing_evidence_does_not_become_proven_divergence(self):
        path = next((self.root / "factory/cloudbank/transaction-core").glob("*.json"))
        path.unlink()
        result = execute(self.root, self.directory, max_steps=1)
        self.assertEqual("unavailable", result["items"][0]["status"])
        self.assertEqual(0, result["summary"]["divergent"])

    def test_elapsed_budget_includes_worker_completion(self):
        self.policy(max_seconds=1, action_timeout_seconds=1)
        def slow(root, action, *_):
            time.sleep(1.05)
            return observe(root, action["service"], action["lane"])
        with patch("lightyear_workflow.execution.run_worker", side_effect=slow):
            result = execute(self.root, self.directory)
        self.assertEqual("budget", result["halt_reason"])
        self.assertEqual(0, result["summary"]["resolved"])
        self.assertEqual("worker-timeout", result["failures"][0]["reason"])

    def test_real_divergence_halts_and_retains_failed_observation(self):
        path = next((self.root / "factory/cloudbank/transaction-core").glob("*.json"))
        path.write_text("{}")
        result = execute(self.root, self.directory)
        self.assertEqual("divergent", result["halt_reason"])
        self.assertEqual(1, result["summary"]["actions_executed"])
        self.assertTrue(result["items"][0]["receipts"][0]["observation"]["errors"])
        self.assertEqual(result, execute(self.root, self.directory))

    def test_policy_can_reduce_authority_but_cannot_enable_other_adapters_or_models(self):
        for change in ({"max_attempts": 3}, {"max_actions": True}, {"network_access": True}, {"model_calls": True}, {"adapter": "submitted-shell"}, {"extra": "command"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_execution_policy({**default_execution_policy(), **change}, default_policy())
        path = self.root / "control-tower/workflow-policy.json"
        value = json.loads(path.read_text())
        value["autonomy"]["widen-observation"] = "always-ask"
        path.write_text(json.dumps(value))
        result = execute(self.root, self.directory)
        self.assertEqual(0, result["summary"]["actions_executed"])
        self.assertEqual("no-permitted-action", result["halt_reason"])

    def test_read_only_projection_and_writer_lock(self):
        self.assertEqual("unavailable", read_execution(self.root)["status"])
        self.assertFalse(self.directory.exists())
        store = RunStore(self.directory)
        self.addCleanup(store.close)
        with self.assertRaisesRegex(ValueError, "Another headless engine"):
            RunStore(self.directory)
        with self.assertRaisesRegex(ValueError, "Read-only"):
            RunStore(self.directory, read_only=True).append("started", {})
        store.close()
        replacement = RunStore(self.directory)
        self.addCleanup(replacement.close)
        self.assertEqual(1, replacement.append("started", {})["sequence"])

    def test_real_worker_timeout_and_output_limits_are_enforced(self):
        plan = build_execution_plan(self.root)
        action = action_for(plan, "account", "contract")
        with self.assertRaisesRegex(WorkerFailure, "worker-timeout"):
            run_worker(self.root, action, plan["policy"], 0.000001)
        with self.assertRaisesRegex(WorkerFailure, "worker-output-limit"):
            run_worker(self.root, action, {**plan["policy"], "max_output_bytes": 1}, 15)

    def test_outside_output_paths_and_unregistered_actions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "work directory"):
            execute(self.root, self.root / "src/new-run")
        plan = build_execution_plan(self.root)
        for service, lane in (("invented", "contract"), ("account", "apply-ledger-entry")):
            with self.assertRaises(ValueError):
                action_for(plan, service, lane)


if __name__ == "__main__":
    unittest.main()
