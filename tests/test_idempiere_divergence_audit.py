from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.idempiere_divergence import (
    CONVERSION_BOUNDARY_PATHS,
    MANIFEST_PATH,
    RECEIPT_PATH,
    build_stage1_receipt,
    pair_current_migrations,
    validate_stage1_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


class IdempiereDivergencePairingTests(unittest.TestCase):
    def _write(self, root: Path, relative: str, content: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_pairs_exact_names_and_unique_ticket_fallback_without_a_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [
                "migration/iD13/oracle/202601010000_IDEMPIERE-7000.sql",
                "migration/iD13/postgresql/202601010000_IDEMPIERE-7000.sql",
                "migration/iD13/oracle/202601020000_IDEMPIERE-7001.sql",
                "migration/iD13/postgresql/202601020001_IDEMPIERE-7001.sql",
            ]
            self._write(root, paths[0], "ALTER TABLE C_Order ADD AuditFlag NUMBER(1);\n")
            self._write(root, paths[1], "ALTER TABLE C_Order ADD AuditFlag NUMERIC(1);\n")
            self._write(root, paths[2], "ALTER TABLE Unrelated ADD Flag NUMBER(1);\n")
            self._write(root, paths[3], "ALTER TABLE Unrelated ADD Flag NUMERIC(1);\n")

            pairs, unpaired = pair_current_migrations(root, paths, ["C_Order"])

            self.assertEqual(2, len(pairs))
            self.assertEqual([], unpaired)
            self.assertEqual(
                ["exact-version-and-filename", "unique-version-and-ticket-id"],
                sorted(item["pairing_method"] for item in pairs),
            )
            selected = next(item for item in pairs if item["pilot_slices"])
            self.assertEqual(["order-to-cash"], selected["pilot_slices"])
            self.assertEqual(["C_Order"], selected["pilot_tables_referenced"])
            self.assertTrue(all(item["comparison_status"] == "not-run" for item in pairs))
            self.assertTrue(
                all(item["maintenance_provenance"] == "not-classified" for item in pairs)
            )

    def test_unpaired_script_is_a_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = "migration/iD13/oracle/202601010000_IDEMPIERE-7000.sql"
            self._write(root, relative, "SELECT 1 FROM dual;\n")
            pairs, unpaired = pair_current_migrations(root, [relative], ["C_Order"])
            self.assertEqual([], pairs)
            self.assertEqual(
                [{"dialect": "oracle", "path": relative, "reason": "no-unique-counterpart"}],
                unpaired,
            )


class IdempiereDivergenceCommittedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
        cls.receipt = json.loads((ROOT / RECEIPT_PATH).read_text(encoding="utf-8"))

    def test_stage1_reuses_prior_assets_and_measures_the_full_pairing_surface(self) -> None:
        self.assertEqual(68, self.manifest["milestone"])
        self.assertEqual(68, self.receipt["milestone"])
        statistics = self.manifest["statistics"]
        self.assertEqual(1_078, statistics["oracle_scripts"])
        self.assertEqual(1_078, statistics["postgresql_scripts"])
        self.assertEqual(1_078, statistics["paired_script_pairs"])
        self.assertEqual(1_077, statistics["exact_version_and_filename_pairs"])
        self.assertEqual(1, statistics["unique_version_and_ticket_id_pairs"])
        self.assertEqual(0, statistics["unpaired_oracle_scripts"])
        self.assertEqual(0, statistics["unpaired_postgresql_scripts"])
        self.assertEqual(1.0, statistics["paired_script_coverage"])
        self.assertGreater(statistics["order_to_cash_pilot_pairs"], 0)
        self.assertEqual("order-to-cash", self.manifest["scope"]["pilot_slice"])
        self.assertEqual(9, len(self.manifest["conversion_boundary"]))
        self.assertEqual(
            list(CONVERSION_BOUNDARY_PATHS),
            [item["path"] for item in self.manifest["conversion_boundary"]],
        )
        self.assertEqual(9, len({item["role"] for item in self.manifest["conversion_boundary"]}))
        checks = self.receipt["checks"]
        self.assertTrue(checks["existing_source_pin_reused"])
        self.assertTrue(checks["ms48_inventory_reconciled"])
        self.assertTrue(checks["existing_order_to_cash_slice_reused"])
        self.assertTrue(checks["existing_database_semantic_core_reused"])

    def test_conversion_layer_prevents_an_independent_maintenance_overclaim(self) -> None:
        premise = self.manifest["premise_check"]
        self.assertTrue(premise["conversion_layer_present"])
        self.assertTrue(premise["dual_dialect_migration_log_writer_present"])
        self.assertFalse(premise["independent_parallel_maintenance_proven"])
        self.assertFalse(premise["generated_variants_ruled_out"])
        self.assertEqual("history-classification-required", premise["status"])

    def test_committed_stage1_evidence_is_current(self) -> None:
        self.assertEqual([], validate_stage1_artifacts(ROOT))

    def test_stage1_cannot_be_relabelled_as_future_milestone(self) -> None:
        mutated = seal({**self.manifest, "milestone": 69})
        errors = validate_stage1_artifacts(
            ROOT, manifest=mutated, receipt=build_stage1_receipt(mutated)
        )
        self.assertIn("stage1-milestone-invalid", errors)

    def test_semantic_and_production_overclaims_fail_closed(self) -> None:
        mutated = dict(self.manifest)
        mutated["audit_complete"] = True
        mutated["production_ready"] = True
        mutated = seal(mutated)
        receipt = build_stage1_receipt(mutated)
        errors = validate_stage1_artifacts(ROOT, manifest=mutated, receipt=receipt)
        self.assertIn("pairing-manifest-completion-overclaim", errors)

    def test_generated_versus_manual_premise_cannot_be_promoted_without_history(self) -> None:
        mutated = dict(self.manifest)
        mutated["premise_check"] = {
            **mutated["premise_check"],
            "independent_parallel_maintenance_proven": True,
            "generated_variants_ruled_out": True,
            "status": "passed",
        }
        mutated = seal(mutated)
        receipt = build_stage1_receipt(mutated)
        errors = validate_stage1_artifacts(ROOT, manifest=mutated, receipt=receipt)
        self.assertIn("pairing-manifest-premise-overclaim", errors)

    def test_audit_uses_no_builder_or_model_in_stage1(self) -> None:
        self.assertEqual(
            "not-used-audit-does-not-generate-candidate",
            self.receipt["station_usage"]["builder"],
        )
        self.assertTrue(self.receipt["checks"]["model_calls_zero"])
        for name in (
            "semantic_comparison_complete",
            "agent_triage_complete",
            "audit_complete",
            "application_equivalence",
            "production_ready",
        ):
            self.assertFalse(self.receipt[name])

    def test_cross_platform_entrypoints_and_schemas_exist(self) -> None:
        self.assertTrue((ROOT / "idempiere-divergence-audit.sh").is_file())
        powershell = (ROOT / "idempiere-divergence-audit.ps1").read_text(encoding="utf-8")
        self.assertIn("python-runtime.ps1", powershell)
        schema_paths = (
            ROOT / "data-modernization/schema/idempiere-dialect-pairing-manifest.schema.json",
            ROOT / "data-modernization/schema/idempiere-divergence-stage1-receipt.schema.json",
        )
        for path in schema_paths:
            with self.subTest(path=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
                self.assertFalse(schema["additionalProperties"])

    def test_schemas_declare_every_committed_top_level_field(self) -> None:
        contracts = (
            (
                ROOT / "data-modernization/schema/idempiere-dialect-pairing-manifest.schema.json",
                self.manifest,
            ),
            (
                ROOT / "data-modernization/schema/idempiere-divergence-stage1-receipt.schema.json",
                self.receipt,
            ),
        )
        for path, payload in contracts:
            with self.subTest(path=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(set(payload), set(schema["properties"]))
                self.assertEqual(set(payload), set(schema["required"]))


if __name__ == "__main__":
    unittest.main()
