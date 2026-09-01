from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from lightyear_data.contracts import seal, sign
from lightyear_data.oracle_native_gate import (
    REQUIRED_DATABASE_IDENTITY_FIELDS,
    REQUIRED_SESSION_FIELDS,
    VERSION_LANES,
    build_oracle_native_gate_artifacts,
    validate_native_execution_receipt,
    validate_oracle_native_gate_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]
KEY = "native-evidence-test-key"
HASH = "a" * 64


def valid_partial_receipt() -> dict[str, object]:
    artifacts = build_oracle_native_gate_artifacts(ROOT)
    manifest = artifacts["native-case-manifest.json"]
    case = manifest["cases"][0]
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "receipt_type": "lightyear-oracle-native-execution-receipt",
        "release": "0.51.0",
        "manifest_sha256": manifest["content_sha256"],
        "run_id": "oracle-19c-admission-test",
        "runner_identity": "oracle-native-test-runner",
        "raw_stdout_sha256": HASH,
        "raw_stderr_sha256": HASH,
        "database_identity": {
            "database_lane": "19c",
            "version_full": "19.25.0.0.0",
            "version_banner_sha256": HASH,
            "dbid_sha256": HASH,
            "container_name": "ORCLPDB1",
            "character_set": "AL32UTF8",
            "national_character_set": "AL16UTF16",
            "database_timezone": "+00:00",
            "option_set_sha256": HASH,
        },
        "session_settings": {
            "current_schema": "LIGHTYEAR_NATIVE",
            "current_edition": "ORA$BASE",
            "session_timezone": "+00:00",
            "nls_date_format": "YYYY-MM-DD HH24:MI:SS",
            "nls_timestamp_format": "YYYY-MM-DD HH24:MI:SS.FF6",
            "nls_numeric_characters": ".,",
            "nls_sort": "BINARY",
            "nls_comp": "BINARY",
            "isolation_level": "READ COMMITTED",
        },
        "security": {
            "external_wallet_authentication": True,
            "credentials_in_arguments": False,
            "credentials_persisted": False,
            "raw_stdout_persisted": False,
            "raw_stderr_persisted": False,
        },
        "results": [
            {
                "case_id": case["case_id"],
                "behavior_id": case["behavior_id"],
                "status": "passed-native",
                "bounded_expectation_sha256": case["bounded_expectation_sha256"],
                "harness_sql_sha256": HASH,
                "observed_result_sha256": HASH,
                "diagnostic_codes": [],
                "started_at": "2026-09-01T18:00:00Z",
                "completed_at": "2026-09-01T18:00:01Z",
            }
        ],
        "native_executed_case_count": 1,
        "native_passed_case_count": 1,
        "native_verified_behavior_count": 1,
        "native_oracle_conformance": False,
        "target_equivalence_observed": False,
        "idempiere_application_equivalence": False,
        "cloudbank_mapping_complete": False,
        "migration_complete": False,
        "production_ready": False,
    }
    return sign(payload, KEY, "oracle-native-test-runner")


class OracleNativeExecutionGateTests(unittest.TestCase):
    def test_manifest_maps_every_catalog_case_to_both_native_lanes(self) -> None:
        manifest = build_oracle_native_gate_artifacts(ROOT)["native-case-manifest.json"]
        self.assertEqual(500, manifest["behavior_count"])
        self.assertEqual(2000, manifest["case_count"])
        self.assertEqual(4000, manifest["required_native_case_execution_count"])
        self.assertEqual(list(VERSION_LANES), manifest["version_lanes"])
        self.assertEqual(2000, len({item["case_id"] for item in manifest["cases"]}))
        self.assertEqual(500, len({item["behavior_id"] for item in manifest["cases"]}))
        self.assertEqual(
            {"19c", "26ai"},
            {
                lane["database_lane"]
                for item in manifest["cases"]
                for lane in item["native_lanes"]
            },
        )
        self.assertTrue(
            all(
                lane["harness_status"] == "required-not-materialized"
                and lane["execution_status"] == "not-executed"
                for item in manifest["cases"]
                for lane in item["native_lanes"]
            )
        )

    def test_run_pack_has_exact_version_domain_batches_and_no_native_claim(self) -> None:
        artifacts = build_oracle_native_gate_artifacts(ROOT)
        index = artifacts["run-pack-index.json"]
        receipt = artifacts["readiness.receipt.json"]
        self.assertEqual(20, index["batch_count"])
        self.assertEqual(4000, sum(item["case_count"] for item in index["batches"]))
        self.assertEqual(0, index["materialized_harness_count"])
        self.assertFalse(
            index["bootstrap_harness"]["eligible_as_catalog_native_case_evidence"]
        )
        self.assertEqual(
            {"passed": 5, "blocked": 3},
            Counter(item["status"] for item in receipt["gates"]),
        )
        self.assertEqual(0, receipt["native_executed_case_count"])
        self.assertEqual(0, receipt["native_verified_behavior_count"])
        self.assertFalse(receipt["native_oracle_conformance"])
        self.assertFalse(receipt["target_equivalence_observed"])

    def test_execution_contract_requires_identity_signature_and_no_credentials(self) -> None:
        contract = build_oracle_native_gate_artifacts(ROOT)["execution-contract.json"]
        self.assertEqual(
            list(REQUIRED_DATABASE_IDENTITY_FIELDS),
            contract["required_database_identity_fields"],
        )
        self.assertEqual(list(REQUIRED_SESSION_FIELDS), contract["required_session_fields"])
        self.assertEqual("external-wallet-alias-only", contract["transport"]["authentication"])
        self.assertFalse(contract["transport"]["username_or_password_arguments_allowed"])
        self.assertFalse(contract["receipt_security"]["unsigned_receipts_admitted"])
        serialized = json.dumps(contract).lower()
        self.assertNotIn("oracle_pwd", serialized)
        self.assertNotIn("password=", serialized)

    def test_signed_partial_native_receipt_is_admitted_without_conformance_promotion(self) -> None:
        receipt = valid_partial_receipt()
        self.assertEqual([], validate_native_execution_receipt(ROOT, receipt, KEY))
        self.assertFalse(receipt["native_oracle_conformance"])
        self.assertFalse(receipt["target_equivalence_observed"])

    def test_unsigned_mutated_and_rehashed_overclaims_fail_closed(self) -> None:
        receipt = valid_partial_receipt()
        unsigned = dict(receipt)
        unsigned.pop("signature")
        self.assertIn(
            "oracle-native-receipt-signature-invalid",
            validate_native_execution_receipt(ROOT, unsigned, KEY),
        )

        changed = copy.deepcopy(receipt)
        changed["results"][0]["bounded_expectation_sha256"] = "b" * 64
        changed = sign(changed, KEY, "oracle-native-test-runner")
        self.assertIn(
            f"oracle-native-receipt-expectation-binding-invalid:{changed['results'][0]['case_id']}",
            validate_native_execution_receipt(ROOT, changed, KEY),
        )

        overclaim = copy.deepcopy(receipt)
        overclaim["native_oracle_conformance"] = True
        overclaim["target_equivalence_observed"] = True
        overclaim = sign(overclaim, KEY, "oracle-native-test-runner")
        errors = validate_native_execution_receipt(ROOT, overclaim, KEY)
        self.assertIn("oracle-native-receipt-conformance-claim-invalid", errors)
        self.assertIn(
            "oracle-native-receipt-overclaim:target_equivalence_observed", errors
        )

    def test_rehashed_committed_readiness_overclaim_is_rejected(self) -> None:
        artifacts = build_oracle_native_gate_artifacts(ROOT)
        changed = copy.deepcopy(artifacts["readiness.receipt.json"])
        changed["native_oracle_execution_observed"] = True
        changed["native_oracle_conformance"] = True
        changed = seal(changed)
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            fixture_source = (
                ROOT / "data-modernization/oracle-dialect-conformance/fixture-catalog.json"
            )
            fixture_target = (
                project_root
                / "data-modernization/oracle-dialect-conformance/fixture-catalog.json"
            )
            fixture_target.parent.mkdir(parents=True)
            fixture_target.write_bytes(fixture_source.read_bytes())
            for relative in (
                "data-modernization/oracle-semantic-coverage",
                "data-modernization/oracle-core-sql-coverage",
                "data-modernization/oracle-plsql-coverage",
                "data-modernization/oracle-transaction-cdc-coverage",
                "data-modernization/oracle-schema-structured-coverage",
            ):
                shutil.copytree(ROOT / relative, project_root / relative)
            output = project_root / "data-modernization/oracle-native-execution-gate"
            output.mkdir(parents=True)
            for name, payload in artifacts.items():
                path = output / name
                if name.endswith(".json"):
                    path.write_text(
                        json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                else:
                    path.write_text(payload, encoding="utf-8")
            (output / "readiness.receipt.json").write_text(
                json.dumps(changed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            errors = validate_oracle_native_gate_artifacts(project_root)
        self.assertIn(
            "oracle-native-gate-artifact-drift:readiness.receipt.json", errors
        )
        self.assertIn(
            "oracle-native-gate-overclaim:native_oracle_conformance", errors
        )

    def test_cli_schemas_launchers_and_committed_artifacts_are_deterministic(self) -> None:
        self.assertEqual([], validate_oracle_native_gate_artifacts(ROOT))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "lightyear_data",
                "verify-oracle-native-execution-gate",
                "--project-root",
                str(ROOT),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(4000, payload["required_native_case_execution_count"])
        self.assertEqual(0, payload["native_executed_case_count"])
        self.assertFalse(payload["native_oracle_conformance"])
        for name in (
            "oracle-native-case-manifest.schema.json",
            "oracle-native-gate-readiness-receipt.schema.json",
            "oracle-native-execution-receipt.schema.json",
        ):
            schema = json.loads(
                (ROOT / "data-modernization/schema" / name).read_text(encoding="utf-8")
            )
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertIn("oracle-native-gate", (ROOT / "data-modernization.sh").read_text())
        self.assertIn("oracle-native-gate", (ROOT / "data-modernization.ps1").read_text())


if __name__ == "__main__":
    unittest.main()
