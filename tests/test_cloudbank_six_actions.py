"""Six real action kinds and adversarial human-authority boundaries.

Signatures in these tests belong to a synthetic test operator, never a customer.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

from lightyear_control_tower.decisions import DecisionService, initialize_authority
from lightyear_data.cloudbank_publication import BUNDLE
from lightyear_workflow.cloudbank import observe
from lightyear_workflow.cloudbank_extensions import (ENTRY_ID, WORKLOAD, GRAMMAR, PREVIOUS_GRAMMAR,
                                                    PLATFORM, extended, parse_scenarios, reparsed, rerun)
from lightyear_workflow.execution import execute, read_execution, replay
from lightyear_workflow.ledger_gate import approval_guard, current_approval, read_events, trust_config, validate_approval, verify_application_history
from lightyear_workflow.run_store import RunStore

ROOT = Path(__file__).resolve().parents[1]


class SixActionTests(unittest.TestCase):
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

    def provision(self):
        try:
            import cryptography  # noqa: F401
        except ImportError:
            self.skipTest("Install .[control-tower] for mandatory signed-decision CI")
        authority = self.root / "work/control-tower/authority.json"
        credential = initialize_authority(authority, "synthetic-test-operator", "Synthetic Test Operator", workload_id=WORKLOAD)
        self.service = DecisionService(self.root, authority)
        self.addCleanup(self.service.close)
        self.token = self.service.login(credential.read_text().strip())["token"]

    def decide(self, outcome="approved"):
        item = self.service.review(self.token, ENTRY_ID)
        return self.service.decide(self.token, {"entry_id": ENTRY_ID, "entry_sha256": item["entry_sha256"],
            "ledger_sha256": item["ledger_sha256"], "previous_decision_sha256": (item["latest_decision"] or {}).get("content_sha256"),
            "outcome": outcome, "reason": "Synthetic test fixture approval; no real human or customer approval asserted",
            "owner": "Synthetic Test Owner", "review_after": (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat(),
            "request_id": str(uuid.uuid4())})

    def events(self):
        with self.service.connect() as db:
            return read_events(db)

    def test_real_six_kind_execution_restart_and_signed_application(self):
        self.provision()
        approval = self.decide()
        before = self.events()
        first = execute(self.root, self.directory, max_steps=19)
        self.assertEqual("paused", first["status"])
        self.assertEqual(5, first["summary"]["action_kinds_executed"])
        result = execute(self.root, self.directory)
        self.assertEqual("completed", result["status"])
        self.assertEqual(20, result["summary"]["actions_executed"])
        self.assertEqual(6, result["summary"]["action_kinds_executed"])
        self.assertEqual(1, result["boundary"]["ledger_entries_applied"])
        self.assertEqual(0, result["boundary"]["decisions_created"])
        receipt = result["action_kinds"][-1]["receipts"][0]
        self.assertEqual(approval, receipt["human_approval"]["decision"])
        artifact = receipt["observation"]["artifact"]
        self.assertFalse(artifact["raw_equal"])
        self.assertTrue(artifact["normalized_equal"])
        self.assertTrue(artifact["raw_differences_retained"])
        self.assertEqual([], artifact["suppressed_fields"])
        self.assertEqual(before, self.events(), "Engine must not write the human decision journal")
        events = RunStore(self.directory, read_only=True).events()
        self.assertEqual(result, execute(self.root, self.directory))
        self.assertEqual(events, RunStore(self.directory, read_only=True).events())
        self.decide("rejected")
        view = read_execution(self.root, self.directory)
        self.assertEqual("blocked", view["current_ledger_approval"]["status"])
        self.assertEqual(1, view["boundary"]["ledger_entries_applied"], "Historical application must remain visible")
        forged = deepcopy(receipt["human_approval"])
        forged["checked_at"] = datetime.now(timezone.utc).isoformat()
        with self.assertRaisesRegex(ValueError, "omitted"):
            verify_application_history(self.root, forged)

    def test_reparse_extends_typed_corpus_and_rerun_observes_changed_inputs(self):
        parsed, corpus, checked = reparsed(self.root), extended(self.root), rerun(self.root)
        self.assertNotEqual(parsed["grammar"], parsed["previous_grammar"])
        self.assertEqual(28, len(parsed["records"]))
        self.assertEqual(8, corpus["previous_count"])
        self.assertEqual(28, corpus["added_count"])
        self.assertEqual(36, len({r["id"] for r in corpus["records"]}))
        self.assertNotEqual(checked["before_corpus_sha256"], checked["after_corpus_sha256"])
        self.assertTrue(all(c["passed"] for c in checked["checks"]))
        self.assertFalse(corpus["new_external_capture"])
        value = json.loads((self.root / PLATFORM).read_text())
        for grammar in (GRAMMAR, PREVIOUS_GRAMMAR):
            bad = deepcopy(value); bad["scenarios"].append(bad["scenarios"][0])
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                parse_scenarios(bad, grammar)
        value["scenarios"][0]["status"] = True
        with self.assertRaises(ValueError):
            parse_scenarios(value, GRAMMAR)
        with self.assertRaisesRegex(ValueError, "Unregistered"):
            parse_scenarios(value, "submitted-parser")

    def test_missing_signature_wrong_scope_actor_chain_review_and_expiry_are_rejected(self):
        self.provision()
        self.decide()
        trust, events = trust_config(self.root), self.events()
        now = datetime.now(timezone.utc)
        self.assertEqual(ENTRY_ID, validate_approval(self.root, trust, events, now)["entry_id"])
        with self.assertRaisesRegex(ValueError, "expired"):
            validate_approval(self.root, trust, events, now + timedelta(days=3))
        with self.assertRaises(ValueError):
            validate_approval(self.root, trust, events[1:], now)
        for mutate in (lambda e: e["payload"].update(workload_id="different-estate"),
                       lambda e: e["payload"].update(entry_sha256="0" * 64),
                       lambda e: e["payload"].update(ledger_sha256="0" * 64),
                       lambda e: e["actor"].update(kind="engine"),
                       lambda e: e["payload"].update(previous_decision_sha256="0" * 64),
                       lambda e: e["payload"].update(reason="")):
            bad = deepcopy(events); mutate(bad[-1])
            # Re-sign the changed body with the test service: valid crypto alone is insufficient.
            bad[-1] = self.service.sign({k: v for k, v in bad[-1].items() if k not in {"content_sha256", "signature"}})
            with self.assertRaises(ValueError):
                validate_approval(self.root, trust, bad, now)
        bad = deepcopy(events); bad[-1]["signature"]["value"] = "invalid"
        with self.assertRaises(ValueError):
            validate_approval(self.root, trust, bad, now)
        bad = deepcopy(events); bad[1]["payload"]["entry_sha256"] = "0" * 64
        previous = "0" * 64
        for i, event in enumerate(bad):
            body = {k: v for k, v in event.items() if k not in {"content_sha256", "signature"}}
            body["previous_sha256"] = previous
            bad[i] = self.service.sign(body); previous = bad[i]["content_sha256"]
        with self.assertRaisesRegex(ValueError, "reviewed"):
            validate_approval(self.root, trust, bad, now)
        self.decide("rejected")
        self.assertEqual("blocked", current_approval(self.root)["status"])

    def test_revocation_during_worker_prevents_application(self):
        self.provision(); self.decide()
        def worker(root, action, *_):
            if action["kind"] == "apply-ledger-entry":
                self.decide("rejected")
            return observe(root, action["service"], action["lane"])
        with patch("lightyear_workflow.execution.run_worker", side_effect=worker):
            result = execute(self.root, self.directory)
        self.assertEqual("scope-boundary", result["halt_reason"])
        self.assertEqual(0, result["boundary"]["ledger_entries_applied"])
        self.assertEqual("approval-changed", result["failures"][-1]["reason"])

    def test_application_guard_excludes_concurrent_decision_writer_without_writing(self):
        self.provision(); self.decide()
        before = self.events()
        with approval_guard(self.root):
            db = sqlite3.connect(self.service.database, timeout=0.01)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute("BEGIN IMMEDIATE")
            finally:
                db.close()
        self.assertEqual(before, self.events())
        self.decide("rejected")  # The writer is released after the application commit.
        self.assertEqual("blocked", current_approval(self.root)["status"])

    def test_narrowed_policy_blocks_each_new_action_and_dependents(self):
        for kind, expected in (("reparse", 2), ("extend-corpus", 3), ("rerun", 4), ("apply-ledger-entry", 5)):
            with self.subTest(kind=kind):
                path = self.root / "control-tower/workflow-policy.json"
                policy = json.loads((ROOT / "control-tower/workflow-policy.json").read_text())
                policy["autonomy"][kind] = "always-ask"
                path.write_text(json.dumps(policy))
                with patch("lightyear_workflow.execution.run_worker", side_effect=lambda root, action, *_: observe(root, action["service"], action["lane"])):
                    result = execute(self.root, self.directory.parent / kind)
                self.assertEqual(expected, result["summary"]["action_kinds_executed"])
                self.assertEqual("no-permitted-action", result["halt_reason"])
                self.assertFalse(result["summary"]["converged_within_scope"])


if __name__ == "__main__":
    unittest.main()
