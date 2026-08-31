from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.ase import (
    SEMANTIC_BOUNDARY_CASES,
    SapAseSourceAdapter,
    analyze_ase_stored_logic,
    ase_canonical_type,
    build_ase_artifacts,
    build_ase_compatibility_ledger,
    build_ase_conformance_corpus,
    build_ase_conformance_receipt,
    build_ase_profile_contract,
    build_ase_qualification,
    classify_ase_sql,
    reference_ase_catalog,
    reference_ase_events,
    reference_ase_rows,
    validate_ase_compatibility_ledger,
    validate_ase_qualification,
)
from lightyear_data.contracts import seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES, SourceAdapter


ROOT = Path(__file__).resolve().parents[1]


class SapAseSourceAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = reference_ase_catalog()
        cls.rows = reference_ase_rows()
        cls.events = reference_ase_events()
        cls.adapter = SapAseSourceAdapter(cls.catalog, cls.rows, cls.events)

    def test_reference_catalog_has_customer_shaped_depth(self) -> None:
        self.assertEqual(4, len(self.catalog["user_defined_types"]))
        self.assertEqual(2, len(self.catalog["tables"]))
        self.assertEqual(31, sum(len(table["columns"]) for table in self.catalog["tables"]))
        self.assertEqual(10, len(self.catalog["stored_logic"]))
        self.assertEqual({"datarows", "datapages"}, {table["locking_scheme"] for table in self.catalog["tables"]})

    def test_ase_is_a_genuine_target_neutral_source_adapter(self) -> None:
        self.assertIsInstance(self.adapter, SourceAdapter)
        self.assertEqual("sap-ase-16", self.adapter.dialect)
        discovery = self.adapter.discover_schema()
        self.assertEqual(31, sum(len(table["columns"]) for table in discovery["tables"]))
        self.assertFalse(discovery["catalog_observed"])
        self.assertNotIn("target", discovery)

    def test_udts_retain_domain_and_resolve_base_type(self) -> None:
        column = next(column for table in self.catalog["tables"] for column in table["columns"] if column["name"] == "CARD_NUM")
        canonical = ase_canonical_type(column, self.catalog)
        self.assertEqual("variable-character", canonical["kind"])
        self.assertEqual("card_number", canonical["domain"]["name"])
        self.assertEqual("rule_card_number", canonical["domain"]["bound_rule"])

    def test_money_datetime_and_timestamp_meanings_are_not_flattened(self) -> None:
        columns = {column["name"]: column for table in self.catalog["tables"] for column in table["columns"]}
        self.assertEqual({"kind": "exact-decimal", "precision": 19, "scale": 4, "source_range": "ase-money", "nullable": True, "domain": {"name": "money_amount", "base_type": "money", "bound_rule": None, "bound_default": "default_zero_money"}}, ase_canonical_type(columns["AUTH_AMT"], self.catalog))
        self.assertEqual("datetime", ase_canonical_type(columns["EVENT_DT"], self.catalog)["source_clock"])
        row_version = ase_canonical_type(columns["RAW_VERSION"], self.catalog)
        self.assertEqual("fixed-binary", row_version["kind"])
        self.assertTrue(row_version["ase_timestamp_is_row_version"])
        self.assertEqual("unsupported", ase_canonical_type(columns["FLOAT_SCORE"], self.catalog)["kind"])

    def test_profile_exposes_empty_single_and_trailing_space_risk(self) -> None:
        contract = build_ase_profile_contract(self.catalog)
        profile = self.adapter.profile_data(contract)
        auth = next(table for table in profile["tables"] if table["table"] == "AUTHFRDS_ASE")
        reason = next(column for column in auth["columns"] if column["name"] == "REASON")
        fixed = next(column for column in auth["columns"] if column["name"] == "FIXED_CODE")
        self.assertEqual(1, reason["metrics"]["empty_string_count"])
        self.assertEqual(1, reason["metrics"]["single_space_count"])
        self.assertGreaterEqual(fixed["metrics"]["trailing_space_count"], 2)
        self.assertFalse(profile["raw_values_persisted"])

    def test_extraction_requires_sealed_exact_catalog_table_and_columns(self) -> None:
        table = self.catalog["tables"][0]
        contract = seal({"catalog_sha256": self.catalog["content_sha256"], "table": table["name"], "columns": [column["name"] for column in table["columns"]]})
        self.assertEqual(3, len(list(self.adapter.read_rows(contract))))
        changed = copy.deepcopy(contract)
        changed["columns"] = changed["columns"][:-1]
        changed = seal(changed)
        with self.assertRaisesRegex(ValueError, "ase-extraction-column-contract-invalid"):
            list(self.adapter.read_rows(changed))

    def test_replication_resume_binds_catalog_position_and_last_event(self) -> None:
        token = seal({"adapter_id": self.adapter.adapter_id, "catalog_sha256": self.catalog["content_sha256"], "position": self.events[1]["position"], "last_event_sha256": self.events[1]["content_sha256"]})
        self.assertEqual([event["position"] for event in self.events[2:]], [event["position"] for event in self.adapter.capture_changes(token)])
        changed = copy.deepcopy(token)
        changed["last_event_sha256"] = "0" * 64
        changed = seal(changed)
        with self.assertRaisesRegex(ValueError, "ase-replication-resume-event-binding-invalid"):
            list(self.adapter.capture_changes(changed))

    def test_transaction_contract_covers_ase_locking_and_isolation(self) -> None:
        capabilities = self.adapter.transaction_capabilities()
        self.assertEqual([0, 1, 2, 3], capabilities["isolation_levels"])
        self.assertEqual(["allpages", "datapages", "datarows"], capabilities["locking_schemes"])
        self.assertEqual("policy-decision-required", capabilities["chained_mode"])
        self.assertFalse(capabilities["capabilities_observed"])

    def test_tsql_classifier_finds_high_risk_constructs(self) -> None:
        source = "set chained on\nselect * into #x from dbo.t\nexec(@sql)\nraiserror 20001 'bad'"
        self.assertEqual(["chained-mode", "dynamic-exec", "raiserror", "select-into", "temp-table"], classify_ase_sql(source))

    def test_stored_logic_inventory_covers_procedures_and_triggers(self) -> None:
        analyses = [analyze_ase_stored_logic(item) for item in self.catalog["stored_logic"]]
        self.assertEqual(6, sum(item["kind"] == "procedure" for item in analyses))
        self.assertEqual(4, sum(item["kind"] == "trigger" for item in analyses))
        dynamic = next(item for item in analyses if item["name"] == "sp_dynamic_reconcile")
        self.assertEqual("unsupported", dynamic["classification"])
        self.assertEqual("excluded-from-claim-scope", dynamic["decision"])

    def test_five_class_ledger_covers_every_object_and_behavior(self) -> None:
        ledger = build_ase_compatibility_ledger(self.catalog)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertTrue(all(ledger["statistics"][name] > 0 for name in COMPATIBILITY_CLASSES))
        self.assertGreaterEqual(len(ledger["entries"]), 100)
        self.assertEqual({"udts": 4, "tables": 2, "columns": 31, "constraints": 5, "indexes": 3, "behaviors": 54, "stored_logic": 10}, ledger["coverage"])
        self.assertEqual([], validate_ase_compatibility_ledger(ledger, self.catalog))

    def test_ledger_rejects_missing_coverage_and_silent_policy_acceptance(self) -> None:
        ledger = build_ase_compatibility_ledger(self.catalog)
        changed = copy.deepcopy(ledger)
        changed["entries"] = [item for item in changed["entries"] if item["item_id"] != "ase-column:AUTHFRDS_ASE:AUTH_ID"]
        changed = seal(changed)
        self.assertIn("ase-ledger-column-coverage-incomplete", validate_ase_compatibility_ledger(changed, self.catalog))
        changed = copy.deepcopy(ledger)
        next(item for item in changed["entries"] if item["classification"] == "policy-decision-required")["decision"] = "accepted-by-default"
        changed = seal(changed)
        self.assertIn("ase-ledger-unsafe-decision-auto-accepted", validate_ase_compatibility_ledger(changed, self.catalog))

    def test_conformance_corpus_has_depth_in_every_required_dimension(self) -> None:
        corpus = build_ase_conformance_corpus(self.catalog)
        self.assertEqual("passed", corpus["status"])
        self.assertGreaterEqual(corpus["case_count"], 180)
        for category in SEMANTIC_BOUNDARY_CASES:
            self.assertGreaterEqual(corpus["categories"][category], 10, category)
        self.assertEqual(29, corpus["categories"]["type-system"])
        self.assertEqual(4, corpus["categories"]["user-defined-datatypes"])

    def test_conformance_receipt_passes_without_live_promotion(self) -> None:
        receipt = build_ase_conformance_receipt()
        self.assertEqual("passed", receipt["status"])
        self.assertTrue(all(receipt["checks"].values()))
        self.assertFalse(receipt["catalog_observed"])
        self.assertFalse(receipt["replication_observed"])
        self.assertFalse(receipt["target_selected"])

    def test_twelve_gates_qualify_source_not_target_migration(self) -> None:
        qualification = build_ase_qualification()
        self.assertEqual(list(range(1, 13)), [gate["gate"] for gate in qualification["gates"]])
        self.assertTrue(qualification["source_adapter_qualified"])
        self.assertTrue(qualification["semantic_loss_analysis_complete"])
        self.assertIsNone(qualification["target"])
        self.assertFalse(qualification["target_selected"])
        self.assertFalse(qualification["target_migration_qualified"])
        self.assertFalse(qualification["stored_logic_complete"])
        self.assertFalse(qualification["production_ready"])

    def test_rehashed_overclaims_are_rejected(self) -> None:
        changed = copy.deepcopy(build_ase_qualification())
        changed["target_selected"] = True
        changed["database_migration_complete"] = True
        changed = seal(changed)
        errors = validate_ase_qualification(changed)
        self.assertIn("ase-qualification-drift", errors)
        self.assertIn("ase-qualification-overclaim", errors)

    def test_committed_artifacts_are_deterministic(self) -> None:
        expected = build_ase_artifacts()
        root = ROOT / "data-modernization/sap-ase-source-adapter"
        self.assertEqual(10, len(expected))
        for name, payload in expected.items():
            self.assertEqual(payload, json.loads((root / name).read_text(encoding="utf-8")))

    def test_ase_schemas_are_frozen(self) -> None:
        for name in ("sap-ase-source-catalog.schema.json", "sap-ase-compatibility-ledger.schema.json", "sap-ase-conformance-corpus.schema.json", "sap-ase-conformance-receipt.schema.json", "sap-ase-qualification.schema.json"):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
