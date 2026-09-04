from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_native_wave import RECEIPT_TYPE as MS60_RECEIPT_TYPE
from lightyear_data.cloudbank_oracle_equivalence import (
    DIAGNOSTIC_MARKER,
    EXPECTED_TESTS,
    OBSERVATION_SHA256,
    ORACLE_AQ_PACKAGES,
    OUTPUT_ROOT,
    RECEIPT_TYPE,
    TEST_PATCHES,
    build_artifacts,
    changed_paths,
    compatibility_ledger,
    equivalence_contract,
    equivalence_failure_diagnostic,
    execute_equivalence,
    execution_plan,
    _failure_phase,
    _bootstrap_oracle_aq_privileges,
    _lane_passed,
    _oracle_lane,
    _safe_database_diagnostics,
    _test_result,
    materialize_workspaces,
    observation_contract,
    readiness_receipt,
    validate_artifacts,
    validate_execution_receipt,
)
from lightyear_data.cloudbank_production_qualification import (
    RECEIPT_TYPE as MS57_RECEIPT_TYPE,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "cloudbank-upstream"
KEY = "unit-test-cloudbank-oracle-equivalence-key"
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def ms57_receipt() -> dict[str, object]:
    return {
        "receipt_type": MS57_RECEIPT_TYPE,
        "content_sha256": HEX_A,
        "oracle_image_id_sha256": HEX_B,
        "postgresql_image_id_sha256": HEX_C,
    }


def ms60_receipt() -> dict[str, object]:
    return {
        "receipt_type": MS60_RECEIPT_TYPE,
        "content_sha256": HEX_B,
        "postgresql_image_id_sha256": HEX_C,
    }


def passed_lane(name: str, image_id: str) -> dict[str, object]:
    lane: dict[str, object] = {
        "lane": name,
        "status": "passed",
        "tests": EXPECTED_TESTS,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "maven_exit_code": 0,
        "database_image_id_sha256": image_id,
        "observation_sha256": OBSERVATION_SHA256,
        "marker_stdout_count": 1,
        "marker_report_count": 1,
        "test_reports_present": 2,
        "failed_tests": [],
        "failure_phase": None,
        "stdout_sha256": HEX_A,
        "stderr_sha256": HEX_B,
        "raw_output_persisted": False,
        "synthetic_data_only": True,
    }
    if name == "oracle":
        lane["aq_privilege_bootstrap"] = True
        lane["identity_login_checks"] = {
            "application": True,
            "migration": True,
        }
    return lane


class CloudBankOracleEquivalenceTests(unittest.TestCase):
    def test_oracle_lane_separates_application_and_migration_identities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            captured: dict[str, object] = {}

            def fake_run(
                argv: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                if argv[:3] == ["docker", "image", "inspect"]:
                    return subprocess.CompletedProcess(argv, 0, f"sha256:{HEX_B}\n", "")
                if argv[:2] == ["docker", "run"]:
                    return subprocess.CompletedProcess(argv, 0, "container-id\n", "")
                if argv[:3] == ["docker", "inspect", "--format"]:
                    state = {"Status": "running", "OOMKilled": False}
                    return subprocess.CompletedProcess(argv, 0, json.dumps(state), "")
                if argv[:3] == ["docker", "exec", "-i"]:
                    captured.setdefault("exec_calls", []).append((argv, kwargs))
                    marker = next(
                        (
                            line.split("'")[1]
                            for line in str(kwargs.get("input", "")).splitlines()
                            if line.startswith("SELECT '")
                        ),
                        "CLOUDBANK_ORACLE_READY",
                    )
                    return subprocess.CompletedProcess(
                        argv, 0, f"{marker}\n", ""
                    )
                if argv[:2] == ["docker", "port"]:
                    return subprocess.CompletedProcess(
                        argv, 0, "127.0.0.1:11521\n", ""
                    )
                if argv[0] == "mvn":
                    captured["env"] = kwargs["env"]
                    reports = (
                        (
                            "account/target/surefire-reports/"
                            "TEST-com.example.accounts.OracleAccountEquivalenceTests.xml",
                            4,
                        ),
                        (
                            "transfer/target/surefire-reports/"
                            "TEST-com.example.transfer.OracleTransferEquivalenceTests.xml",
                            3,
                        ),
                    )
                    for relative, tests in reports:
                        report = workspace / relative
                        report.parent.mkdir(parents=True)
                        report.write_text(
                            f'<testsuite tests="{tests}" failures="0" '
                            'errors="0" skipped="0"/>',
                            encoding="utf-8",
                        )
                    marker = (
                        "CLOUDBANK_EQUIVALENCE_CONTRACT="
                        "account-success:conserved;invalid:no-mutation;"
                        "funds:no-mutation;failure:restored;transfer-invalid:400;"
                        "transfer-auth:403;transfer-success:200\n"
                    )
                    return subprocess.CompletedProcess(argv, 0, marker, "")
                if argv[:2] == ["docker", "rm"]:
                    return subprocess.CompletedProcess(argv, 0, "", "")
                return subprocess.CompletedProcess(argv, 1, "", "unexpected command")

            result = _oracle_lane(workspace, HEX_B, fake_run, lambda _: None)
            self.assertEqual("passed", result["status"])
            env = captured["env"]
            self.assertIsInstance(env, dict)
            self.assertEqual("ACCOUNT", env["SPRING_DATASOURCE_USERNAME"])
            self.assertEqual("system", env["LIQUIBASE_DATASOURCE_USERNAME"])
            self.assertEqual(
                env["SPRING_DATASOURCE_PASSWORD"],
                env["LIQUIBASE_DATASOURCE_PASSWORD"],
            )
            self.assertEqual(
                {"application": True, "migration": True},
                result["identity_login_checks"],
            )
            self.assertTrue(result["aq_privilege_bootstrap"])
            exec_calls = captured["exec_calls"]
            self.assertIsInstance(exec_calls, list)
            bootstrap_calls = [
                call
                for call in exec_calls
                if call[0][-1] == "sqlplus -L -s / as sysdba"
            ]
            self.assertEqual(1, len(bootstrap_calls))

    def test_aq_bootstrap_is_fixed_bounded_and_pdb_scoped(self) -> None:
        self.assertEqual(
            (
                "DBMS_AQ",
                "DBMS_AQADM",
                "DBMS_AQIN",
                "DBMS_AQJMS",
                "DBMS_AQJMS_INTERNAL",
            ),
            ORACLE_AQ_PACKAGES,
        )
        captured: dict[str, object] = {}

        def fake_run(
            argv: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            captured["argv"] = argv
            captured["input"] = kwargs["input"]
            return subprocess.CompletedProcess(
                argv, 0, "CLOUDBANK_ORACLE_AQ_BOOTSTRAP_OK\n", ""
            )

        self.assertTrue(_bootstrap_oracle_aq_privileges("fixed-container", fake_run))
        self.assertEqual("sqlplus -L -s / as sysdba", captured["argv"][-1])
        script = captured["input"]
        self.assertIsInstance(script, str)
        self.assertIn("ALTER SESSION SET CONTAINER=FREEPDB1;", script)
        self.assertEqual(5, script.count(" TO SYSTEM WITH GRANT OPTION;"))
        for package in ORACLE_AQ_PACKAGES:
            self.assertEqual(
                1,
                script.count(
                    f"GRANT EXECUTE ON SYS.{package} TO SYSTEM WITH GRANT OPTION;"
                ),
            )
        self.assertNotIn("ACCOUNT", script)
        self.assertNotIn("password", script.lower())

        def failed_run(
            argv: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                argv, 1, "CLOUDBANK_ORACLE_AQ_BOOTSTRAP_OK\n", "hidden"
            )

        self.assertFalse(
            _bootstrap_oracle_aq_privileges("fixed-container", failed_run)
        )

    def test_oracle_lane_fails_closed_without_bootstrap_and_identity_proofs(
        self,
    ) -> None:
        lane = passed_lane("oracle", HEX_B)
        self.assertTrue(_lane_passed(lane, "oracle", HEX_B))
        lane["aq_privilege_bootstrap"] = False
        self.assertFalse(_lane_passed(lane, "oracle", HEX_B))
        lane["aq_privilege_bootstrap"] = True
        lane["identity_login_checks"] = {
            "application": True,
            "migration": False,
        }
        self.assertFalse(_lane_passed(lane, "oracle", HEX_B))

        postgres = passed_lane("postgresql", HEX_C)
        self.assertTrue(_lane_passed(postgres, "postgresql", HEX_C))

    def test_database_diagnostic_exposes_only_allowlisted_codes_and_changesets(
        self,
    ) -> None:
        root = ET.fromstring(
            """
<testsuite>
  <testcase name="contextFailure">
    <error type="java.lang.IllegalStateException">
Migration failed for changeset db/changelog/txeventq.sql::1::account:
ORA-01031: hidden detail password=should-not-leak
Caused by: ORA-00942: hidden detail
Migration failed for changeset db/changelog/unsafe.sql::steal::attacker:
ORA-ABCDE: not a valid code
    </error>
  </testcase>
</testsuite>
""".strip()
        )
        codes, changesets = _safe_database_diagnostics(root)
        self.assertEqual(["ORA-00942", "ORA-01031"], codes)
        self.assertEqual(
            [{"file": "db/changelog/txeventq.sql", "id": "1"}],
            changesets,
        )
        rendered = json.dumps({"codes": codes, "changesets": changesets})
        self.assertNotIn("hidden detail", rendered)
        self.assertNotIn("should-not-leak", rendered)
        self.assertNotIn("unsafe.sql", rendered)

    def test_surefire_report_takes_precedence_and_exposes_nested_types_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            report = (
                workspace
                / "account/target/surefire-reports"
                / "TEST-com.example.accounts.OracleAccountEquivalenceTests.xml"
            )
            report.parent.mkdir(parents=True)
            report.write_text(
                """
<testsuite tests="4" failures="0" errors="4" skipped="0">
  <testcase name="contextFailure">
    <error type="java.lang.IllegalStateException">hidden
Caused by: org.springframework.beans.factory.BeanCreationException: hidden
Caused by: java.sql.SQLException: password=should-not-leak
    </error>
  </testcase>
  <testcase name="unsafe">
    <error type="token=should-not-leak">hidden</error>
  </testcase>
</testsuite>
""".strip(),
                encoding="utf-8",
            )

            def fake_run(
                argv: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(
                    argv,
                    1,
                    "maven-checkstyle-plugin password=should-not-leak",
                    "token=should-not-leak",
                )

            result = _test_result(workspace, "oracle", HEX_B, {}, fake_run)
            self.assertEqual("test", result["failure_phase"])
            self.assertEqual(1, result["test_reports_present"])
            self.assertEqual(
                [
                    "java.lang.IllegalStateException",
                    "java.sql.SQLException",
                    "org.springframework.beans.factory.BeanCreationException",
                ],
                result["exception_types"],
            )
            rendered = json.dumps(result, sort_keys=True)
            self.assertNotIn("should-not-leak", rendered)
            self.assertNotIn("BeanCreationException: hidden", rendered)

        checkstyle = subprocess.CompletedProcess(
            ["mvn"], 1, "maven-checkstyle-plugin", ""
        )
        self.assertEqual("checkstyle", _failure_phase(checkstyle, 0))
        self.assertEqual("test", _failure_phase(checkstyle, 1))

    def test_failure_diagnostic_emits_only_bounded_classifications(self) -> None:
        oracle = passed_lane("oracle", HEX_B)
        oracle.update(
            {
                "status": "failed",
                "errors": 2,
                "maven_exit_code": 1,
                "failure_phase": "test",
                "failed_tests": [
                    {
                        "name": "password=should-not-leak",
                        "type": "java.lang.IllegalStateException",
                    },
                    {
                        "name": "unsafe",
                        "type": "token=should-not-leak",
                    },
                ],
                "raw_stdout": "secret=should-not-leak",
                "database_error_codes": [
                    "ORA-01031",
                    "ORA-ABCDE",
                    "password=should-not-leak",
                ],
                "liquibase_changesets": [
                    {"file": "db/changelog/txeventq.sql", "id": "1"},
                    {"file": "db/changelog/unsafe.sql", "id": "secret"},
                    {"file": "db/changelog/table.sql", "id": "bad value"},
                ],
                "identity_login_checks": {
                    "application": True,
                    "migration": False,
                    "password": "should-not-leak",
                },
                "aq_privilege_bootstrap": True,
            }
        )
        postgres = passed_lane("postgresql", HEX_C)
        postgres["failure_phase"] = ["password=should-not-leak"]
        diagnostic = equivalence_failure_diagnostic(
            {"oracle_lane": oracle, "postgresql_lane": postgres}, HEX_B, HEX_C
        )
        self.assertEqual(["oracle-lane"], diagnostic["failed_checks"])
        self.assertEqual("test", diagnostic["oracle"]["failure_phase"])
        self.assertEqual(
            ["java.lang.IllegalStateException"],
            diagnostic["oracle"]["exception_types"],
        )
        self.assertEqual(
            ["ORA-01031"], diagnostic["oracle"]["database_error_codes"]
        )
        self.assertEqual(
            [{"file": "db/changelog/txeventq.sql", "id": "1"}],
            diagnostic["oracle"]["liquibase_changesets"],
        )
        self.assertEqual(
            {"application": True, "migration": False},
            diagnostic["oracle"]["identity_login_checks"],
        )
        self.assertTrue(diagnostic["oracle"]["aq_privilege_bootstrap"])
        self.assertTrue(diagnostic["cross_lane_observation_match"])
        self.assertEqual("invalid", diagnostic["postgresql"]["failure_phase"])
        self.assertFalse(diagnostic["raw_output_persisted"])
        self.assertFalse(diagnostic["credentials_persisted"])
        rendered = json.dumps(diagnostic, sort_keys=True)
        self.assertNotIn("should-not-leak", rendered)
        self.assertNotIn("raw_stdout", rendered)

    def test_committed_artifacts_are_deterministic_and_fail_closed(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        readiness = readiness_receipt(ROOT)
        self.assertTrue(readiness["contract_complete"])
        self.assertFalse(readiness["native_oracle_lane_observed"])
        self.assertFalse(readiness["oracle_postgresql_equivalent"])
        self.assertFalse(readiness["production_ready"])

    def test_shared_contract_has_seven_exact_normalized_observations(self) -> None:
        contract = observation_contract()
        self.assertEqual(7, contract["scenario_count"])
        self.assertEqual(OBSERVATION_SHA256, contract["marker_sha256"])
        self.assertEqual("exact-normalized-observation-marker", contract["comparison_policy"])
        acceptance = equivalence_contract(ROOT)
        self.assertEqual(EXPECTED_TESTS, acceptance["tests_per_lane"])
        self.assertEqual(["oracle", "postgresql"], acceptance["required_lanes"])
        self.assertTrue(acceptance["eligible_claim"]["oracle_postgresql_equivalent"])
        self.assertFalse(
            acceptance["eligible_claim"]["exact_internal_implementation_equivalent"]
        )

    def test_plan_binds_all_four_isolated_test_templates(self) -> None:
        plan = execution_plan(ROOT)
        self.assertEqual(4, len(plan["patches"]))
        self.assertEqual(changed_paths(), sorted(item["path"] for item in plan["patches"]))
        self.assertEqual("sequential-database-lanes", plan["runtime_order"])
        for template in (ROOT / OUTPUT_ROOT / "patches").glob("*.java"):
            self.assertTrue(
                template.read_text(encoding="utf-8").startswith(
                    "// Copyright (c) 2023, Oracle and/or its affiliates.\n"
                )
            )

    def test_ledger_exposes_implementation_and_observation_differences(self) -> None:
        entries = {item["capability"]: item for item in compatibility_ledger()["entries"]}
        self.assertEqual(
            "intentional-implementation-change",
            entries["source-lra-compensation-target-atomic-rollback"]["classification"],
        )
        self.assertEqual(
            "observable-difference",
            entries["oracle-zero-amount-failure-journal"]["classification"],
        )
        self.assertEqual(
            "partially-observed",
            entries["source-transfer-http-runtime"]["classification"],
        )
        self.assertFalse(compatibility_ledger()["whole_application_equivalent"])

    @unittest.skipUnless(SOURCE.is_dir(), "pinned CloudBank source is unavailable")
    def test_materialization_preserves_source_and_creates_both_lanes(self) -> None:
        source_head = (SOURCE / ".git/HEAD").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            oracle, postgres = materialize_workspaces(ROOT, SOURCE, Path(directory) / "work")
            for lane, workspace in (("oracle", oracle), ("postgresql", postgres)):
                for relative in TEST_PATCHES[lane]:
                    self.assertTrue((workspace / relative).is_file())
            self.assertIn("oracle", str(oracle))
            self.assertIn("postgresql", str(postgres))
        self.assertEqual(source_head, (SOURCE / ".git/HEAD").read_bytes())

    @patch(
        "lightyear_data.cloudbank_oracle_equivalence.validate_ms57_receipt",
        return_value=[],
    )
    @patch(
        "lightyear_data.cloudbank_oracle_equivalence.validate_ms60_receipt",
        return_value=[],
    )
    @patch("lightyear_data.cloudbank_oracle_equivalence.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_oracle_equivalence.materialize_workspaces")
    def test_execution_closes_only_bounded_equivalence(
        self, materialize: object, _source: object, _ms60: object, _ms57: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = (output / "oracle", output / "postgresql")
            receipt = execute_equivalence(
                ROOT,
                ROOT,
                ms57_receipt(),
                ms60_receipt(),
                output,
                KEY,
                "unit-test",
                "ms61-unit-run",
                oracle_runner=lambda _workspace, image: passed_lane("oracle", image),
                postgres_runner=lambda _workspace, image: passed_lane("postgresql", image),
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["oracle_postgresql_equivalent"])
            self.assertTrue(receipt["customer_equivalence_inherited_from_ms57"])
            self.assertFalse(receipt["exact_internal_implementation_equivalent"])
            self.assertFalse(receipt["oracle_integrated_http_wave_observed"])
            self.assertFalse(receipt["production_identity_qualified"])
            self.assertFalse(receipt["whole_application_equivalent"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-oracle-equivalence-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-oracle-equivalence-receipt-claims-invalid", errors)

    @patch(
        "lightyear_data.cloudbank_oracle_equivalence.validate_ms57_receipt",
        return_value=[],
    )
    @patch(
        "lightyear_data.cloudbank_oracle_equivalence.validate_ms60_receipt",
        return_value=[],
    )
    @patch("lightyear_data.cloudbank_oracle_equivalence.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_oracle_equivalence.materialize_workspaces")
    def test_failed_comparison_writes_only_safe_aggregate_diagnostics(
        self, materialize: object, _source: object, _ms60: object, _ms57: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = (output / "oracle", output / "postgresql")
            failed = passed_lane("postgresql", HEX_C)
            failed["status"] = "failed"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_equivalence(
                    ROOT,
                    ROOT,
                    ms57_receipt(),
                    ms60_receipt(),
                    output,
                    KEY,
                    "unit-test",
                    "ms61-failed-run",
                    oracle_runner=lambda _workspace, image: passed_lane("oracle", image),
                    postgres_runner=lambda _workspace, _image: failed,
                )
            diagnostic = (output / "cloudbank-oracle-postgresql-equivalence.failure.json")
            text = diagnostic.read_text(encoding="utf-8")
            self.assertNotIn("synthetic-ms61-token", text)
            self.assertNotIn("raw_stdout", text)

    def test_launchers_schemas_and_verification_integration_exist(self) -> None:
        for relative in (
            "cloudbank-oracle-equivalence.sh",
            "cloudbank-oracle-equivalence.ps1",
            "tools/cloudbank_oracle_equivalence.py",
            "reference-estates/cloudbank/schema/oracle-postgresql-equivalence-readiness.schema.json",
            "reference-estates/cloudbank/schema/oracle-postgresql-equivalence-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        powershell = (ROOT / "cloudbank-oracle-equivalence.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-FactoryDarkPython", powershell)
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        self.assertIn("cloudbank-oracle-equivalence.sh materialize", workflow)
        self.assertIn("OracleAccountEquivalenceTests", workflow)
        self.assertIn("PostgreSqlAccountEquivalenceTests", workflow)
        tool = (ROOT / "tools/cloudbank_oracle_equivalence.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("DIAGNOSTIC_MARKER", tool)
        self.assertTrue(DIAGNOSTIC_MARKER.endswith("="))


if __name__ == "__main__":
    unittest.main()
