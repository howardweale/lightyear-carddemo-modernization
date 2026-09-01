from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.oracle_dialect import (
    FIXTURE_IDS,
    build_oracle_dialect_artifacts,
    execute_case,
    fixture_catalog,
    validate_conformance_receipt,
    validate_oracle_dialect_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]
ORACLE_ROOT = ROOT / "reference-estates/oracle"
OUTPUT_ROOT = ROOT / "data-modernization/oracle-dialect-conformance"


class OracleDialectCorpusTests(unittest.TestCase):
    def test_official_corpus_is_exact_pinned_and_bounded(self) -> None:
        pin = json.loads((ORACLE_ROOT / "source-pin.json").read_text(encoding="utf-8"))
        manifest = json.loads((ORACLE_ROOT / "corpus-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("v23.3", pin["release"])
        self.assertEqual("e3325a83e56c516815844025418a96ecaf219751", pin["commit"])
        self.assertEqual(pin["commit"], manifest["source"]["commit"])
        self.assertEqual(["customer_orders", "human_resources", "sales_history"], manifest["selection"]["schemas"])
        self.assertEqual(9, manifest["file_count"])
        self.assertEqual(4, manifest["sql_file_count"])
        self.assertEqual(2000, manifest["sql_line_count"])
        self.assertEqual(77919, manifest["total_bytes"])
        expected = {item["path"] for item in pin["files"]}
        actual = {
            path.relative_to(ORACLE_ROOT / "corpus").as_posix()
            for path in (ORACLE_ROOT / "corpus").rglob("*")
            if path.is_file()
        }
        self.assertEqual(expected, actual)
        self.assertFalse(any(path.endswith(".csv") for path in actual))

    def test_offline_acquisition_verifier_passes(self) -> None:
        result = subprocess.run(
            ["python3", "tools/acquire_oracle_dialect_corpus.py", "--verify"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('"status": "verified"', result.stdout)

    def test_eight_prioritized_fixtures_are_carried_forward_unchanged(self) -> None:
        catalog = fixture_catalog(ROOT)
        self.assertEqual(list(FIXTURE_IDS), [item["id"] for item in catalog["fixtures"]])
        self.assertEqual(8, catalog["fixture_count"])
        self.assertEqual(24, catalog["case_count"])
        self.assertEqual(list(range(1, 9)), [item["priority"] for item in catalog["fixtures"]])
        for fixture in catalog["fixtures"]:
            docs = fixture["authority"]["documentation"]
            for url in docs if isinstance(docs, list) else [docs]:
                self.assertTrue(url.startswith("https://docs.oracle.com/"), url)
            for relative in fixture["authority"]["official_corpus_paths"]:
                self.assertTrue((ORACLE_ROOT / "corpus" / relative).is_file(), relative)
            self.assertTrue(fixture["idempiere_source_paths"])

    def test_all_twenty_four_bounded_model_cases_execute(self) -> None:
        catalog = fixture_catalog(ROOT)
        observed = []
        for fixture in catalog["fixtures"]:
            for case in fixture["cases"]:
                result = execute_case(case)
                self.assertEqual(case["expected"], result, f"{fixture['id']}:{case['id']}")
                observed.append((fixture["id"], case["id"]))
        self.assertEqual(24, len(observed))
        self.assertEqual(24, len(set(observed)))

    def test_receipt_is_passing_but_does_not_claim_native_oracle(self) -> None:
        _, receipt, _ = build_oracle_dialect_artifacts(ROOT)
        self.assertEqual("passed-bounded-model", receipt["status"])
        self.assertTrue(receipt["oracle_dialect_authority_acquired"])
        self.assertTrue(receipt["bounded_model_execution_observed"])
        self.assertTrue(all(item["passed"] for item in receipt["results"]))
        for name in (
            "native_oracle_execution_observed", "native_oracle_conformance",
            "idempiere_application_equivalence", "cloudbank_mapping_complete",
            "migration_complete", "production_ready",
        ):
            self.assertFalse(receipt[name], name)
        self.assertEqual([], validate_conformance_receipt(ROOT, receipt))

    def test_rehashed_native_and_equivalence_overclaims_fail_closed(self) -> None:
        _, receipt, _ = build_oracle_dialect_artifacts(ROOT)
        changed = copy.deepcopy(receipt)
        changed["native_oracle_execution_observed"] = True
        changed["native_oracle_conformance"] = True
        changed["idempiere_application_equivalence"] = True
        changed = seal(changed)
        errors = validate_conformance_receipt(ROOT, changed)
        self.assertIn("oracle-dialect-conformance-receipt-drift", errors)
        self.assertIn("oracle-dialect-overclaim:native_oracle_execution_observed", errors)
        self.assertIn("oracle-dialect-overclaim:native_oracle_conformance", errors)
        self.assertIn("oracle-dialect-overclaim:idempiere_application_equivalence", errors)

    def test_native_script_is_complete_but_recorded_as_unexecuted(self) -> None:
        catalog, _, sql = build_oracle_dialect_artifacts(ROOT)
        self.assertIn("WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK", sql)
        self.assertIn("FOR UPDATE", sql)
        self.assertIn("WHEN NO_DATA_FOUND", sql)
        self.assertIn("BLOB", sql)
        self.assertIn("CLOB", sql)
        for fixture in catalog["fixtures"]:
            self.assertEqual(1, sql.count(f"LY49|{fixture['id']}|PASS"), fixture["id"])
        self.assertFalse(catalog["native_oracle_executed"])

    def test_committed_artifacts_and_schemas_are_deterministic(self) -> None:
        catalog, receipt, sql = build_oracle_dialect_artifacts(ROOT)
        self.assertEqual(catalog, json.loads((OUTPUT_ROOT / "fixture-catalog.json").read_text(encoding="utf-8")))
        self.assertEqual(receipt, json.loads((OUTPUT_ROOT / "model-conformance.receipt.json").read_text(encoding="utf-8")))
        self.assertEqual(sql, (OUTPUT_ROOT / "native-oracle-fixtures.sql").read_text(encoding="utf-8"))
        self.assertEqual([], validate_oracle_dialect_artifacts(ROOT))
        for name in (
            "oracle-dialect-fixture-catalog.schema.json",
            "oracle-dialect-model-conformance-receipt.schema.json",
        ):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
