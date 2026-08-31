from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.builder import load_assets
from lightyear_data.contracts import seal
from lightyear_data.oracle_procedures import (
    PROCEDURE_SOURCE,
    build_procedure_conformance,
    build_procedure_ledger,
    build_procedure_qualification,
    classify_unsupported,
    execute_procedure_case,
    parse_oracle_procedures,
    procedure_cases,
    translate_oracle_procedure,
    validate_procedure_artifacts,
)
from lightyear_data.oracle_source import (
    OracleSourceAdapter,
    build_oracle_postgresql_source_qualification,
    build_oracle_source_artifacts,
    build_oracle_source_conformance,
    build_oracle_source_ledger,
    reference_oracle_events,
    validate_oracle_postgresql_source_qualification,
    validate_oracle_source_ledger,
)
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES, SourceAdapter, build_profile_contract


ROOT = Path(__file__).resolve().parents[1]


class OracleSourceQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model, _, cls.fixtures = load_assets(ROOT)
        cls.events = reference_oracle_events(cls.fixtures["rows"])
        cls.adapter = OracleSourceAdapter(cls.model, cls.fixtures["rows"], cls.events)
        cls.source = (ROOT / PROCEDURE_SOURCE).read_text(encoding="utf-8")

    def test_oracle_is_a_genuine_source_adapter(self) -> None:
        self.assertIsInstance(self.adapter, SourceAdapter)
        discovery = self.adapter.discover_schema()
        self.assertEqual("oracle-26ai-free", self.adapter.dialect)
        self.assertEqual(26, len(discovery["canonical_schema"]["columns"]))
        self.assertEqual(26, len(discovery["source_columns"]))
        self.assertFalse(discovery["catalog_observed"])

    def test_profile_and_extraction_are_contract_bound(self) -> None:
        contract = build_profile_contract(self.model)
        profile = self.adapter.profile_data(contract)
        self.assertFalse(profile["raw_values_persisted"])
        self.assertFalse(profile["profile_observed"])
        extraction = {"model_sha256": self.model["content_sha256"], "columns": [item["name"] for item in self.model["columns"]]}
        self.assertEqual(2, len(list(self.adapter.read_rows(extraction))))
        changed = copy.deepcopy(extraction)
        changed["columns"].pop()
        with self.assertRaisesRegex(ValueError, "oracle-source-extraction-column-contract-invalid"):
            list(self.adapter.read_rows(changed))

    def test_cdc_resume_is_bound_to_scn_and_last_event(self) -> None:
        token = seal({
            "adapter_id": self.adapter.adapter_id,
            "position": self.events[1]["position"],
            "last_event_sha256": self.events[1]["content_sha256"],
        })
        self.assertEqual(2, len(list(self.adapter.capture_changes(token))))
        changed = copy.deepcopy(token)
        changed["last_event_sha256"] = "0" * 64
        changed = seal(changed)
        with self.assertRaisesRegex(ValueError, "oracle-source-cdc-resume-event-binding-invalid"):
            list(self.adapter.capture_changes(changed))

    def test_transaction_capabilities_fail_closed(self) -> None:
        capabilities = self.adapter.transaction_capabilities()
        self.assertEqual("supported", capabilities["commit"])
        self.assertIn("policy-decision-required", capabilities["isolation"])
        self.assertFalse(capabilities["capabilities_observed"])

    def test_source_ledger_covers_columns_and_all_five_classes(self) -> None:
        ledger = build_oracle_source_ledger(self.model)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertEqual(26, len([item for item in ledger["entries"] if item["scope"] == "source-column-to-canonical-type"]))
        self.assertTrue(all(ledger["statistics"][name] > 0 for name in COMPATIBILITY_CLASSES))
        self.assertEqual([], validate_oracle_source_ledger(ledger, self.model))

    def test_source_ledger_rejects_silent_policy_and_exclusion_promotion(self) -> None:
        ledger = build_oracle_source_ledger(self.model)
        policy = copy.deepcopy(ledger)
        next(item for item in policy["entries"] if item["classification"] == "policy-decision-required")["decision"] = "accepted-by-default"
        self.assertIn("oracle-source-ledger-policy-auto-accepted", validate_oracle_source_ledger(seal(policy), self.model))
        unsupported = copy.deepcopy(ledger)
        next(item for item in unsupported["entries"] if item["classification"] == "unsupported")["decision"] = "migrated"
        self.assertIn("oracle-source-ledger-unsupported-not-excluded", validate_oracle_source_ledger(seal(unsupported), self.model))

    def test_source_adapter_conformance_is_non_promoting(self) -> None:
        receipt = build_oracle_source_conformance(ROOT)
        self.assertEqual("passed", receipt["status"])
        self.assertTrue(all(receipt["checks"].values()))
        self.assertFalse(receipt["catalog_observed"])
        self.assertFalse(receipt["redo_observed"])
        self.assertFalse(receipt["production_ready"])

    def test_four_declared_procedures_are_fully_inventoried(self) -> None:
        procedures = parse_oracle_procedures(self.source)
        self.assertEqual(
            ["GET_AUTH_STATUS", "SET_FRAUD_FLAG", "CLASSIFY_AMOUNT", "NORMALIZE_REASON"],
            [item["name"] for item in procedures],
        )
        self.assertTrue(all(item["dependencies"] in ([], ["CARDDEMO.AUTHFRDS"]) for item in procedures))
        with self.assertRaisesRegex(ValueError, "not-fully-inventoried"):
            parse_oracle_procedures(self.source + "\nSELECT 1 FROM DUAL;\n")

    def test_translations_cover_supported_plsql_mechanisms(self) -> None:
        translations = {item["name"]: translate_oracle_procedure(item) for item in parse_oracle_procedures(self.source)}
        self.assertIn("GET DIAGNOSTICS P_ROWS = ROW_COUNT", translations["SET_FRAUD_FLAG"])
        self.assertIn("COALESCE(P_REASON", translations["NORMALIZE_REASON"])
        self.assertIn("ERRCODE = 'P0001'", translations["CLASSIFY_AMOUNT"])
        self.assertTrue(all("LANGUAGE plpgsql" in item for item in translations.values()))

    def test_twenty_procedure_cases_cover_results_side_effects_and_errors(self) -> None:
        cases = procedure_cases()
        self.assertEqual(20, len(cases))
        self.assertEqual({"positive", "targeted-boundary", "mutation"}, {item["classification"] for item in cases})
        for case in cases:
            observed = execute_procedure_case(case)
            for field, value in case["expected"].items():
                self.assertEqual(value, observed[field], msg=f"{case['id']}:{field}")
        conformance = build_procedure_conformance(ROOT)
        self.assertEqual("passed", conformance["status"])
        self.assertGreaterEqual(conformance["observed_feature_count"], 15)

    def test_unsupported_procedure_features_fail_closed(self) -> None:
        samples = {
            "dynamic-sql": "BEGIN EXECUTE IMMEDIATE 'DELETE FROM T'; END;",
            "autonomous-transaction": "PRAGMA AUTONOMOUS_TRANSACTION;",
            "package-state": "CREATE OR REPLACE PACKAGE P AS X NUMBER; END;",
            "database-link": "SELECT X INTO Y FROM T@REMOTE;",
            "procedure-owned-commit": "BEGIN COMMIT; END;",
        }
        for feature, source in samples.items():
            self.assertIn(feature, classify_unsupported(source))
        with self.assertRaisesRegex(ValueError, "unsupported-feature"):
            parse_oracle_procedures(self.source.replace("BEGIN", "BEGIN\n  COMMIT;", 1))

    def test_procedure_ledger_and_qualification_separate_subset_from_completion(self) -> None:
        ledger = build_procedure_ledger(ROOT)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertTrue(all(ledger["statistics"][name] > 0 for name in COMPATIBILITY_CLASSES))
        result = build_procedure_qualification(ROOT)
        self.assertEqual(4, result["procedure_count"])
        self.assertTrue(result["supported_procedure_subset_qualified"])
        self.assertFalse(result["native_execution_observed"])
        self.assertFalse(result["stored_logic_complete"])
        self.assertEqual([], validate_procedure_artifacts(ROOT, result))

    def test_eight_gates_unlock_only_bounded_development(self) -> None:
        result = build_oracle_postgresql_source_qualification(ROOT)
        self.assertEqual(list(range(1, 9)), [item["gate"] for item in result["gates"]])
        self.assertEqual("passed-bounded-supported-subset", result["gates"][7]["status"])
        self.assertTrue(result["development_ready"])
        self.assertTrue(result["supported_procedure_subset_qualified"])
        for name in (
            "live_source_observed", "live_target_observed", "live_redo_observed",
            "native_procedure_execution_observed", "database_migration_complete",
            "stored_logic_complete", "production_ready",
        ):
            self.assertFalse(result[name])

    def test_rehashed_overclaims_are_rejected(self) -> None:
        qualification = copy.deepcopy(build_oracle_postgresql_source_qualification(ROOT))
        qualification["live_source_observed"] = True
        qualification["database_migration_complete"] = True
        errors = validate_oracle_postgresql_source_qualification(ROOT, seal(qualification))
        self.assertIn("oracle-postgresql-source-qualification-drift", errors)
        self.assertIn("oracle-postgresql-source-qualification-overclaim", errors)

    def test_committed_artifacts_are_deterministic_and_schemas_frozen(self) -> None:
        expected = build_oracle_source_artifacts(ROOT)
        root = ROOT / "data-modernization/oracle-source-qualification"
        for name, payload in expected.items():
            self.assertEqual(payload, json.loads((root / name).read_text(encoding="utf-8")))
        for name in (
            "oracle-source-compatibility-ledger.schema.json",
            "oracle-source-conformance-receipt.schema.json",
            "oracle-procedure-compatibility-ledger.schema.json",
            "oracle-procedure-conformance-receipt.schema.json",
            "oracle-procedure-qualification.schema.json",
            "oracle-postgresql-source-qualification.schema.json",
        ):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
