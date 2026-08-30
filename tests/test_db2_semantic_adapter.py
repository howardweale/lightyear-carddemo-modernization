from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.builder import load_assets
from lightyear_data.contracts import seal
from lightyear_data.db2 import Db2SourceAdapter, build_db2_source_ledger, db2_source_conformance_receipt, validate_db2_source_ledger
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES, SourceAdapter, build_profile_contract


ROOT = Path(__file__).resolve().parents[1]


class Db2SemanticAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model, _, cls.fixtures = load_assets(ROOT)
        cls.profile_contract = build_profile_contract(cls.model)
        cls.adapter = Db2SourceAdapter(cls.model, cls.fixtures["rows"])

    def test_db2_is_a_genuine_source_adapter(self) -> None:
        self.assertIsInstance(self.adapter, SourceAdapter)
        self.assertEqual("db2-zos", self.adapter.dialect)
        discovery = self.adapter.discover_schema()
        self.assertEqual(26, len(discovery["canonical_schema"]["columns"]))
        self.assertFalse(discovery["catalog_observed"])

    def test_profile_is_contract_bound_and_does_not_persist_raw_values(self) -> None:
        profile = self.adapter.profile_data(self.profile_contract)
        self.assertEqual(self.profile_contract["content_sha256"], profile["profile_contract_sha256"])
        self.assertFalse(profile["raw_values_persisted"])
        self.assertFalse(profile["profile_observed"])
        merchant = next(item for item in profile["columns"] if item["name"] == "MERCHANT_NAME")
        self.assertIn("invalid_encoding_count", merchant["metrics"])

    def test_extraction_requires_exact_model_and_column_contract(self) -> None:
        contract = {"model_sha256": self.model["content_sha256"], "columns": [item["name"] for item in self.model["columns"]]}
        self.assertEqual(2, len(list(self.adapter.read_rows(contract))))
        changed = copy.deepcopy(contract)
        changed["columns"] = changed["columns"][:-1]
        with self.assertRaisesRegex(ValueError, "db2-extraction-column-contract-invalid"):
            list(self.adapter.read_rows(changed))

    def test_cdc_resume_token_is_content_bound_and_unknown_positions_fail(self) -> None:
        event = {"position": "0001", "operation": "insert"}
        adapter = Db2SourceAdapter(self.model, events=[event])
        token = seal({"adapter_id": adapter.adapter_id, "position": "0001"})
        self.assertEqual([], list(adapter.capture_changes(token)))
        changed = dict(token)
        changed["position"] = "9999"
        with self.assertRaisesRegex(ValueError, "db2-cdc-resume-token-invalid"):
            list(adapter.capture_changes(changed))

    def test_transaction_capabilities_fail_closed_on_unobserved_behavior(self) -> None:
        capabilities = self.adapter.transaction_capabilities()
        self.assertEqual("policy-decision-required", capabilities["isolation"])
        self.assertFalse(capabilities["capabilities_observed"])
        self.assertFalse(capabilities["production_ready"])

    def test_db2_ledger_governs_every_column_and_behavior_with_five_classes(self) -> None:
        ledger = build_db2_source_ledger(self.model)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        columns = [item for item in ledger["entries"] if item["scope"] == "source-column-to-canonical-type"]
        self.assertEqual(26, len(columns))
        self.assertTrue(all(item["classification"] in COMPATIBILITY_CLASSES for item in ledger["entries"]))
        self.assertTrue(ledger["equivalence_blocked"])
        self.assertGreater(ledger["statistics"]["policy-decision-required"], 0)
        self.assertGreater(ledger["statistics"]["unsupported"], 0)
        self.assertEqual([], validate_db2_source_ledger(ledger, self.model))

    def test_ledger_rejects_missing_coverage_and_unsafe_decisions(self) -> None:
        ledger = build_db2_source_ledger(self.model)
        changed = copy.deepcopy(ledger)
        changed["entries"] = changed["entries"][1:]
        changed = seal(changed)
        self.assertIn("db2-source-ledger-column-coverage-incomplete", validate_db2_source_ledger(changed, self.model))

        changed = copy.deepcopy(ledger)
        policy = next(item for item in changed["entries"] if item["classification"] == "policy-decision-required")
        policy["decision"] = "accepted-by-default"
        changed = seal(changed)
        self.assertIn("db2-source-ledger-policy-auto-accepted", validate_db2_source_ledger(changed, self.model))

    def test_conformance_passes_without_promoting_mainframe_equivalence(self) -> None:
        ledger = build_db2_source_ledger(self.model)
        receipt = db2_source_conformance_receipt(self.adapter, self.model, self.profile_contract, ledger)
        self.assertEqual("passed", receipt["status"])
        self.assertTrue(all(receipt["checks"].values()))
        self.assertFalse(receipt["catalog_observed"])
        self.assertFalse(receipt["cdc_observed"])
        self.assertFalse(receipt["mainframe_equivalent"])

    def test_committed_adapter_artifacts_are_deterministic(self) -> None:
        root = ROOT / "data-modernization/db2-semantic-adapter"
        ledger = build_db2_source_ledger(self.model)
        expected = {
            "authfrds.discovery.json": self.adapter.discover_schema(),
            "authfrds.profile.json": self.adapter.profile_data(self.profile_contract),
            "authfrds.compatibility-ledger.json": ledger,
            "authfrds.conformance.receipt.json": db2_source_conformance_receipt(self.adapter, self.model, self.profile_contract, ledger),
        }
        for name, payload in expected.items():
            self.assertEqual(payload, json.loads((root / name).read_text()))

    def test_db2_schemas_are_frozen(self) -> None:
        for name in ("db2-source-compatibility-ledger.schema.json", "db2-source-conformance-receipt.schema.json"):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
