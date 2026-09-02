from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_data.cloudbank_baseline import ORACLE_IMAGE, ORACLE_RECEIPT_TYPE, build_plan, oracle_runtime_plan
from lightyear_data.cloudbank_customer_postgres import (
    POSTGRES_IMAGE,
    RECEIPT_TYPE as POSTGRES_RECEIPT_TYPE,
    behavior_contract,
    compatibility_ledger,
    source_contract,
    target_mapping,
)
from lightyear_data.cloudbank_dark_factory import (
    FACTORY_RECEIPT_TYPE,
    LANE_MARKER,
    PATCHES,
    SHARED_CONTRACT_SHA256,
    CloudBankCustomerAgentSet,
    _execute_oracle_lane,
    _execute_postgresql_lane,
    _maven_result,
    _safe_controller_reason,
    _wait_oracle,
    acceptance_contract,
    build_artifacts,
    execute_dark_factory,
    factory_work_order,
    readiness_receipt,
    transformation_plan,
    validate_artifacts,
    validate_factory_receipt,
    validate_source_patch_inputs,
    work_order_template,
)
from lightyear_data.contracts import seal, sign
from lightyear_factory.patches import PatchBroker
from lightyear_factory.workspace import IsolatedWorkspace


ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-test-cloudbank-dark-factory-key"
HEX_A = "a" * 64
HEX_B = "b" * 64


def oracle_receipt() -> dict[str, object]:
    return sign(
        {
            "schema_version": "1.0",
            "receipt_type": ORACLE_RECEIPT_TYPE,
            "release": "0.54.0",
            "source": build_plan()["source"],
            "oracle_runtime_plan_sha256": oracle_runtime_plan()["content_sha256"],
            "build_receipt_sha256": HEX_A,
            "toolchain": {"java_version": "21.0.12", "java_major": 21, "maven_version": "3.9.16"},
            "oracle_image": ORACLE_IMAGE,
            "oracle_image_id_sha256": HEX_A,
            "command": {"argv_sha256": HEX_A, "exit_code": 0, "stdout_sha256": HEX_A, "stderr_sha256": HEX_A},
            "test_results": {"tests": 7, "failures": 0, "errors": 0, "skipped": 0, "classes": 3},
            "status": "passed",
            "security": {"raw_stdout_persisted": False, "raw_stderr_persisted": False, "credentials_persisted": False},
            "source_build_observed": True,
            "oracle_runtime_observed": True,
            "cloudbank_source_baseline_complete": True,
            "customer_service_runtime_observed": False,
            "production_data_observed": False,
            "postgresql_mapping_complete": False,
            "target_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        },
        KEY,
        "unit-test",
    )


def postgres_receipt(source: dict[str, object]) -> dict[str, object]:
    return sign(
        {
            "schema_version": "1.0",
            "receipt_type": POSTGRES_RECEIPT_TYPE,
            "release": "0.55.0",
            "source": source_contract()["source"],
            "source_oracle_receipt_sha256": source["content_sha256"],
            "source_oracle_image_id_sha256": HEX_A,
            "mapping_sha256": target_mapping()["content_sha256"],
            "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            "behavior_contract_sha256": behavior_contract()["content_sha256"],
            "postgresql_image": POSTGRES_IMAGE,
            "postgresql_image_id_sha256": HEX_B,
            "checks": behavior_contract()["required_native_checks"],
            "psql_exit_code": 0,
            "stdout_sha256": HEX_B,
            "stderr_sha256": HEX_B,
            "security": {"raw_stdout_persisted": False, "raw_stderr_persisted": False, "credentials_persisted": False, "production_data_persisted": False},
            "status": "passed-bounded-database-mapping",
            "postgresql_mapping_complete": True,
            "native_postgresql_observed": True,
            "bounded_database_mapping_qualified": True,
            "application_refactored": False,
            "application_equivalent": False,
            "target_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        },
        KEY,
        "unit-test",
    )


def lane(name: str, image: str) -> dict[str, object]:
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


class FakeOrchestrator:
    def __init__(self, source_root: Path, runs_root: Path, agents: object, **kwargs: object) -> None:
        self.runs_root = runs_root

    def run(self, order: object, run_id: str) -> dict[str, object]:
        artifacts = self.runs_root / run_id / "artifacts"
        artifacts.mkdir(parents=True)
        for index, result in enumerate((lane("oracle", HEX_A), lane("postgresql", HEX_B)), 1):
            write_json(
                artifacts / f"{index:04d}-verification-report.json",
                {"content": {"gates": [{"stdout": LANE_MARKER + json.dumps(result, sort_keys=True)}]}},
            )
        return seal(
            {
                "status": "passed",
                "attempts": 1,
                "changed_paths": sorted(PATCHES),
                "run_id": run_id,
            }
        )


class CloudBankDarkFactoryTests(unittest.TestCase):
    def test_contracts_bind_six_exact_generated_edits(self) -> None:
        plan = transformation_plan(ROOT)
        self.assertEqual(6, len(plan["changes"]))
        self.assertEqual(sorted(PATCHES), [item["path"] for item in plan["changes"]])
        self.assertEqual(SHARED_CONTRACT_SHA256, work_order_template(ROOT)["acceptance"]["shared_contract_sha256"])
        self.assertEqual(1, acceptance_contract(ROOT)["required_outcomes"]["attempts"])
        self.assertEqual(sys.executable, factory_work_order(ROOT, HEX_A, HEX_B).gates[0].command[0])
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads((ROOT / "factory/cloudbank/customer-postgresql" / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)

    def test_readiness_does_not_fabricate_the_operator_run(self) -> None:
        receipt = readiness_receipt(ROOT)
        self.assertTrue(receipt["factory_contract_complete"])
        self.assertFalse(receipt["native_dual_run_observed"])
        self.assertFalse(receipt["application_refactored"])
        self.assertFalse(receipt["bounded_customer_application_equivalent"])
        self.assertFalse(receipt["human_promotion_authorized"])
        self.assertFalse(receipt["production_ready"])

    def test_agent_changes_only_the_admitted_paths_and_preserves_source(self) -> None:
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        before = {path: (checkout / "cloudbank-v5" / path).read_bytes() for path in PATCHES}
        with tempfile.TemporaryDirectory() as directory:
            workspace = IsolatedWorkspace(
                checkout / "cloudbank-v5",
                Path(directory) / "workspace",
                tuple(sorted(PATCHES)),
            )
            workspace.create()
            order = factory_work_order(ROOT, HEX_A, HEX_B)
            agent = CloudBankCustomerAgentSet(ROOT)
            context = {"source_excerpts": [], "nodes": [{"id": order.graph_node_ids[0]}]}
            proposal = agent.build(order, agent.plan(order, context), {}, workspace.root, 1)
            change = PatchBroker().apply(order, workspace, proposal["edits"])
            self.assertEqual(6, change["files_changed"])
            self.assertEqual(sorted(PATCHES), [item["path"] for item in change["changes"]])
            for relative, (template, _) in PATCHES.items():
                self.assertEqual(
                    (ROOT / "factory/cloudbank/customer-postgresql/patches" / template).read_bytes(),
                    (workspace.root / relative).read_bytes(),
                )
        self.assertEqual(before, {path: (checkout / "cloudbank-v5" / path).read_bytes() for path in PATCHES})

    def test_shared_maven_evidence_requires_exact_marker_and_two_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                report = workspace / "customer/target/surefire-reports/TEST-com.example.customer.CustomerApplicationTests.xml"
                report.parent.mkdir(parents=True)
                report.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"/>', encoding="utf-8")
                marker = "CLOUDBANK_SHARED_CONTRACT=rows:4;name:2;email:2;case:0;empty:null;crud:pass;default:pass;auth:pass\n"
                return subprocess.CompletedProcess(argv, 0, marker, "")

            result = _maven_result(workspace, "postgresql", {}, fake_run)
            self.assertEqual("passed", result["status"])
            self.assertEqual(2, result["tests"])
            self.assertFalse(result["raw_output_persisted"])

    def test_postgresql_lane_overrides_inherited_oracle_hibernate_dialect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            captured: dict[str, object] = {}

            def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if argv[:3] == ["docker", "image", "inspect"]:
                    return subprocess.CompletedProcess(argv, 0, f"sha256:{HEX_B}\n", "")
                if argv[:2] == ["docker", "run"]:
                    return subprocess.CompletedProcess(argv, 0, "container-id\n", "")
                if argv[:2] == ["docker", "exec"]:
                    return subprocess.CompletedProcess(argv, 0, "1\n", "")
                if argv[:2] == ["docker", "port"]:
                    return subprocess.CompletedProcess(argv, 0, "127.0.0.1:15432\n", "")
                if argv[0] == "mvn":
                    captured["env"] = kwargs["env"]
                    report = workspace / "customer/target/surefire-reports/TEST-com.example.customer.CustomerApplicationTests.xml"
                    report.parent.mkdir(parents=True)
                    report.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"/>', encoding="utf-8")
                    marker = (
                        "CLOUDBANK_SHARED_CONTRACT="
                        "rows:4;name:2;email:2;case:0;empty:null;crud:pass;default:pass;auth:pass\n"
                    )
                    return subprocess.CompletedProcess(argv, 0, marker, "")
                if argv[:2] == ["docker", "rm"]:
                    return subprocess.CompletedProcess(argv, 0, "", "")
                return subprocess.CompletedProcess(argv, 1, "", "unexpected command")

            result = _execute_postgresql_lane(workspace, HEX_B, fake_run, lambda _: None)
            self.assertEqual("passed", result["status"])
            env = captured["env"]
            self.assertIsInstance(env, dict)
            self.assertEqual(
                "org.hibernate.dialect.PostgreSQLDialect",
                env["SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT"],
            )

    def test_oracle_lane_preserves_entrypoint_privilege_transition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            (workspace / "customer/src/test/java/com/example/customer").mkdir(parents=True)
            captured: dict[str, list[str]] = {}

            def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if argv[:3] == ["docker", "image", "inspect"]:
                    return subprocess.CompletedProcess(argv, 0, f"sha256:{HEX_A}\n", "")
                if argv[:2] == ["docker", "run"]:
                    captured["run"] = argv
                    return subprocess.CompletedProcess(argv, 0, "container-id\n", "")
                if argv[:3] == ["docker", "inspect", "--format"]:
                    state = {"Status": "running", "OOMKilled": False}
                    return subprocess.CompletedProcess(argv, 0, json.dumps(state), "")
                if argv[:3] == ["docker", "exec", "-i"]:
                    return subprocess.CompletedProcess(argv, 0, "CLOUDBANK_ORACLE_READY\n", "")
                if argv[:2] == ["docker", "port"]:
                    return subprocess.CompletedProcess(argv, 0, "127.0.0.1:11521\n", "")
                if argv[0] == "mvn":
                    lane_root = Path(kwargs["cwd"])
                    report = (
                        lane_root
                        / "customer/target/surefire-reports/TEST-com.example.customer.CustomerApplicationTests.xml"
                    )
                    report.parent.mkdir(parents=True)
                    report.write_text(
                        '<testsuite tests="2" failures="0" errors="0" skipped="0"/>',
                        encoding="utf-8",
                    )
                    marker = (
                        "CLOUDBANK_SHARED_CONTRACT="
                        "rows:4;name:2;email:2;case:0;empty:null;crud:pass;default:pass;auth:pass\n"
                    )
                    return subprocess.CompletedProcess(argv, 0, marker, "")
                if argv[:2] == ["docker", "rm"]:
                    return subprocess.CompletedProcess(argv, 0, "", "")
                return subprocess.CompletedProcess(argv, 1, "", "unexpected command")

            result = _execute_oracle_lane(workspace, ROOT, HEX_A, fake_run, lambda _: None)
            self.assertEqual("passed", result["status"])
            run_command = captured["run"]
            self.assertNotIn("--rm", run_command)
            self.assertNotIn("no-new-privileges", run_command)
            self.assertEqual("4g", run_command[run_command.index("--memory") + 1])
            self.assertEqual("1g", run_command[run_command.index("--shm-size") + 1])

    def test_controller_reason_preserves_only_safe_factory_codes(self) -> None:
        self.assertEqual(
            "cloudbank-dark-factory-oracle-not-ready",
            _safe_controller_reason(ValueError("cloudbank-dark-factory-oracle-not-ready")),
        )
        self.assertEqual(
            "ValueError",
            _safe_controller_reason(ValueError("cloudbank-dark-factory-password leaked")),
        )

    def test_oracle_wait_uses_customer_sql_probe_and_reports_terminal_state(self) -> None:
        running = json.dumps({"Status": "running", "OOMKilled": False})
        calls: list[tuple[list[str], dict[str, object]]] = []

        def healthy_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((argv, kwargs))
            if argv[:3] == ["docker", "inspect", "--format"]:
                return subprocess.CompletedProcess(argv, 0, running, "")
            return subprocess.CompletedProcess(argv, 0, "CLOUDBANK_ORACLE_READY\n", "")

        _wait_oracle("oracle", healthy_run, lambda _: None)
        sql_call = calls[-1]
        self.assertEqual(["docker", "exec", "-i"], sql_call[0][:3])
        self.assertIn("$APP_USER_PASSWORD", sql_call[0][-1])
        self.assertIn("SELECT 'CLOUDBANK_ORACLE_READY' FROM DUAL", str(sql_call[1]["input"]))

        oom = json.dumps({"Status": "exited", "OOMKilled": True})

        def oom_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, oom, "")

        with self.assertRaisesRegex(ValueError, "oracle-oom-killed"):
            _wait_oracle("oracle", oom_run, lambda _: None)

        exited = json.dumps({"Status": "exited", "OOMKilled": False})

        def exited_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, exited, "")

        with self.assertRaisesRegex(ValueError, "oracle-container-exited"):
            _wait_oracle("oracle", exited_run, lambda _: None)

    def test_receipt_chain_drives_one_bounded_factory_run(self) -> None:
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        source = oracle_receipt()
        target = postgres_receipt(source)
        with tempfile.TemporaryDirectory() as directory:
            receipt = execute_dark_factory(
                ROOT,
                checkout,
                source,
                target,
                Path(directory),
                KEY,
                "unit-test",
                "cloudbank-test-run",
                FakeOrchestrator,
            )
            self.assertEqual(FACTORY_RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["bounded_customer_application_equivalent"])
            self.assertFalse(receipt["target_equivalent"])
            self.assertFalse(receipt["human_promotion_authorized"])
            self.assertEqual([], validate_factory_receipt(receipt, KEY, ROOT))
            self.assertIn(
                "cloudbank-dark-factory-receipt-signature-invalid",
                validate_factory_receipt(receipt, "", ROOT),
            )

            tampered = copy.deepcopy(receipt)
            tampered["postgresql_lane"]["tests"] = 1
            tampered = sign(tampered, KEY, "unit-test")
            self.assertIn(
                "cloudbank-dark-factory-receipt-postgresql-lane-invalid",
                validate_factory_receipt(tampered, KEY, ROOT),
            )
            overclaim = copy.deepcopy(receipt)
            overclaim["production_ready"] = True
            overclaim = sign(overclaim, KEY, "unit-test")
            self.assertIn("cloudbank-dark-factory-receipt-overclaims", validate_factory_receipt(overclaim, KEY, ROOT))

    def test_receipt_chain_and_source_drift_fail_closed(self) -> None:
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        self.assertEqual([], validate_source_patch_inputs(checkout))
        source = oracle_receipt()
        unrelated = oracle_receipt()
        unrelated["run_nonce"] = "different"
        unrelated = sign(unrelated, KEY, "unit-test")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "receipt-chain-invalid"):
                execute_dark_factory(
                    ROOT,
                    checkout,
                    unrelated,
                    postgres_receipt(source),
                    Path(directory),
                    KEY,
                    "unit-test",
                    "cloudbank-test-run",
                    FakeOrchestrator,
                )
        wrong_image = postgres_receipt(source)
        wrong_image["source_oracle_image_id_sha256"] = "c" * 64
        wrong_image = sign(wrong_image, KEY, "unit-test")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "source-image-chain-invalid"):
                execute_dark_factory(
                    ROOT,
                    checkout,
                    source,
                    wrong_image,
                    Path(directory),
                    KEY,
                    "unit-test",
                    "cloudbank-test-run",
                    FakeOrchestrator,
                )

    def test_launchers_schemas_and_operator_boundary_exist(self) -> None:
        self.assertTrue((ROOT / "cloudbank-dark-factory.sh").is_file())
        self.assertTrue((ROOT / "cloudbank-dark-factory.ps1").is_file())
        schemas = sorted((ROOT / "reference-estates/cloudbank/schema").glob("customer-dark-factory-*.schema.json"))
        self.assertEqual(2, len(schemas))
        self.assertTrue(all(json.loads(path.read_text(encoding="utf-8"))["$schema"] for path in schemas))
        readme = (ROOT / "factory/cloudbank/customer-postgresql/README.md").read_text(encoding="utf-8")
        self.assertIn("unchanged customer service", readme)
        self.assertIn("does not authorize promotion", readme)
        source = (ROOT / "src/lightyear_data/cloudbank_dark_factory.py").read_text(encoding="utf-8")
        self.assertIn("POSTGRES_PASSWORD", source)
        self.assertNotIn("POSTGRES_HOST_AUTH_METHOD=trust", source)


if __name__ == "__main__":
    unittest.main()
