"""Prove MS76 calls existing gates and fails when they accept witnessed defects."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from carddemo_oracle import cli
from lightyear_data.cloudbank_journeys import Journeys
from lightyear_data.contracts import content_hash
from lightyear_qualification import carddemo_gate, cloudbank_gate, runtime_gates
from lightyear_qualification.__main__ import main


class RuntimeGateQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = runtime_gates.run()

    def test_existing_gates_accept_correct_cases_and_detect_witnessed_defects(self):
        self.assertEqual(self.report["status"], "passed")
        self.assertEqual(self.report["content_sha256"], content_hash(self.report))
        cloud, card = self.report["gates"]
        self.assertEqual(len(cloud["correct"]), 10)
        self.assertEqual(len(card["correct"]), 2)
        for gate, count in ((cloud, 3), (card, 7)):
            self.assertEqual(len(gate["faults"]), count)
            self.assertTrue(all(r["witness"]["observed"] and r["fault_outcome"] == "detected" for r in gate["faults"]))
        self.assertFalse(cloud["whole_journey_suite_qualified"])
        self.assertFalse(self.report["claims"]["partner_qualified"])

    def test_missing_evidence_and_unexercised_fault_do_not_become_pass_or_detection(self):
        cloud, card = self.report["gates"]
        self.assertEqual(cloud["missing_observation"]["verdict"], "indeterminate")
        self.assertEqual(cloud["unexercised_control"]["fault_outcome"], "not-exercised")
        self.assertEqual(card["both_empty"]["verdict"], "indeterminate")
        self.assertEqual(card["one_sided_empty"]["verdict"], "failed")
        self.assertTrue(all(c["verdict"] == "indeterminate" for c in card["admission"]))

    def test_disabling_actual_cloudbank_journal_assertion_exposes_an_escape(self):
        # Balance polling succeeds for this defect; the existing journey's
        # journal assertion is the actual acceptance boundary being qualified.
        with patch.object(Journeys, "assert_transfer", return_value=None) as gate:
            run = cloudbank_gate.run_challenge("success", fault="lost-on-restart")
        gate.assert_called_once()
        self.assertTrue(run["witness"]["observed"])
        self.assertEqual(run["fault_outcome"], "missed")

    def test_disabling_actual_carddemo_comparator_fails_qualification(self):
        original = cli.compare_directories
        def falsely_accept(*args):
            result = original(*args)
            result.update(status="passed", differences=[], reason_code=None)
            return result
        with patch.object(cli, "compare_directories", side_effect=falsely_accept) as gate:
            result = carddemo_gate.campaign()
        self.assertGreater(gate.call_count, 10)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(all(r["fault_outcome"] == "missed" for r in result["faults"]))

    def test_target_failure_retains_raw_invocation_and_is_not_a_witnessed_defect(self):
        with patch.object(cloudbank_gate, "invoke", return_value={"exit_code": 1, "error": "target invocation failed", "stderr": "fixture failed"}):
            result = cloudbank_gate.run_challenge("success", fault="wrong-recipient")
        self.assertEqual(result["verdict"], "indeterminate")
        self.assertEqual(result["fault_outcome"], "not-exercised")
        self.assertEqual(len(result["raw"]), 1)

    def test_freeze_includes_real_gate_implementations_and_policy(self):
        files = self.report["files"]
        for name in ("src/carddemo_oracle/compare.py", "src/carddemo_oracle/cli.py",
                     "src/lightyear_data/cloudbank_journeys.py", "src/lightyear_qualification/cloudbank_gate.py",
                     "spec/comparison-normalizations.json", "factory/verifier-qualification/runtime-gates.json"):
            self.assertIn(name, files)

    def test_source_change_during_campaign_blocks_qualification(self):
        before = runtime_gates.identity()
        with patch.object(runtime_gates, "identity", side_effect=[before, {**before, "changed": "hash"}]), \
             patch.object(cloudbank_gate, "campaign", return_value=self.report["gates"][0]), \
             patch.object(carddemo_gate, "campaign", return_value=self.report["gates"][1]):
            report = runtime_gates.run()
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["source_unchanged_during_campaign"])

    def test_cli_retains_failed_campaign_and_refuses_evidence_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            report = deepcopy(self.report)
            report["status"] = "failed"
            with patch.object(runtime_gates, "run", return_value=report):
                self.assertEqual(main(["runtime-gates", "--output", str(output)]), 1)
            self.assertEqual(json.loads((output / "report.json").read_text())["status"], "failed")
            before = (output / "report.json").read_bytes()
            self.assertEqual(main(["runtime-gates", "--output", str(output)]), 2)
            self.assertEqual((output / "report.json").read_bytes(), before)
