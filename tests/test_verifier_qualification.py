from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_qualification.__main__ import main
from lightyear_qualification.campaign import (
    builtin, check_freeze, development_campaign, fault_outcome, freeze,
    normalization_challenges, run_case,
)
from lightyear_qualification.corpus import cases, fault_witness
from lightyear_qualification.protocol import ObservationError, compare, normalize, strict_json, validate_command


class ExecutableQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = development_campaign()

    def test_both_differently_structured_programs_pass_all_contract_examples(self):
        for implementation in self.report["correct_implementations"]:
            with self.subTest(implementation=implementation["adapter"]):
                self.assertEqual(16, implementation["metrics"]["cases_in_scope"])
                self.assertEqual(16, implementation["metrics"]["passed"], implementation["runs"])
                self.assertEqual(1, implementation["metrics"]["decision_rate"])

    def test_actual_program_faults_have_witnesses_and_are_detected(self):
        self.assertEqual("passed", self.report["status"])
        self.assertEqual(8, self.report["fault_counts"]["detected"])
        for fault in self.report["faults"]:
            with self.subTest(fault=fault["fault"]):
                self.assertTrue(fault["witness_observed"])
                self.assertEqual("detected", fault["outcome"])
                self.assertTrue(any("stdout" in record for record in fault["run"]["records"]))

    def test_wrong_recipient_caught_even_when_total_money_is_conserved(self):
        fault = next(f for f in self.report["faults"] if f["fault"] == "wrong-recipient")
        step = fault["run"]["records"][0]
        self.assertEqual(12000, sum(a["cents"] for a in step["raw"]["accounts"]))
        self.assertEqual("failed", step["comparison"]["verdict"])

    def test_crash_is_an_actual_process_exit_and_recovery_is_observed(self):
        for implementation in self.report["correct_implementations"]:
            crash = next(r for r in implementation["runs"] if r["case_id"] == "crash-retry")
            self.assertEqual(75, crash["records"][0]["exit_code"])
            self.assertEqual(0, crash["records"][0]["recovery"]["exit_code"])
            self.assertEqual("passed", crash["verdict"])

    def test_unexercised_control_is_not_counted_as_a_detected_defect(self):
        self.assertEqual("not-exercised", self.report["unexercised_control"]["outcome"])
        self.assertEqual("not-exercised", fault_outcome(False, "failed"))
        self.assertEqual("missed", fault_outcome(True, "passed"))
        self.assertEqual("blocked-indeterminate", fault_outcome(True, "indeterminate"))

    def test_fault_confirmation_is_independent_of_comparator_verdict(self):
        with patch("lightyear_qualification.campaign.compare", return_value={"verdict": "passed", "reason": None, "differences": []}):
            run = run_case(builtin("sqlite", "wrong-recipient"), cases()[0])
        self.assertEqual("passed", run["verdict"])
        self.assertTrue(fault_witness("wrong-recipient", run["records"]))
        self.assertEqual("missed", fault_outcome(True, run["verdict"]))

    def test_claims_do_not_promote_local_tests_to_partner_or_blind_qualification(self):
        self.assertTrue(all(value is False for value in self.report["claims"].values()))


class ObservationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.expected = cases()[0]["steps"][0]["expected"]
        self.raw = {"encoding": "integer-cents-v1", **copy.deepcopy(self.expected)}

    def test_normalization_keeps_nearby_business_errors_visible(self):
        self.assertTrue(all(item["passed"] for item in normalization_challenges()))

    def test_missing_owner_recipient_or_outcome_cannot_pass(self):
        for mutation in ("owner", "recipient", "outcome"):
            raw = copy.deepcopy(self.raw)
            if mutation == "owner":
                del raw["accounts"][0]["owner"]
            elif mutation == "recipient":
                raw["accounts"].pop(1)
            else:
                raw["outcomes"] = []
            self.assertNotEqual("passed", compare(self.expected, raw)["verdict"])

    def test_duplicates_extra_fields_unknown_encoding_and_bad_dates_fail_closed(self):
        for field in ("accounts", "operations", "outcomes"):
            raw = copy.deepcopy(self.raw)
            raw[field] += raw[field]
            self.assertEqual("indeterminate", compare(self.expected, raw)["verdict"])
        for value in ("2028-02-30", "20280229", None):
            raw = copy.deepcopy(self.raw)
            raw["operations"][0]["date"] = value
            self.assertEqual("indeterminate", compare(self.expected, raw)["verdict"])

    def test_account_and_operation_order_is_harmless_but_business_fields_are_exact(self):
        raw = copy.deepcopy(self.raw)
        raw["accounts"].reverse()
        self.assertEqual("passed", compare(self.expected, raw)["verdict"])
        raw["operations"][0]["date"] = "2028-03-01"
        self.assertEqual("failed", compare(self.expected, raw)["verdict"])

    def test_reject_nonfinite_values_boolean_amounts_and_duplicate_json_keys(self):
        for text in ('{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}', "not json"):
            with self.assertRaises(ObservationError):
                strict_json(text)
        self.raw["accounts"][0]["cents"] = True
        self.assertEqual("indeterminate", compare(self.expected, self.raw)["verdict"])

    def test_process_failure_cannot_count_as_detected_business_defect(self):
        adapter = {"id": "failed", "argv": [sys.executable, "-c", "raise SystemExit(9)"]}
        run = run_case(adapter, cases()[0])
        self.assertEqual("indeterminate", run["verdict"])
        self.assertEqual("not-exercised", fault_outcome(fault_witness("wrong-recipient", run["records"]), run["verdict"]))

    def test_malformed_adapter_response_is_indeterminate(self):
        adapter = {"id": "malformed", "argv": [sys.executable, "-c", "print('not-json')"]}
        self.assertEqual("indeterminate", run_case(adapter, cases()[0])["verdict"])

    def test_freeze_detects_changed_code_or_policy(self):
        record = freeze()
        check_freeze(record)
        record["public_corpus_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            check_freeze(record)

    def test_external_command_scope_and_crash_types_are_explicit(self):
        for case in cases():
            for step in case["steps"]:
                validate_command(step["command"])
        malformed = copy.deepcopy(cases()[0]["steps"][0]["command"])
        malformed["crash_after_debit"] = "false"
        for command in (malformed, {"kind": "initialize", "accounts": []}, {"kind": "concurrent", "operations": []}):
            with self.assertRaises(ObservationError):
                validate_command(command)

    def test_external_case_evaluation_uses_bound_adapter_and_frozen_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = builtin("journal")
            descriptor = {k: adapter[k] for k in ("id", "argv", "artifact_sha256")}
            descriptor["artifact"] = adapter["argv"][1]
            for name, payload in (("freeze", freeze()), ("cases", cases()[:1]), ("adapter", descriptor)):
                (root / (name + ".json")).write_text(json.dumps(payload), encoding="utf-8")
            args = ["evaluate", "--adapter", str(root / "adapter.json"), "--cases", str(root / "cases.json"),
                    "--freeze", str(root / "freeze.json"), "--output", str(root / "report.json")]
            self.assertEqual(0, main(args))
            result = json.loads((root / "report.json").read_text(encoding="utf-8"))
            self.assertFalse(result["partner_qualified"])
            self.assertEqual("not-attested", result["independent_review"])
            self.assertEqual(2, main(args))  # evidence cannot silently be overwritten


if __name__ == "__main__":
    unittest.main()
