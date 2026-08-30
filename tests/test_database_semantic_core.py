from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.oracle import OracleAdapter
from lightyear_data.postgres import PostgreSQLAdapter
from lightyear_data.semantic_core import (
    CANONICAL_TYPES,
    COMPATIBILITY_CLASSES,
    CompatibilityClass,
    adapter_conformance_receipt,
    build_compatibility_ledger,
    build_canonical_schema,
    build_profile_contract,
    build_semantic_core_contract,
    build_transformation_plan,
    canonical_type,
    compare_normalized_rows,
    compare_query_results,
    compare_transactions,
    normalize_row,
    validate_cdc_event,
    validate_compatibility_ledger,
    validate_cutover_and_rollback,
)


ROOT = Path(__file__).resolve().parents[1]


class DatabaseSemanticCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base = ROOT / "data-modernization"
        cls.model = json.loads((base / "canonical/authfrds.model.json").read_text())
        cls.fixtures = json.loads((base / "fixtures/authfrds.fixtures.json").read_text())
        cls.postgres = PostgreSQLAdapter()
        cls.oracle = OracleAdapter()
        cls.mappings = (cls.postgres.mapping(cls.model), cls.oracle.mapping(cls.model))

    def test_core_contract_defines_all_required_platform_boundaries(self) -> None:
        contract = build_semantic_core_contract()
        self.assertEqual(set(CANONICAL_TYPES), set(contract["canonical_type_system"]["types"]))
        self.assertEqual(
            set(COMPATIBILITY_CLASSES),
            set(contract["compatibility_ledger_contract"]["allowed_classifications"]),
        )
        self.assertEqual(
            {"discover_schema", "profile_data", "read_rows", "capture_changes", "transaction_capabilities"},
            set(contract["source_adapter_interface"]["required_operations"]),
        )
        self.assertFalse(contract["production_ready"])

    def test_canonical_types_preserve_exact_shape_and_reject_unknowns(self) -> None:
        decimal_column = next(item for item in self.model["columns"] if item["name"] == "APPROVED_AMT")
        self.assertEqual(
            {"kind": "exact-decimal", "precision": 12, "scale": 2, "nullable": True},
            canonical_type(decimal_column),
        )
        changed = copy.deepcopy(decimal_column)
        changed["source_type"] = "FLOAT"
        with self.assertRaisesRegex(ValueError, "unsupported-canonical-source-type:FLOAT"):
            canonical_type(changed)

    def test_profile_contract_requires_semantic_risk_metrics_without_values(self) -> None:
        profile = build_profile_contract(self.model)
        character = next(item for item in profile["columns"] if item["name"] == "MERCHANT_NAME")
        decimal = next(item for item in profile["columns"] if item["name"] == "APPROVED_AMT")
        self.assertIn("empty_string_count", character["metrics"])
        self.assertIn("decimal_overflow_count", decimal["metrics"])
        self.assertFalse(profile["raw_values_persisted"])
        self.assertFalse(profile["profile_observed"])

    def test_authfrds_projects_to_a_genuine_canonical_schema(self) -> None:
        schema = build_canonical_schema(self.model)
        self.assertEqual("lightyear-canonical-database-schema", schema["schema_type"])
        self.assertEqual(26, len(schema["columns"]))
        self.assertEqual("fixed-character", schema["columns"][0]["type"]["kind"])
        self.assertEqual("timestamp", schema["columns"][1]["type"]["kind"])
        self.assertEqual([], schema["stored_logic"])
        self.assertFalse(schema["production_ready"])

    def test_transformation_plan_is_multi_target_but_not_pairwise_or_stored_logic(self) -> None:
        plan = build_transformation_plan(self.model, self.mappings)
        self.assertEqual(["oracle-26ai-free", "postgresql-16"], [item["target_dialect"] for item in plan["targets"]])
        self.assertTrue(all(item["steps"][-1]["operation"] == "compare-schema-data-query-and-transaction-evidence" for item in plan["targets"]))
        self.assertFalse(plan["stored_logic_in_scope"])
        self.assertFalse(plan["automatic_cutover_allowed"])

    def test_ledger_covers_every_column_and_declares_behavioral_boundaries(self) -> None:
        ledger = build_compatibility_ledger(self.model, self.mappings)
        self.assertEqual([], validate_compatibility_ledger(ledger, self.model, self.mappings))
        column_entries = [item for item in ledger["entries"] if item["scope"] == "column-type-and-value-semantics"]
        self.assertEqual(52, len(column_entries))
        oracle_char = next(item for item in column_entries if item["item_id"] == "column:oracle-26ai-free:MERCHANT_NAME")
        self.assertEqual(CompatibilityClass.POLICY_DECISION_REQUIRED.value, oracle_char["classification"])
        self.assertEqual("unresolved", oracle_char["decision"])
        scopes = {item["scope"] for item in ledger["entries"]}
        self.assertTrue({"transaction-isolation", "cdc-ddl", "cdc-sequence-state", "stored-logic"}.issubset(scopes))
        self.assertTrue(ledger["equivalence_blocked"])

    def test_ledger_rejects_unknown_classes_missing_coverage_and_unsafe_acceptance(self) -> None:
        ledger = build_compatibility_ledger(self.model, self.mappings)
        changed = copy.deepcopy(ledger)
        changed["entries"][0]["classification"] = "probably-compatible"
        changed = seal(changed)
        self.assertIn("compatibility-ledger-classification-invalid", validate_compatibility_ledger(changed, self.model, self.mappings))

        changed = copy.deepcopy(ledger)
        changed["entries"] = changed["entries"][1:]
        changed = seal(changed)
        self.assertIn("compatibility-ledger-column-coverage-incomplete", validate_compatibility_ledger(changed, self.model, self.mappings))

        changed = copy.deepcopy(ledger)
        policy = next(item for item in changed["entries"] if item["classification"] == "policy-decision-required")
        policy["decision"] = "accepted-by-core-policy"
        changed = seal(changed)
        self.assertIn("compatibility-ledger-unsafe-auto-acceptance", validate_compatibility_ledger(changed, self.model, self.mappings))

    def test_normalized_rows_are_typed_deterministic_and_multiset_compared(self) -> None:
        row = copy.deepcopy(self.fixtures["rows"][0])
        row["MERCHANT_CITY"] = "APPROVED   "
        normalized = normalize_row(row, self.model)
        desc = next(item for item in normalized["cells"] if item["name"] == "MERCHANT_CITY")
        amount = next(item for item in normalized["cells"] if item["name"] == "APPROVED_AMT")
        self.assertEqual("APPROVED", desc["value"])
        self.assertEqual("125.50", amount["value"])
        self.assertEqual("passed", compare_normalized_rows([normalized], [normalized])["status"])
        other = normalize_row(self.fixtures["rows"][1], self.model)
        self.assertEqual("failed", compare_normalized_rows([normalized], [other])["status"])

    def test_query_comparison_binds_statement_parameters_shape_rows_and_errors(self) -> None:
        result = {
            "statement_sha256": "a" * 64,
            "parameters_sha256": "b" * 64,
            "columns": [{"name": "COUNT", "canonical_type": "signed-integer"}],
            "rows": [["1"]],
            "error_class": None,
        }
        self.assertEqual("passed", compare_query_results(result, copy.deepcopy(result))["status"])
        changed = copy.deepcopy(result)
        changed["rows"] = [["2"]]
        receipt = compare_query_results(result, changed)
        self.assertEqual("failed", receipt["status"])
        self.assertFalse(receipt["checks"]["rows"])

    def test_transaction_comparison_includes_commit_rollback_and_isolation(self) -> None:
        result = {
            "initial_state_sha256": "a" * 64,
            "operations_sha256": "b" * 64,
            "commit_state_sha256": "c" * 64,
            "rollback_state_sha256": "a" * 64,
            "error_class": None,
            "isolation_observations": {"dirty_read": False, "nonrepeatable_read": False},
        }
        self.assertEqual("passed", compare_transactions(result, copy.deepcopy(result))["status"])
        changed = copy.deepcopy(result)
        changed["rollback_state_sha256"] = "d" * 64
        self.assertEqual("failed", compare_transactions(result, changed)["status"])

    def test_cdc_envelope_is_content_bound_and_operation_specific(self) -> None:
        event = seal({
            "source_adapter": {"id": "db2-source", "version": "1.0"},
            "stream_id": "authfrds",
            "partition": "0",
            "position": "0001",
            "transaction_id": "tx-1",
            "operation": "insert",
            "table": "CARDDEMO.AUTHFRDS",
            "key": {"CARD_NUM": "1", "AUTH_TS": "2026-01-01T00:00:00.000000"},
            "before": None,
            "after": {"CARD_NUM": "1"},
            "occurred_at": "2026-08-30T00:00:00Z",
        })
        self.assertEqual([], validate_cdc_event(event))
        changed = copy.deepcopy(event)
        changed["after"] = None
        self.assertIn("cdc-insert-image-invalid", validate_cdc_event(changed))
        self.assertIn("cdc-event-content-hash-invalid", validate_cdc_event(changed))

    def test_cutover_and_rollback_contracts_fail_closed(self) -> None:
        cutover = {
            "gates": {name: True for name in (
                "initial-load-reconciled", "cdc-caught-up", "write-freeze-observed",
                "final-delta-reconciled", "human-approval-valid", "rollback-checkpoint-valid",
            )},
            "automatic_approval": False,
        }
        rollback = {
            "evidence": {name: "sha256:" + name for name in (
                "pre-cutover-checkpoint", "reverse-or-replay-plan", "identity-after-restore", "divergence-report",
            )},
            "production_ready": False,
        }
        self.assertEqual([], validate_cutover_and_rollback(cutover, rollback))
        cutover["gates"]["human-approval-valid"] = False
        rollback["production_ready"] = True
        self.assertEqual(
            ["cutover-gates-incomplete", "rollback-overclaims-production-readiness"],
            validate_cutover_and_rollback(cutover, rollback),
        )

    def test_both_existing_target_adapters_pass_non_promoting_conformance(self) -> None:
        ledger = build_compatibility_ledger(self.model, self.mappings)
        receipt = adapter_conformance_receipt(
            (self.postgres, self.oracle), self.model, ledger, self.fixtures
        )
        self.assertEqual("passed", receipt["status"])
        self.assertEqual({"factorydark-postgresql", "factorydark-oracle"}, {item["adapter"]["id"] for item in receipt["adapters"]})
        self.assertFalse(receipt["production_qualification_implied"])
        self.assertFalse(receipt["production_ready"])

    def test_semantic_core_schemas_are_frozen_and_parseable(self) -> None:
        names = {
            "database-semantic-core.schema.json",
            "database-compatibility-ledger.schema.json",
            "normalized-row.schema.json",
            "cdc-event-envelope.schema.json",
            "adapter-conformance-receipt.schema.json",
            "canonical-database-schema.schema.json",
        }
        schema_root = ROOT / "data-modernization/schema"
        for name in names:
            payload = json.loads((schema_root / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", payload["$schema"])


if __name__ == "__main__":
    unittest.main()
