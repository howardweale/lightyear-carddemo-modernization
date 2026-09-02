from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from lightyear_data.cloudbank_customer_postgres import target_mapping
from lightyear_data.cloudbank_dark_factory import (
    FACTORY_RECEIPT_TYPE,
    PATCHES,
    SHARED_CONTRACT_SHA256,
    transformation_plan as ms56_transformation_plan,
    validate_source_patch_inputs,
)
from lightyear_data.cloudbank_production_qualification import (
    EXPECTED_TESTS,
    FAILURE_REPORT_NAME,
    QUALIFICATION_MARKER_SHA256,
    RECEIPT_TYPE,
    _materialize_workspaces,
    _maven_test_result,
    _package_result,
    build_artifacts,
    execute_qualification,
    migration_rehearsal,
    qualification_contract,
    readiness_receipt,
    synthetic_profile,
    transformation_plan,
    validate_artifacts,
    validate_execution_receipt,
)
from lightyear_data.contracts import sign


ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-test-cloudbank-production-qualification-key"
HEX_A = "a" * 64
HEX_B = "b" * 64


def ms56_lane(name: str, image: str) -> dict[str, object]:
    return {
        "lane": name,
        "status": "passed",
        "tests": 2,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "shared_contract_sha256": SHARED_CONTRACT_SHA256,
        "maven_exit_code": 0,
        "stdout_sha256": image,
        "stderr_sha256": image,
        "raw_output_persisted": False,
        "database_image_id_sha256": image,
    }


def ms56_receipt() -> dict[str, object]:
    return sign(
        {
            "schema_version": "1.0",
            "receipt_type": FACTORY_RECEIPT_TYPE,
            "release": "0.56.0",
            "run_id": "cloudbank-test-run",
            "source_oracle_receipt_sha256": HEX_A,
            "postgresql_mapping_receipt_sha256": HEX_B,
            "oracle_image_id_sha256": HEX_A,
            "postgresql_image_id_sha256": HEX_B,
            "mapping_sha256": target_mapping()["content_sha256"],
            "transformation_plan_sha256": ms56_transformation_plan(ROOT)["content_sha256"],
            "work_order_sha256": HEX_A,
            "factory_run_receipt_sha256": HEX_B,
            "changed_paths": sorted(PATCHES),
            "oracle_lane": ms56_lane("oracle", HEX_A),
            "postgresql_lane": ms56_lane("postgresql", HEX_B),
            "shared_contract_sha256": SHARED_CONTRACT_SHA256,
            "status": "passed-bounded-customer-dark-factory-run",
            "source_oracle_application_observed": True,
            "target_postgresql_application_observed": True,
            "native_dual_run_observed": True,
            "application_refactored": True,
            "bounded_customer_application_equivalent": True,
            "human_promotion_authorized": False,
            "target_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
            "security": {
                "source_checkout_mutated": False,
                "raw_maven_output_persisted": False,
                "credentials_persisted": False,
                "production_data_persisted": False,
                "database_ports": "ephemeral-loopback-only",
                "dependency_resolution_network_allowed": True,
            },
        },
        KEY,
        "unit-test",
    )


def qualification_lane(name: str, image: str) -> dict[str, object]:
    return {
        "lane": name,
        "status": "passed",
        "tests": EXPECTED_TESTS,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "maven_exit_code": 0,
        "marker_sha256": QUALIFICATION_MARKER_SHA256,
        "stdout_sha256": image,
        "stderr_sha256": image,
        "raw_output_persisted": False,
        "database_image_id_sha256": image,
    }


def package_result() -> dict[str, object]:
    return {
        "status": "passed",
        "maven_exit_code": 0,
        "jar_sha256": HEX_B,
        "jar_size_bytes": 1024,
        "spring_boot_executable": True,
        "runtime_library_count": 42,
        "oracle_runtime_library_count": 0,
        "postgresql_driver_count": 1,
        "stdout_sha256": HEX_A,
        "stderr_sha256": HEX_B,
        "raw_output_persisted": False,
    }


class CloudBankProductionQualificationTests(unittest.TestCase):
    def test_committed_contracts_are_deterministic_and_bounded(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads(
                (ROOT / "factory/cloudbank/customer-production-qualification" / name).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(expected, actual)
        contract = qualification_contract(ROOT)
        self.assertEqual(EXPECTED_TESTS, contract["native_dual_lane"]["tests_per_lane"])
        self.assertFalse(contract["claim_boundary"]["whole_cloudbank_equivalent"])
        self.assertFalse(contract["claim_boundary"]["production_ready"])
        self.assertFalse(readiness_receipt(ROOT)["native_dual_run_observed"])

    def test_synthetic_profile_persists_only_aggregates(self) -> None:
        profile = synthetic_profile()
        self.assertEqual(10_000, profile["generation"]["row_count"])
        self.assertEqual(10_000, profile["metrics"]["distinct_customer_ids"])
        self.assertEqual(40, profile["metrics"]["maximum_name_characters"])
        self.assertEqual(40, profile["metrics"]["maximum_email_characters"])
        self.assertEqual(4000, profile["metrics"]["maximum_details_characters"])
        self.assertFalse(profile["generation"]["raw_rows_persisted"])
        self.assertFalse(profile["generation"]["production_data_used"])
        self.assertNotIn("rows", profile)

    def test_offline_rehearsal_has_checkpoint_cutover_and_exact_rollback(self) -> None:
        rehearsal = migration_rehearsal()
        self.assertTrue(all(rehearsal["checks"].values()))
        self.assertEqual(5, rehearsal["journal"]["events"])
        self.assertEqual(1, rehearsal["checkpoint"]["resume_count"])
        self.assertEqual(
            rehearsal["rollback"]["pre_cutover_state_sha256"],
            rehearsal["rollback"]["restored_state_sha256"],
        )
        self.assertFalse(rehearsal["native_cdc_observed"])
        self.assertFalse(rehearsal["production_cutover_authorized"])

    def test_materialization_replays_ms56_and_removes_target_oracle_runtime(self) -> None:
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        self.assertEqual([], validate_source_patch_inputs(checkout))
        source_file = checkout / "cloudbank-v5/customer/pom.xml"
        before = source_file.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            oracle, postgres = _materialize_workspaces(ROOT, checkout, Path(directory))
            oracle_pom = (oracle / "customer/pom.xml").read_text(encoding="utf-8")
            target_pom = (postgres / "customer/pom.xml").read_text(encoding="utf-8")
            target_root = (postgres / "pom.xml").read_text(encoding="utf-8")
            self.assertIn("oracle-spring-boot-starter-wallet", oracle_pom)
            self.assertIn("spring-security-test", oracle_pom)
            self.assertIn("org.postgresql", target_pom)
            self.assertIn("<exclusions>", target_pom)
            self.assertNotIn("oracle-spring-boot-starter-ucp", target_root)
            self.assertTrue(
                (
                    postgres
                    / "customer/src/test/java/com/example/customer/"
                    "CustomerProductionQualificationTests.java"
                ).is_file()
            )
        self.assertEqual(before, source_file.read_bytes())

    def test_signed_ms56_chain_drives_bounded_qualification(self) -> None:
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        progress: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            receipt = execute_qualification(
                ROOT,
                checkout,
                ms56_receipt(),
                Path(directory),
                KEY,
                "unit-test",
                "cloudbank-qualification-test",
                lambda workspace, image: qualification_lane("oracle", image),
                lambda workspace, image: (
                    qualification_lane("postgresql", image),
                    package_result(),
                ),
                progress.append,
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["http_contract_observed"])
            self.assertTrue(receipt["transaction_isolation_observed"])
            self.assertFalse(receipt["whole_cloudbank_equivalent"])
            self.assertFalse(receipt["production_ready"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            self.assertEqual(5, len(progress))

            tampered = copy.deepcopy(receipt)
            tampered["postgresql_lane"]["tests"] = 4
            tampered = sign(tampered, KEY, "unit-test")
            self.assertIn(
                "cloudbank-production-qualification-receipt-lane-invalid:postgresql_lane",
                validate_execution_receipt(tampered, KEY, ROOT),
            )

            overclaim = copy.deepcopy(receipt)
            overclaim["production_ready"] = True
            overclaim = sign(overclaim, KEY, "unit-test")
            self.assertIn(
                "cloudbank-production-qualification-receipt-claims-invalid",
                validate_execution_receipt(overclaim, KEY, ROOT),
            )

    def test_plan_launchers_schemas_and_operator_boundary_exist(self) -> None:
        plan = transformation_plan(ROOT)
        self.assertEqual(["customer"], plan["limits"]["application_modules"])
        self.assertIn("pom.xml", plan["target_paths"])
        self.assertEqual(0, plan["limits"]["other_runtime_modules_changed"])
        self.assertTrue((ROOT / "cloudbank-production-qualification.sh").is_file())
        self.assertTrue((ROOT / "cloudbank-production-qualification.ps1").is_file())
        schemas = sorted(
            (ROOT / "reference-estates/cloudbank/schema").glob(
                "customer-production-qualification-*.schema.json"
            )
        )
        self.assertEqual(2, len(schemas))
        self.assertTrue(
            all(json.loads(path.read_text(encoding="utf-8"))["$schema"] for path in schemas)
        )
        readme = (
            ROOT / "factory/cloudbank/customer-production-qualification/README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("10,000-row", readme)
        self.assertIn("does not exercise native CDC", readme)
        qualification_test = (
            ROOT
            / "factory/cloudbank/customer-production-qualification/patches/"
            "CustomerProductionQualificationTests.java"
        ).read_text(encoding="utf-8")
        self.assertTrue(
            qualification_test.startswith(
                "// Copyright (c) 2026, Oracle and/or its affiliates.\n"
            )
        )
        self.assertIn("// Modifications Copyright (c) 2026 Lightyear.", qualification_test)
        self.assertIn("import java.util.List;\nimport javax.sql.DataSource;", qualification_test)

    def test_output_inside_source_and_incomplete_lane_fail_closed(self) -> None:
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        with self.assertRaisesRegex(ValueError, "output-inside-source"):
            execute_qualification(
                ROOT,
                checkout,
                ms56_receipt(),
                checkout / "work",
                KEY,
                "unit-test",
            )
        incomplete = qualification_lane("oracle", HEX_A)
        incomplete["tests"] = 4
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_qualification(
                    ROOT,
                    checkout,
                    ms56_receipt(),
                    output,
                    KEY,
                    "unit-test",
                    oracle_runner=lambda workspace, image: incomplete,
                    postgres_runner=lambda workspace, image: (
                        qualification_lane("postgresql", image),
                        package_result(),
                    ),
                )
            failure = json.loads((output / FAILURE_REPORT_NAME).read_text(encoding="utf-8"))
            self.assertEqual("failed-bounded-qualification", failure["status"])
            self.assertEqual(4, failure["oracle_lane"]["tests"])
            self.assertFalse(failure["security"]["raw_maven_output_persisted"])

    def test_maven_and_executable_jar_evidence_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def test_run(
                argv: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                report = workspace / (
                    "customer/target/surefire-reports/"
                    "TEST-com.example.customer.CustomerProductionQualificationTests.xml"
                )
                report.parent.mkdir(parents=True)
                report.write_text(
                    '<testsuite tests="5" failures="0" errors="0" skipped="0"/>',
                    encoding="utf-8",
                )
                marker = (
                    "CLOUDBANK_PRODUCTION_QUALIFICATION="
                    "http:pass;authn:pass;authz:pass;errors:pass;"
                    "isolation:pass;rollback:pass\n"
                )
                return subprocess.CompletedProcess(argv, 0, marker, "")

            lane = _maven_test_result(workspace, "postgresql", {}, test_run)
            self.assertEqual("passed", lane["status"])
            self.assertEqual(EXPECTED_TESTS, lane["tests"])

            def package_run(
                argv: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                jar = workspace / "customer/target/customer-0.0.1-SNAPSHOT.jar"
                jar.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(jar, "w") as archive:
                    archive.writestr(
                        "BOOT-INF/classes/com/example/customer/CustomerApplication.class",
                        b"synthetic-class",
                    )
                    archive.writestr("BOOT-INF/lib/postgresql-42.7.7.jar", b"driver")
                return subprocess.CompletedProcess(argv, 0, "packaged", "")

            package = _package_result(workspace, {}, package_run)
            self.assertEqual("passed", package["status"])
            self.assertEqual(0, package["oracle_runtime_library_count"])
            self.assertEqual(1, package["postgresql_driver_count"])

    def test_maven_marker_can_be_proven_by_surefire_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def test_run(
                argv: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                report = workspace / (
                    "customer/target/surefire-reports/"
                    "TEST-com.example.customer.CustomerProductionQualificationTests.xml"
                )
                report.parent.mkdir(parents=True)
                marker = (
                    "CLOUDBANK_PRODUCTION_QUALIFICATION="
                    "http:pass;authn:pass;authz:pass;errors:pass;"
                    "isolation:pass;rollback:pass"
                )
                report.write_text(
                    '<testsuite tests="5" failures="0" errors="0" skipped="0">'
                    f"<system-out>{marker}</system-out></testsuite>",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(argv, 0, "build passed", "")

            lane = _maven_test_result(workspace, "oracle", {}, test_run)
            self.assertEqual("passed", lane["status"])
            self.assertEqual(0, lane["marker_stdout_count"])
            self.assertEqual(1, lane["marker_report_count"])

    def test_failed_test_diagnostic_excludes_message_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def test_run(
                argv: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                report = workspace / (
                    "customer/target/surefire-reports/"
                    "TEST-com.example.customer.CustomerProductionQualificationTests.xml"
                )
                report.parent.mkdir(parents=True)
                report.write_text(
                    '<testsuite tests="5" failures="1" errors="0" skipped="0">'
                    '<testcase name="httpContract"><failure type="AssertionError" '
                    'message="secret-value">raw-secret-value</failure></testcase></testsuite>',
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(argv, 1, "maven output", "")

            lane = _maven_test_result(workspace, "postgresql", {}, test_run)
            self.assertEqual("failed", lane["status"])
            self.assertEqual(
                [{"name": "httpContract", "type": "AssertionError"}],
                lane["failed_tests"],
            )
            self.assertNotIn("secret-value", json.dumps(lane))


if __name__ == "__main__":
    unittest.main()
