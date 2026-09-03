from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Mapping

from lightyear_common.io import write_json

from .cloudbank_baseline import ORACLE_IMAGE, PINNED_SUBTREE
from .cloudbank_customer_postgres import POSTGRES_IMAGE
from .cloudbank_dark_factory import (
    _container_connectivity_args,
    _container_endpoint,
    _inspect_image,
    _wait_oracle,
    _wait_postgres,
)
from .cloudbank_native_wave import (
    RECEIPT_TYPE as MS60_RECEIPT_TYPE,
    materialize_target as materialize_ms60_target,
    validate_execution_receipt as validate_ms60_receipt,
)
from .cloudbank_production_qualification import (
    RECEIPT_TYPE as MS57_RECEIPT_TYPE,
    validate_execution_receipt as validate_ms57_receipt,
)
from .cloudbank_transaction_wave import validate_source
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.61.0"
OUTPUT_ROOT = Path("factory/cloudbank/oracle-equivalence")
PATCH_ROOT = OUTPUT_ROOT / "patches"
RECEIPT_TYPE = "lightyear-cloudbank-oracle-postgresql-equivalence-execution"
RECEIPT_NAME = "cloudbank-oracle-postgresql-equivalence.receipt.json"
FAILURE_NAME = "cloudbank-oracle-postgresql-equivalence.failure.json"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_TESTS = 7
OBSERVATION_CONTRACT = (
    "account-success:conserved;invalid:no-mutation;funds:no-mutation;"
    "failure:restored;transfer-invalid:400;transfer-auth:403;transfer-success:200"
)
OBSERVATION_SHA256 = hashlib.sha256(OBSERVATION_CONTRACT.encode()).hexdigest()
TEST_PATCHES = {
    "oracle": {
        "account/src/test/java/com/example/accounts/OracleAccountEquivalenceTests.java": (
            "OracleAccountEquivalenceTests.java"
        ),
        "transfer/src/test/java/com/example/transfer/OracleTransferEquivalenceTests.java": (
            "OracleTransferEquivalenceTests.java"
        ),
    },
    "postgresql": {
        "account/src/test/java/com/example/accounts/PostgreSqlAccountEquivalenceTests.java": (
            "PostgreSqlAccountEquivalenceTests.java"
        ),
        "transfer/src/test/java/com/example/transfer/PostgreSqlTransferEquivalenceTests.java": (
            "PostgreSqlTransferEquivalenceTests.java"
        ),
    },
}
TEST_CLASSES = {
    "oracle": ("OracleAccountEquivalenceTests", "OracleTransferEquivalenceTests"),
    "postgresql": (
        "PostgreSqlAccountEquivalenceTests",
        "PostgreSqlTransferEquivalenceTests",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def changed_paths() -> list[str]:
    return sorted(
        path
        for patches in TEST_PATCHES.values()
        for path in patches
    )


def observation_contract() -> dict[str, Any]:
    scenarios = [
        ("account-success", "conserved", "paired finalized nonzero journals"),
        ("invalid", "no-mutation", "bad amount rejected before state change"),
        ("funds", "no-mutation", "insufficient balance produces no effective mutation"),
        ("failure", "restored", "compensation or rollback restores both balances"),
        ("transfer-invalid", "400", "facade returns bad request before dependency calls"),
        ("transfer-auth", "403", "facade rejects missing identity before dependency calls"),
        ("transfer-success", "200", "facade completes its normalized orchestration contract"),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-normalized-oracle-postgresql-observation",
            "release": RELEASE,
            "services": ["customer", "account", "transfer"],
            "newly_executed_services": ["account", "transfer"],
            "inherited_customer_gate": "signed-ms57-native-dual-lane",
            "scenario_count": len(scenarios),
            "scenarios": [
                {"id": identifier, "normalized_result": result, "evidence": evidence}
                for identifier, result, evidence in scenarios
            ],
            "marker": OBSERVATION_CONTRACT,
            "marker_sha256": OBSERVATION_SHA256,
            "comparison_policy": "exact-normalized-observation-marker",
        }
    )


def execution_plan(project_root: Path) -> dict[str, Any]:
    patches = []
    for lane, lane_patches in TEST_PATCHES.items():
        for target, template in sorted(lane_patches.items()):
            patches.append(
                {
                    "lane": lane,
                    "path": target,
                    "template": f"patches/{template}",
                    "template_sha256": _sha256(project_root / PATCH_ROOT / template),
                    "operation": "create-in-isolated-workspace",
                }
            )
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-oracle-postgresql-equivalence",
            "release": RELEASE,
            "requires": ["signed-ms57-receipt", "signed-ms60-receipt", "same-evidence-key"],
            "lanes": {
                "oracle": "exact-pinned-source-account-and-transfer",
                "postgresql": "exact-ms60-generated-account-and-transfer-target",
            },
            "patches": patches,
            "stages": [
                "validate-content-addressed-contracts-and-receipts",
                "materialize-isolated-source-and-target-workspaces",
                "run-native-oracle-account-and-source-transfer-contract",
                "run-native-postgresql-account-and-target-transfer-contract",
                "compare-exact-normalized-observation-markers",
                "sign-bounded-equivalence-receipt",
            ],
            "runtime_order": "sequential-database-lanes",
            "source_checkout_mutated": False,
            "production_data": False,
            "production_identity": False,
            "whole_application": False,
        }
    )


def compatibility_ledger() -> dict[str, Any]:
    entries = [
        ("customer-http-and-jdbc", "inherited-equivalent", "signed-ms57"),
        ("successful-value-conservation", "normalized-equivalent", "native-dual-lane"),
        ("invalid-and-insufficient-rejection", "normalized-equivalent", "native-dual-lane"),
        ("source-lra-compensation-target-atomic-rollback", "intentional-implementation-change", "final-state-exact"),
        ("successful-journal-net", "normalized-equivalent", "paired-net-zero"),
        ("oracle-zero-amount-failure-journal", "observable-difference", "target-has-no-effective-mutation"),
        ("target-durable-idempotency", "target-safety-improvement", "signed-ms60"),
        ("source-transfer-http-runtime", "partially-observed", "source-code-orchestration-contract-only"),
        ("production-oauth2-oidc", "not-qualified", "ms62"),
        ("oracle-aq-checks-flow", "not-qualified", "ms63"),
        ("remaining-five-services", "not-qualified", "ms64"),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "ledger_type": "lightyear-cloudbank-oracle-postgresql-equivalence-compatibility",
            "release": RELEASE,
            "entries": [
                {"capability": name, "classification": classification, "evidence": evidence}
                for name, classification, evidence in entries
            ],
            "bounded_business_equivalence_eligible": True,
            "exact_internal_implementation_equivalent": False,
            "whole_application_equivalent": False,
            "production_ready": False,
        }
    )


def equivalence_contract(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-bounded-oracle-postgresql-equivalence",
            "release": RELEASE,
            "bindings": {
                "observation_contract_sha256": observation_contract()["content_sha256"],
                "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
                "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            },
            "required_lanes": ["oracle", "postgresql"],
            "tests_per_lane": EXPECTED_TESTS,
            "required_marker_sha256": OBSERVATION_SHA256,
            "required_database_images": [ORACLE_IMAGE, POSTGRES_IMAGE],
            "required_receipt_chain": [MS57_RECEIPT_TYPE, MS60_RECEIPT_TYPE],
            "eligible_claim": {
                "oracle_postgresql_equivalent": True,
                "equivalence_scope": "bounded-normalized-customer-account-transfer",
                "exact_internal_implementation_equivalent": False,
                "whole_application_equivalent": False,
                "production_ready": False,
            },
        }
    )


def readiness_receipt(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-oracle-postgresql-equivalence-readiness",
            "release": RELEASE,
            "bindings": {
                "observation_contract_sha256": observation_contract()["content_sha256"],
                "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
                "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
                "equivalence_contract_sha256": equivalence_contract(project_root)["content_sha256"],
            },
            "status": "ready-for-signed-ms57-ms60-native-dual-lane",
            "contract_complete": True,
            "native_oracle_lane_observed": False,
            "native_postgresql_lane_observed": False,
            "oracle_postgresql_equivalent": False,
            "exact_internal_implementation_equivalent": False,
            "production_identity_qualified": False,
            "native_messaging_observed": False,
            "remaining_service_workcells_complete": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def build_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "observation-contract.json": observation_contract(),
        "execution-plan.json": execution_plan(project_root),
        "compatibility-ledger.json": compatibility_ledger(),
        "equivalence-contract.json": equivalence_contract(project_root),
        "readiness.receipt.json": readiness_receipt(project_root),
    }


def write_artifacts(project_root: Path) -> None:
    for name, payload in build_artifacts(project_root).items():
        write_json(project_root / OUTPUT_ROOT / name, payload)


def validate_artifacts(project_root: Path) -> list[str]:
    errors: list[str] = []
    for name, expected in build_artifacts(project_root).items():
        try:
            actual = json.loads((project_root / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"cloudbank-oracle-equivalence-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-oracle-equivalence-artifact-drift:{name}")
    readiness = readiness_receipt(project_root)
    false_claims = (
        "native_oracle_lane_observed",
        "native_postgresql_lane_observed",
        "oracle_postgresql_equivalent",
        "exact_internal_implementation_equivalent",
        "production_identity_qualified",
        "native_messaging_observed",
        "remaining_service_workcells_complete",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    )
    if any(readiness.get(name) is not False for name in false_claims):
        errors.append("cloudbank-oracle-equivalence-readiness-overclaims")
    if len(observation_contract()["scenarios"]) != EXPECTED_TESTS:
        errors.append("cloudbank-oracle-equivalence-scenario-count-invalid")
    return sorted(set(errors))


def materialize_workspaces(
    project_root: Path, source_root: Path, output: Path
) -> tuple[Path, Path]:
    if output.exists():
        raise ValueError("cloudbank-oracle-equivalence-output-exists")
    output.mkdir(parents=True)
    source = source_root / PINNED_SUBTREE
    oracle = output / "oracle"
    postgres = output / "postgresql"
    shutil.copytree(
        source,
        oracle,
        ignore=shutil.ignore_patterns("target", "*.pyc", "__pycache__"),
    )
    materialize_ms60_target(project_root, source_root, postgres)
    for lane, workspace in (("oracle", oracle), ("postgresql", postgres)):
        for target, template in TEST_PATCHES[lane].items():
            destination = workspace / target
            if destination.exists():
                raise ValueError(f"cloudbank-oracle-equivalence-target-collision:{target}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_root / PATCH_ROOT / template, destination)
    return oracle, postgres


def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, text=True, capture_output=True, **kwargs)


def _failure_phase(result: subprocess.CompletedProcess[str], reports: int) -> str:
    output = f"{result.stdout}\n{result.stderr}"
    if "maven-checkstyle-plugin" in output or "Checkstyle violation" in output:
        return "checkstyle"
    if "maven-compiler-plugin" in output or "COMPILATION ERROR" in output:
        return "compilation"
    if "Could not resolve dependencies" in output:
        return "dependency-resolution"
    if reports or "maven-surefire-plugin" in output:
        return "test"
    return "maven-command"


def _test_result(
    workspace: Path,
    lane: str,
    image_id: str,
    env: Mapping[str, str],
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    classes = TEST_CLASSES[lane]
    result = run(
        [
            "mvn",
            "-pl",
            "account,transfer",
            "-am",
            "-Dtest=" + ",".join(classes),
            "-Dsurefire.failIfNoSpecifiedTests=false",
            "test",
        ],
        cwd=workspace,
        env=dict(env),
        timeout=1200,
    )
    reports = [
        workspace
        / module
        / "target/surefire-reports"
        / f"TEST-com.example.{package}.{test_class}.xml"
        for module, package, test_class in (
            ("account", "accounts", classes[0]),
            ("transfer", "transfer", classes[1]),
        )
    ]
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    failed_tests: list[dict[str, str]] = []
    report_text = ""
    present = 0
    for report in reports:
        if not report.is_file():
            continue
        present += 1
        text = report.read_text(encoding="utf-8", errors="replace")
        report_text += text
        root = ET.fromstring(text)
        for name in totals:
            totals[name] += int(root.attrib.get(name, "0"))
        for test_case in root.findall(".//testcase"):
            failure = test_case.find("failure")
            failure = failure if failure is not None else test_case.find("error")
            if failure is not None:
                failed_tests.append(
                    {
                        "name": test_case.attrib.get("name", "unknown"),
                        "type": failure.attrib.get("type", "unknown"),
                    }
                )
    marker = f"CLOUDBANK_EQUIVALENCE_CONTRACT={OBSERVATION_CONTRACT}"
    stdout_count = result.stdout.count(marker)
    report_count = report_text.count(marker)
    marker_observed = (
        stdout_count in {0, 1}
        and report_count in {0, 1}
        and max(stdout_count, report_count) == 1
    )
    passed = (
        result.returncode == 0
        and present == 2
        and marker_observed
        and totals == {"tests": EXPECTED_TESTS, "failures": 0, "errors": 0, "skipped": 0}
    )
    return {
        "lane": lane,
        "status": "passed" if passed else "failed",
        **totals,
        "maven_exit_code": result.returncode,
        "database_image_id_sha256": image_id,
        "observation_sha256": OBSERVATION_SHA256 if marker_observed else None,
        "marker_stdout_count": stdout_count,
        "marker_report_count": report_count,
        "test_reports_present": present,
        "failed_tests": failed_tests,
        "failure_phase": None if passed else _failure_phase(result, present),
        "stdout_sha256": _sha256_text(result.stdout),
        "stderr_sha256": _sha256_text(result.stderr),
        "raw_output_persisted": False,
        "synthetic_data_only": True,
    }


def _oracle_lane(
    workspace: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]] = _run,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    _inspect_image(ORACLE_IMAGE, image_id, run)
    name = "lightyear-cb61-oracle-" + uuid.uuid4().hex[:10]
    password = "Ly" + secrets.token_hex(12) + "A1"
    started = run(
        [
            "docker", "run", "-d", "--name", name,
            *_container_connectivity_args(1521), "--pids-limit", "512",
            "--memory", "4g", "--cpus", "2.0", "--shm-size", "1g",
            "-e", f"ORACLE_PASSWORD={password}",
            "-e", "APP_USER=ACCOUNT", "-e", f"APP_USER_PASSWORD={password}",
            f"sha256:{image_id}",
        ],
        timeout=120,
    )
    if started.returncode:
        raise ValueError("cloudbank-oracle-equivalence-oracle-start-failed")
    try:
        _wait_oracle(name, run, pause)
        host, port = _container_endpoint(name, 1521, run)
        url = f"jdbc:oracle:thin:@{host}:{port}/FREEPDB1"
        env = {
            **os.environ,
            "SPRING_DATASOURCE_URL": url,
            "SPRING_DATASOURCE_USERNAME": "ACCOUNT",
            "SPRING_DATASOURCE_PASSWORD": password,
            "LIQUIBASE_DATASOURCE_URL": url,
            "LIQUIBASE_DATASOURCE_USERNAME": "ACCOUNT",
            "LIQUIBASE_DATASOURCE_PASSWORD": password,
            "MP_LRA_COORDINATOR_URL": "http://127.0.0.1:1/lra-coordinator",
            "EUREKA_CLIENT_ENABLED": "false",
            "SPRING_CLOUD_DISCOVERY_ENABLED": "false",
            "SPRING_CLOUD_CONFIG_ENABLED": "false",
        }
        return _test_result(workspace, "oracle", image_id, env, run)
    finally:
        password = ""
        run(["docker", "rm", "-f", name], timeout=30)


def _postgresql_lane(
    workspace: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]] = _run,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    _inspect_image(POSTGRES_IMAGE, image_id, run)
    name = "lightyear-cb61-pg-" + uuid.uuid4().hex[:10]
    password = "Ly" + secrets.token_hex(12) + "A1"
    started = run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            *_container_connectivity_args(5432), "--read-only", "--user", "70:70",
            "--pids-limit", "128", "--memory", "768m", "--cpus", "1.0",
            "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=384m,uid=70,gid=70",
            "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16m,uid=70,gid=70",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m,uid=70,gid=70",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "-e", f"POSTGRES_PASSWORD={password}", "-e", "POSTGRES_DB=cloudbank",
            f"sha256:{image_id}",
        ],
        timeout=120,
    )
    if started.returncode:
        raise ValueError("cloudbank-oracle-equivalence-postgresql-start-failed")
    try:
        _wait_postgres(name, run, pause)
        host, port = _container_endpoint(name, 5432, run)
        url = f"jdbc:postgresql://{host}:{port}/cloudbank"
        env = {
            **os.environ,
            "SPRING_DATASOURCE_URL": url,
            "SPRING_DATASOURCE_USERNAME": "postgres",
            "SPRING_DATASOURCE_PASSWORD": password,
            "LIQUIBASE_DATASOURCE_URL": url,
            "LIQUIBASE_DATASOURCE_USERNAME": "postgres",
            "LIQUIBASE_DATASOURCE_PASSWORD": password,
            "SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT": "org.hibernate.dialect.PostgreSQLDialect",
            "EUREKA_CLIENT_ENABLED": "false",
            "SPRING_CLOUD_DISCOVERY_ENABLED": "false",
            "SPRING_CLOUD_CONFIG_ENABLED": "false",
            "CLOUDBANK_SECURITY_REQUIRE_INTERNAL_TOKEN": "false",
        }
        return _test_result(workspace, "postgresql", image_id, env, run)
    finally:
        password = ""
        run(["docker", "rm", "-f", name], timeout=30)


def _lane_passed(lane: Mapping[str, Any], name: str, image_id: str) -> bool:
    return (
        lane.get("lane") == name
        and lane.get("status") == "passed"
        and lane.get("tests") == EXPECTED_TESTS
        and all(lane.get(field) == 0 for field in ("failures", "errors", "skipped"))
        and lane.get("maven_exit_code") == 0
        and lane.get("database_image_id_sha256") == image_id
        and lane.get("observation_sha256") == OBSERVATION_SHA256
        and lane.get("test_reports_present") == 2
        and lane.get("raw_output_persisted") is False
        and lane.get("synthetic_data_only") is True
    )


def execute_equivalence(
    project_root: Path,
    source_root: Path,
    ms57_receipt: Mapping[str, Any],
    ms60_receipt: Mapping[str, Any],
    output_root: Path,
    key: str,
    signer: str,
    run_id: str | None = None,
    oracle_runner: Callable[[Path, str], dict[str, Any]] | None = None,
    postgres_runner: Callable[[Path, str], dict[str, Any]] | None = None,
    progress: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    progress("Validating MS #61 artifacts, pinned source, and signed MS #57/MS #60 receipts")
    errors = validate_artifacts(project_root)
    errors.extend(validate_source(source_root))
    errors.extend(validate_ms57_receipt(ms57_receipt, key, project_root))
    errors.extend(validate_ms60_receipt(ms60_receipt, key, project_root))
    if ms57_receipt.get("receipt_type") != MS57_RECEIPT_TYPE:
        errors.append("cloudbank-oracle-equivalence-ms57-receipt-required")
    if ms60_receipt.get("receipt_type") != MS60_RECEIPT_TYPE:
        errors.append("cloudbank-oracle-equivalence-ms60-receipt-required")
    if errors:
        raise ValueError(",".join(sorted(set(errors))))
    oracle_image_id = str(ms57_receipt.get("oracle_image_id_sha256", ""))
    postgres_image_id = str(ms60_receipt.get("postgresql_image_id_sha256", ""))
    if not HEX_64.fullmatch(oracle_image_id) or not HEX_64.fullmatch(postgres_image_id):
        raise ValueError("cloudbank-oracle-equivalence-image-identity-invalid")
    if ms57_receipt.get("postgresql_image_id_sha256") != postgres_image_id:
        raise ValueError("cloudbank-oracle-equivalence-postgresql-image-chain-invalid")
    resolved_source = source_root.resolve()
    resolved_output = output_root.resolve()
    if resolved_output == resolved_source or resolved_source in resolved_output.parents:
        raise ValueError("cloudbank-oracle-equivalence-output-inside-source")
    run_name = run_id or (
        "cloudbank-oracle-equivalence-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    )
    workspace_root = resolved_output / "runs" / run_name / "workspace"
    progress("Materializing isolated pinned-source Oracle and generated-target PostgreSQL lanes")
    oracle_workspace, postgres_workspace = materialize_workspaces(
        project_root, source_root, workspace_root
    )
    progress("Running the original Account and Transfer observation contract against native Oracle")
    oracle_lane = (
        oracle_runner(oracle_workspace, oracle_image_id)
        if oracle_runner
        else _oracle_lane(oracle_workspace, oracle_image_id)
    )
    progress("Running the generated Account and Transfer observation contract against PostgreSQL")
    postgres_lane = (
        postgres_runner(postgres_workspace, postgres_image_id)
        if postgres_runner
        else _postgresql_lane(postgres_workspace, postgres_image_id)
    )
    equivalent = (
        _lane_passed(oracle_lane, "oracle", oracle_image_id)
        and _lane_passed(postgres_lane, "postgresql", postgres_image_id)
        and oracle_lane.get("observation_sha256") == postgres_lane.get("observation_sha256")
    )
    if not equivalent:
        failure = seal(
            {
                "schema_version": "1.0",
                "report_type": "lightyear-cloudbank-oracle-postgresql-equivalence-failure",
                "release": RELEASE,
                "run_id": run_name,
                "status": "failed-bounded-equivalence",
                "oracle_lane": oracle_lane,
                "postgresql_lane": postgres_lane,
                "security": {
                    "raw_output_persisted": False,
                    "credentials_persisted": False,
                    "production_data_persisted": False,
                },
            }
        )
        resolved_output.mkdir(parents=True, exist_ok=True)
        write_json(resolved_output / FAILURE_NAME, failure)
        raise ValueError("cloudbank-oracle-equivalence-acceptance-failed")
    progress("Both native lanes matched; signing the bounded normalized equivalence receipt")
    receipt = sign(
        {
            "schema_version": "1.0",
            "receipt_type": RECEIPT_TYPE,
            "release": RELEASE,
            "run_id": run_name,
            "source_ms57_receipt_sha256": ms57_receipt["content_sha256"],
            "source_ms60_receipt_sha256": ms60_receipt["content_sha256"],
            "oracle_image_id_sha256": oracle_image_id,
            "postgresql_image_id_sha256": postgres_image_id,
            "observation_contract_sha256": observation_contract()["content_sha256"],
            "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
            "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            "equivalence_contract_sha256": equivalence_contract(project_root)["content_sha256"],
            "changed_paths": changed_paths(),
            "oracle_lane": oracle_lane,
            "postgresql_lane": postgres_lane,
            "status": "passed-bounded-normalized-customer-account-transfer-equivalence",
            "equivalence_scope": "customer-account-transfer",
            "customer_equivalence_inherited_from_ms57": True,
            "native_oracle_account_state_transitions_observed": True,
            "source_transfer_orchestration_contract_observed": True,
            "native_postgresql_target_requalified": True,
            "oracle_postgresql_equivalent": True,
            "exact_internal_implementation_equivalent": False,
            "oracle_integrated_http_wave_observed": False,
            "production_identity_qualified": False,
            "native_messaging_observed": False,
            "remaining_service_workcells_complete": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
            "security": {
                "source_checkout_mutated": False,
                "synthetic_data_only": True,
                "credentials_persisted": False,
                "raw_maven_output_persisted": False,
                "database_ports_loopback_only": True,
                "human_promotion_authorized": False,
            },
        },
        key,
        signer,
    )
    resolved_output.mkdir(parents=True, exist_ok=True)
    write_json(resolved_output / RECEIPT_NAME, receipt)
    return receipt


def validate_execution_receipt(
    receipt: Mapping[str, Any], key: str, project_root: Path
) -> list[str]:
    errors: list[str] = []
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-oracle-equivalence-receipt-identity-invalid")
    if receipt.get("status") != (
        "passed-bounded-normalized-customer-account-transfer-equivalence"
    ):
        errors.append("cloudbank-oracle-equivalence-receipt-status-invalid")
    if receipt.get("content_sha256") != content_hash(dict(receipt)):
        errors.append("cloudbank-oracle-equivalence-receipt-content-hash-invalid")
    if not key or not verify_signature(dict(receipt), key):
        errors.append("cloudbank-oracle-equivalence-receipt-signature-invalid")
    expected = {
        "observation_contract_sha256": observation_contract()["content_sha256"],
        "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
        "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
        "equivalence_contract_sha256": equivalence_contract(project_root)["content_sha256"],
        "changed_paths": changed_paths(),
    }
    if any(receipt.get(name) != value for name, value in expected.items()):
        errors.append("cloudbank-oracle-equivalence-receipt-binding-invalid")
    for name in (
        "source_ms57_receipt_sha256",
        "source_ms60_receipt_sha256",
        "oracle_image_id_sha256",
        "postgresql_image_id_sha256",
    ):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"cloudbank-oracle-equivalence-receipt-hash-invalid:{name}")
    oracle_id = str(receipt.get("oracle_image_id_sha256", ""))
    postgres_id = str(receipt.get("postgresql_image_id_sha256", ""))
    for name, image_id in (("oracle", oracle_id), ("postgresql", postgres_id)):
        lane = receipt.get(f"{name}_lane")
        if not isinstance(lane, Mapping) or not _lane_passed(lane, name, image_id):
            errors.append(f"cloudbank-oracle-equivalence-receipt-{name}-lane-invalid")
    required_true = (
        "customer_equivalence_inherited_from_ms57",
        "native_oracle_account_state_transitions_observed",
        "source_transfer_orchestration_contract_observed",
        "native_postgresql_target_requalified",
        "oracle_postgresql_equivalent",
    )
    required_false = (
        "exact_internal_implementation_equivalent",
        "oracle_integrated_http_wave_observed",
        "production_identity_qualified",
        "native_messaging_observed",
        "remaining_service_workcells_complete",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    )
    if any(receipt.get(name) is not True for name in required_true) or any(
        receipt.get(name) is not False for name in required_false
    ):
        errors.append("cloudbank-oracle-equivalence-receipt-claims-invalid")
    if receipt.get("equivalence_scope") != "customer-account-transfer":
        errors.append("cloudbank-oracle-equivalence-receipt-scope-invalid")
    errors.extend(validate_artifacts(project_root))
    return sorted(set(errors))
