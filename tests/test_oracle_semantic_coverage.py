from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.oracle_coverage import (
    DOMAIN_SPECS,
    build_oracle_coverage_artifacts,
    validate_oracle_coverage_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


class OracleSemanticCoverageTests(unittest.TestCase):
    def test_catalog_has_exact_governed_domain_targets(self) -> None:
        artifacts = build_oracle_coverage_artifacts(ROOT)
        catalog = artifacts["behavior-catalog.json"]
        expected = {domain_id: quota for domain_id, _code, _title, quota, _topics in DOMAIN_SPECS}
        actual = {item["id"]: item["behavior_contract_count"] for item in catalog["domains"]}
        self.assertEqual(expected, actual)
        self.assertEqual(500, catalog["behavior_contract_count"])
        self.assertEqual(2000, catalog["case_specification_count"])

    def test_every_behavior_is_documented_versioned_unique_and_unclaimed(self) -> None:
        catalog = build_oracle_coverage_artifacts(ROOT)["behavior-catalog.json"]
        behavior_ids = set()
        case_ids = set()
        for behavior in catalog["behaviors"]:
            self.assertNotIn(behavior["id"], behavior_ids)
            behavior_ids.add(behavior["id"])
            self.assertTrue(behavior["documentation"].startswith("https://docs.oracle.com/"))
            self.assertEqual("19c", behavior["version_scope"]["baseline"])
            self.assertEqual("26ai", behavior["version_scope"]["delta"])
            self.assertEqual([], behavior["version_scope"]["native_versions_executed"])
            self.assertEqual("catalogued-not-executed", behavior["catalog_status"])
            self.assertFalse(behavior["native_oracle_verified"])
            self.assertFalse(behavior["target_equivalent"])
            self.assertEqual(4, behavior["case_specification_count"])
            for case in behavior["case_specifications"]:
                self.assertNotIn(case["id"], case_ids)
                case_ids.add(case["id"])
                self.assertEqual("specified-not-executed", case["status"])
        self.assertEqual(500, len(behavior_ids))
        self.assertEqual(2000, len(case_ids))

    def test_prior_eight_are_bindings_not_inflated_native_claims(self) -> None:
        catalog = build_oracle_coverage_artifacts(ROOT)["behavior-catalog.json"]
        self.assertEqual(8, len(catalog["bootstrap_bindings"]))
        self.assertEqual(8, catalog["bounded_model_verified_behavior_count"])
        self.assertEqual(24, catalog["bounded_model_executed_case_count"])
        self.assertEqual(0, catalog["native_oracle_verified_behavior_count"])
        self.assertEqual(
            {"passed-bounded-model-only"},
            {item["evidence_status"] for item in catalog["bootstrap_bindings"]},
        )

    def test_receipt_tells_architects_catalogued_is_not_supported(self) -> None:
        receipt = build_oracle_coverage_artifacts(ROOT)["coverage.receipt.json"]
        self.assertIn("500 catalogued behaviors", receipt["claim_statement"])
        self.assertIn("none has native Oracle verification", receipt["claim_statement"])
        for name in (
            "case_implementation_complete", "native_oracle_execution_observed", "native_oracle_conformance",
            "idempiere_application_equivalence", "cloudbank_mapping_complete", "migration_complete", "production_ready",
        ):
            self.assertFalse(receipt[name], name)

    def test_rehashed_overclaim_and_committed_drift_fail_closed(self) -> None:
        artifacts = build_oracle_coverage_artifacts(ROOT)
        changed = copy.deepcopy(artifacts["coverage.receipt.json"])
        changed["native_oracle_conformance"] = True
        changed["production_ready"] = True
        changed = seal(changed)
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            prior_source = (
                ROOT / "data-modernization/oracle-dialect-conformance/fixture-catalog.json"
            )
            prior_target = (
                project_root / "data-modernization/oracle-dialect-conformance/fixture-catalog.json"
            )
            prior_target.parent.mkdir(parents=True)
            prior_target.write_bytes(prior_source.read_bytes())
            output_root = project_root / "data-modernization/oracle-semantic-coverage"
            output_root.mkdir(parents=True)
            for name, payload in artifacts.items():
                path = output_root / name
                if name.endswith(".json"):
                    path.write_text(
                        json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                else:
                    path.write_text(payload, encoding="utf-8")
            path = output_root / "coverage.receipt.json"
            path.write_text(json.dumps(changed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            errors = validate_oracle_coverage_artifacts(project_root)
            self.assertIn("oracle-coverage-artifact-drift:coverage.receipt.json", errors)

    def test_cli_and_committed_artifacts_are_deterministic(self) -> None:
        self.assertEqual([], validate_oracle_coverage_artifacts(ROOT))
        result = subprocess.run(
            ["python3", "-m", "lightyear_data", "verify-oracle-semantic-coverage", "--project-root", str(ROOT)],
            cwd=ROOT,
            env={"PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(500, payload["behavior_contract_count"])
        self.assertEqual(2000, payload["case_specification_count"])
        for name in (
            "oracle-semantic-behavior-catalog.schema.json",
            "oracle-semantic-coverage-receipt.schema.json",
        ):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
