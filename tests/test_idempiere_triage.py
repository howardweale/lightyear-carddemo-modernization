from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_data.contracts import seal
from lightyear_data.idempiere_triage import (
    ANALYST_SCHEMA,
    CALIBRATION_PATH,
    CLAIMS,
    COVERAGE_PATH,
    DIVERGENCE_PATH,
    INDETERMINATE_PATH,
    PLANNER_SCHEMA,
    PLANNER_EXCLUSIONS,
    POLICY_PATH,
    PROVENANCE_PATH,
    RECEIPT_PATH,
    SCHEMA_PATH,
    STRATA,
    WORK_PACKAGE_PATH,
    run_model_triage,
    triage_policy,
    validate_stage3_artifacts,
    verify_analyst_result,
)
from lightyear_factory.providers import ScriptedModelProvider


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATHS = (
    POLICY_PATH,
    WORK_PACKAGE_PATH,
    CALIBRATION_PATH,
    COVERAGE_PATH,
    DIVERGENCE_PATH,
    INDETERMINATE_PATH,
    PROVENANCE_PATH,
    RECEIPT_PATH,
)


class IdempiereTriageEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = {
            path.name: json.loads((ROOT / path).read_text(encoding="utf-8"))
            for path in ARTIFACT_PATHS
        }

    def test_committed_artifacts_verify(self) -> None:
        self.assertEqual([], validate_stage3_artifacts(ROOT))

    def test_sample_is_balanced_unique_and_stratified(self) -> None:
        cases = self.artifacts[WORK_PACKAGE_PATH.name]["cases"]
        self.assertEqual(20, len(cases))
        self.assertEqual(20, len({case["pair_id"] for case in cases}))
        self.assertEqual(
            {"order-to-cash-pilot": 10, "remaining-current-pairs": 10},
            dict(Counter(case["scope"] for case in cases)),
        )
        self.assertEqual(
            {name: 2 for name, _ in STRATA},
            dict(Counter(case["stratum"] for case in cases)),
        )
        self.assertTrue(all(case["stage2_verdict"] == "indeterminate" for case in cases))

    def test_coverage_registers_preserve_the_ms69_denominator(self) -> None:
        coverage = self.artifacts[COVERAGE_PATH.name]
        self.assertEqual(1_078, coverage["pairing"]["paired_script_pairs"])
        self.assertEqual(1_077, coverage["triage"]["flagged_pairs"])
        self.assertEqual(20, coverage["triage"]["sampled_pairs"])
        self.assertEqual(1_057, coverage["triage"]["unsampled_flagged_pairs"])
        self.assertEqual([], self.artifacts[DIVERGENCE_PATH.name]["entries"])
        self.assertEqual(
            1_077, len(self.artifacts[INDETERMINATE_PATH.name]["entries"])
        )
        self.assertEqual(20, len(self.artifacts[PROVENANCE_PATH.name]["entries"]))

    def test_budget_and_claim_boundaries_are_explicit(self) -> None:
        policy = triage_policy()
        self.assertEqual(20, policy["model_budgets"]["planner"]["max_calls"])
        self.assertEqual(20, policy["model_budgets"]["analyst"]["max_calls"])
        self.assertEqual(60_000, policy["model_budgets"]["planner"]["max_input_tokens_per_call"])
        self.assertEqual(25_000, policy["model_budgets"]["analyst"]["max_output_tokens_per_call"])
        self.assertEqual(80_000, policy["context"]["max_role_context_bytes"])
        self.assertEqual(200.0, policy["model_budgets"]["max_total_cost_usd"])
        self.assertIn("not-used", policy["roles"]["builder"])
        receipt = self.artifacts[RECEIPT_PATH.name]
        self.assertEqual(0, receipt["statistics"]["model_calls"])
        self.assertEqual(0, receipt["statistics"]["builder_calls"])
        self.assertEqual(CLAIMS, receipt["claims"])
        self.assertFalse(receipt["claims"]["live_model_triage_complete"])
        self.assertFalse(receipt["claims"]["audit_complete"])

    def test_resealed_tampering_is_rejected(self) -> None:
        artifacts = copy.deepcopy(self.artifacts)
        receipt = artifacts[RECEIPT_PATH.name]
        receipt["claims"]["audit_complete"] = True
        artifacts[RECEIPT_PATH.name] = seal(receipt)
        self.assertIn(
            "stage3-artifact-drift:stage4.receipt.json",
            validate_stage3_artifacts(ROOT, artifacts=artifacts),
        )

    def test_schema_declares_required_fields(self) -> None:
        schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))

        def walk(value):
            if isinstance(value, dict):
                if "required" in value:
                    self.assertLessEqual(set(value["required"]), set(value["properties"]))
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(schema)


class IdempiereTriageWorkcellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.work_package = json.loads((ROOT / WORK_PACKAGE_PATH).read_text(encoding="utf-8"))

    @staticmethod
    def _planner_output(case):
        evidence_id = case["case_id"] + ":bounded:1"
        return {
            "pair_id": case["pair_id"],
            "focus_id": case["case_id"],
            "selected_evidence_ids": [evidence_id],
            "analyst_questions": ["What can the admitted evidence establish?"],
            "excluded_claims": list(PLANNER_EXCLUSIONS),
            "summary": "Bounded evidence only.",
        }

    @staticmethod
    def _analyst_output(case):
        classification = (
            "deliberate-dialect-adaptation"
            if case["stratum"] == "helper-catalog-effects"
            else "indeterminate"
        )
        return {
            "pair_id": case["pair_id"],
            "classification": classification,
            "provenance_classification": "generation-path-present-per-pair-unclassified",
            "evidence_ids": [case["case_id"] + ":bounded:1"],
            "reason_codes": [case["stratum_reason_code"]],
            "summary": "Classification is limited to the admitted excerpt.",
            "required_evidence": ["native database execution"],
        }

    def test_scripted_contract_run_uses_planner_and_analyst_but_no_builder(self) -> None:
        cases = self.work_package["cases"]
        planner = ScriptedModelProvider([self._planner_output(case) for case in cases])
        analyst = ScriptedModelProvider([self._analyst_output(case) for case in cases])

        def context(_source_root, case):
            return {
                "case_id": case["case_id"],
                "pair_id": case["pair_id"],
                "evidence": [{"evidence_id": case["case_id"] + ":bounded:1"}],
                "context_bytes": 100,
            }

        with patch(
            "lightyear_data.idempiere_triage.validate_stage3_artifacts", return_value=[]
        ), patch("lightyear_data.idempiere_triage.hydrate_case_context", side_effect=context):
            result = run_model_triage(ROOT, ROOT, planner, analyst)

        self.assertEqual(20, len(planner.requests))
        self.assertEqual(20, len(analyst.requests))
        self.assertTrue(all(item["role"] == "planner" for item in planner.requests))
        self.assertTrue(all(item["role"] == "failure_analyst" for item in analyst.requests))
        self.assertEqual(40, result["statistics"]["model_calls"])
        self.assertEqual(0, result["statistics"]["builder_calls"])
        self.assertFalse(result["statistics"]["live_model_performance_evidence"])
        self.assertFalse(result["claims"]["live_model_triage_complete"])
        self.assertEqual(2, result["statistics"]["verified_classifications"]["deliberate-dialect-adaptation"])
        self.assertEqual(18, result["statistics"]["verified_classifications"]["indeterminate"])
        self.assertEqual(PLANNER_SCHEMA, planner.requests[0]["schema"])
        self.assertEqual(ANALYST_SCHEMA, analyst.requests[0]["schema"])

    def test_verifier_downgrades_an_unsupported_divergence(self) -> None:
        case = self.work_package["cases"][0]
        plan = self._planner_output(case)
        analysis = {
            **self._analyst_output(case),
            "classification": "genuine-semantic-divergence",
        }
        verified = verify_analyst_result(case, plan, analysis)
        self.assertEqual("indeterminate", verified["verified_classification"])
        self.assertFalse(verified["classification_accepted"])
        self.assertFalse(verified["semantic_verdict_changed"])

    def test_verifier_rejects_unbound_evidence(self) -> None:
        case = self.work_package["cases"][0]
        plan = self._planner_output(case)
        analysis = {**self._analyst_output(case), "evidence_ids": ["invented"]}
        with self.assertRaisesRegex(ValueError, "unknown or empty evidence"):
            verify_analyst_result(case, plan, analysis)

    def test_live_provider_without_token_preflight_is_rejected(self) -> None:
        class UnsafeProvider:
            provider_id = "openai-responses"
            model = "test-model"
            token_preflight = False
            max_input_tokens_per_call = 60_000
            max_output_tokens = 25_000
            input_usd_per_million = 1.0
            output_usd_per_million = 1.0

        unsafe = UnsafeProvider()
        with patch(
            "lightyear_data.idempiere_triage.validate_stage3_artifacts", return_value=[]
        ), self.assertRaisesRegex(ValueError, "requires input-token preflight"):
            run_model_triage(ROOT, ROOT, unsafe, unsafe)


if __name__ == "__main__":
    unittest.main()
