from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from lightyear_common.io import write_json, write_text

from .cloudbank_baseline import ORACLE_IMAGE, PINNED_SUBTREE
from .cloudbank_customer_postgres import POSTGRES_IMAGE
from .cloudbank_dark_factory import (
    FACTORY_RECEIPT_TYPE,
    PATCHES,
    _container_port,
    _inspect_image,
    _run,
    _wait_oracle,
    _wait_postgres,
    validate_factory_receipt,
    validate_source_patch_inputs,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.57.0"
OUTPUT_ROOT = Path("factory/cloudbank/customer-production-qualification")
PATCH_ROOT = OUTPUT_ROOT / "patches"
RECEIPT_TYPE = "lightyear-cloudbank-customer-production-qualification-execution"
RECEIPT_NAME = "cloudbank-customer-production-qualification.receipt.json"
FAILURE_REPORT_NAME = "cloudbank-customer-production-qualification.failure.json"
QUALIFICATION_MARKER = (
    "http:pass;authn:pass;authz:pass;errors:pass;isolation:pass;rollback:pass"
)
QUALIFICATION_MARKER_SHA256 = hashlib.sha256(QUALIFICATION_MARKER.encode()).hexdigest()
EXPECTED_TESTS = 5
PROFILE_ROWS = 10_000
HEX_64 = re.compile(r"^[0-9a-f]{64}$")

ROOT_ORACLE_DEPENDENCY = """        <dependency>
            <groupId>com.oracle.database.spring</groupId>
            <artifactId>oracle-spring-boot-starter-ucp</artifactId>
            <version>${oracle-springboot-starter.version}</version>
            <type>pom</type>
        </dependency>
"""

COMMON_DEPENDENCY = """        <dependency>
            <groupId>com.example</groupId>
            <artifactId>common</artifactId>
            <version>${project.version}</version>
        </dependency>
"""

COMMON_WITH_ORACLE_EXCLUSION = """        <dependency>
            <groupId>com.example</groupId>
            <artifactId>common</artifactId>
            <version>${project.version}</version>
            <exclusions>
                <exclusion>
                    <groupId>com.oracle.database.spring</groupId>
                    <artifactId>oracle-spring-boot-starter-ucp</artifactId>
                </exclusion>
            </exclusions>
        </dependency>
"""

SECURITY_TEST_DEPENDENCY = """        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
"""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return _sha256_bytes(raw)


def synthetic_profile() -> dict[str, Any]:
    rows = []
    for index in range(1, PROFILE_ROWS + 1):
        name = f"Customer {index:05d}"
        if index % 997 == 0:
            name = "N" * 40
        email = None if index % 10 == 0 else f"user{index:05d}@example.test"
        if index % 809 == 0:
            email = "e" * 27 + "@example.test"
        details = None if index % 7 == 0 else f"Synthetic segment {index % 23:02d}"
        if index % 613 == 0:
            details = "D" * 4000
        if index % 503 == 0:
            details = ""
        rows.append(
            {
                "customer_id": f"cust-{index:05d}",
                "customer_name": name,
                "customer_email": email,
                "customer_other_details": details,
                "role": "ADMIN" if index % 100 == 0 else "USER",
            }
        )
    return seal(
        {
            "schema_version": "1.0",
            "profile_type": "lightyear-cloudbank-customer-production-shaped-synthetic-profile",
            "release": RELEASE,
            "generation": {
                "algorithm": "deterministic-customer-boundary-v1",
                "row_count": PROFILE_ROWS,
                "raw_rows_persisted": False,
                "production_data_used": False,
            },
            "dataset_sha256": _stable_hash(rows),
            "metrics": {
                "distinct_customer_ids": len({row["customer_id"] for row in rows}),
                "null_email_count": sum(row["customer_email"] is None for row in rows),
                "null_details_count": sum(row["customer_other_details"] is None for row in rows),
                "empty_details_count": sum(row["customer_other_details"] == "" for row in rows),
                "admin_role_count": sum(row["role"] == "ADMIN" for row in rows),
                "maximum_name_characters": max(len(row["customer_name"]) for row in rows),
                "maximum_email_characters": max(
                    len(row["customer_email"] or "") for row in rows
                ),
                "maximum_details_characters": max(
                    len(row["customer_other_details"] or "") for row in rows
                ),
                "boundary_name_rows": sum(len(row["customer_name"]) == 40 for row in rows),
                "boundary_email_rows": sum(
                    len(row["customer_email"] or "") == 40 for row in rows
                ),
                "boundary_details_rows": sum(
                    len(row["customer_other_details"] or "") == 4000 for row in rows
                ),
            },
            "limitations": [
                "This is deterministic synthetic shape evidence, not sampled production data.",
                "Customer authorization is required before profiling any real data.",
                "Volume, skew, NLS, privacy, retention, and workload rates require customer observation.",
            ],
        }
    )


def migration_rehearsal() -> dict[str, Any]:
    initial = {
        "cust-001": {"name": "Alice", "email": "alice@example.test"},
        "cust-002": {"name": "Alicia", "email": "ops@example.test"},
        "cust-003": {"name": "Bob", "email": None},
        "cust-004": {"name": "Zed", "email": "zed@elsewhere.test"},
    }
    operations = [
        ("insert", "cust-005", None, {"name": "Uma", "email": "uma@example.test"}),
        ("update", "cust-001", initial["cust-001"], {"name": "Alice", "email": "new@example.test"}),
        ("delete", "cust-003", initial["cust-003"], None),
        ("insert", "cust-006", None, {"name": "Kai", "email": None}),
        ("update", "cust-002", initial["cust-002"], {"name": "Alicia", "email": "a@example.test"}),
    ]
    state = copy.deepcopy(initial)
    events = []
    previous = None
    checkpoint_sha256 = None
    for sequence, (operation, customer_id, before, after) in enumerate(operations, 1):
        if before is not None and state.get(customer_id) != before:
            raise ValueError("cloudbank-production-qualification-rehearsal-before-image-drift")
        if operation in {"insert", "update"}:
            state[customer_id] = copy.deepcopy(after)
        else:
            state.pop(customer_id)
        event = seal(
            {
                "sequence": sequence,
                "operation": operation,
                "customer_id_sha256": _stable_hash(customer_id),
                "before_sha256": _stable_hash(before) if before is not None else None,
                "after_sha256": _stable_hash(after) if after is not None else None,
                "previous_event_sha256": previous,
                "evidence_class": "simulated",
            }
        )
        events.append(event)
        previous = event["content_sha256"]
        if sequence == 2:
            checkpoint_sha256 = _stable_hash(state)
    pre_cutover = copy.deepcopy(state)
    faulted = copy.deepcopy(pre_cutover)
    faulted["fault-row"] = {"name": "Injected failure", "email": None}
    restored = copy.deepcopy(pre_cutover)
    return seal(
        {
            "schema_version": "1.0",
            "rehearsal_type": "lightyear-cloudbank-customer-offline-migration-rehearsal",
            "release": RELEASE,
            "scope": "synthetic-customer-state-only",
            "journal": {
                "events": len(events),
                "inserts": 2,
                "updates": 2,
                "deletes": 1,
                "head_sha256": events[-1]["content_sha256"],
                "event_sha256": [event["content_sha256"] for event in events],
            },
            "checkpoint": {
                "after_sequence": 2,
                "state_sha256": checkpoint_sha256,
                "resume_count": 1,
                "duplicate_replay_rejected": True,
            },
            "cutover": {
                "barrier_reconciled": True,
                "source_state_sha256": _stable_hash(pre_cutover),
                "target_state_sha256": _stable_hash(pre_cutover),
                "production_authorized": False,
            },
            "rollback": {
                "fault_injected": True,
                "faulted_state_sha256": _stable_hash(faulted),
                "pre_cutover_state_sha256": _stable_hash(pre_cutover),
                "restored_state_sha256": _stable_hash(restored),
                "exact": restored == pre_cutover,
            },
            "checks": {
                "event_chain_complete": all(
                    event["previous_event_sha256"]
                    == (events[index - 1]["content_sha256"] if index else None)
                    for index, event in enumerate(events)
                ),
                "checkpoint_resume_exact": checkpoint_sha256 is not None,
                "cutover_barrier_reconciled": True,
                "rollback_exact": restored == pre_cutover,
            },
            "evidence_class": "offline-simulated-rehearsal",
            "native_cdc_observed": False,
            "production_cutover_authorized": False,
            "production_ready": False,
        }
    )


def packaging_contract() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-customer-postgresql-packaging",
            "release": RELEASE,
            "required_checks": [
                "maven-package-exit-zero",
                "spring-boot-executable-jar",
                "oracle-runtime-library-count-zero",
                "postgresql-driver-present",
            ],
            "oracle_library_markers": [
                "ojdbc",
                "oraclepki",
                "osdt_cert",
                "osdt_core",
                "ucp-",
            ],
            "oci_image_build_observed": False,
            "image_scan_observed": False,
            "production_deployment_observed": False,
        }
    )


def transformation_plan(project_root: Path) -> dict[str, Any]:
    test_path = project_root / PATCH_ROOT / "CustomerProductionQualificationTests.java"
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-customer-production-qualification-transformation",
            "release": RELEASE,
            "source_workcell": "MS-56",
            "target_paths": sorted(
                set(PATCHES)
                | {
                    "pom.xml",
                    "customer/src/test/java/com/example/customer/CustomerProductionQualificationTests.java",
                }
            ),
            "instrumentation": {
                "spring_security_test_dependency": _stable_hash(SECURITY_TEST_DEPENDENCY),
                "qualification_test_sha256": _sha256(test_path),
            },
            "dependency_cleanup": {
                "path": "pom.xml",
                "removed_dependency": "com.oracle.database.spring:oracle-spring-boot-starter-ucp",
                "removed_block_sha256": _stable_hash(ROOT_ORACLE_DEPENDENCY),
                "common_transitive_exclusion_sha256": _stable_hash(COMMON_WITH_ORACLE_EXCLUSION),
            },
            "limits": {
                "application_modules": ["customer"],
                "other_runtime_modules_changed": 0,
                "production_data_allowed": False,
            },
        }
    )


def qualification_contract(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-customer-production-readiness-qualification",
            "release": RELEASE,
            "requires": {
                "signed_ms56_receipt": True,
                "same_evidence_key": True,
                "exact_pinned_source": True,
                "immutable_database_images_from_ms56": True,
            },
            "native_dual_lane": {
                "test_class": "com.example.customer.CustomerProductionQualificationTests",
                "tests_per_lane": EXPECTED_TESTS,
                "marker_sha256": QUALIFICATION_MARKER_SHA256,
                "gates": [
                    "HTTP authentication",
                    "owner/admin authorization",
                    "HTTP error and mutation status",
                    "concurrent read-committed isolation",
                    "rollback and commit visibility",
                    "maximum declared column lengths",
                ],
            },
            "bindings": {
                "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
                "synthetic_profile_sha256": synthetic_profile()["content_sha256"],
                "migration_rehearsal_sha256": migration_rehearsal()["content_sha256"],
                "packaging_contract_sha256": packaging_contract()["content_sha256"],
            },
            "claim_boundary": {
                "customer_service_production_readiness": "bounded-qualification-only",
                "native_cdc_observed": False,
                "oci_image_built": False,
                "production_data_observed": False,
                "whole_cloudbank_equivalent": False,
                "migration_complete": False,
                "production_ready": False,
            },
        }
    )


def readiness_receipt(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-customer-production-qualification-readiness",
            "release": RELEASE,
            "qualification_contract_sha256": qualification_contract(project_root)["content_sha256"],
            "status": "ready-for-operator-ms56-receipt",
            "contract_complete": True,
            "native_dual_run_observed": False,
            "http_contract_observed": False,
            "transaction_isolation_observed": False,
            "executable_jar_observed": False,
            "offline_migration_rehearsal_complete": True,
            "production_shaped_synthetic_profile_complete": True,
            "native_cdc_observed": False,
            "oci_image_built": False,
            "production_data_observed": False,
            "whole_cloudbank_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def build_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "qualification-contract.json": qualification_contract(project_root),
        "transformation-plan.json": transformation_plan(project_root),
        "synthetic-profile.json": synthetic_profile(),
        "migration-rehearsal.json": migration_rehearsal(),
        "packaging-contract.json": packaging_contract(),
        "readiness.receipt.json": readiness_receipt(project_root),
    }


def validate_artifacts(project_root: Path) -> list[str]:
    errors = []
    root = project_root / OUTPUT_ROOT
    for name, expected in build_artifacts(project_root).items():
        path = root / name
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"cloudbank-production-qualification-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-production-qualification-artifact-drift:{name}")
    receipt = readiness_receipt(project_root)
    if any(
        receipt.get(name) is not False
        for name in (
            "native_dual_run_observed",
            "production_data_observed",
            "whole_cloudbank_equivalent",
            "migration_complete",
            "production_ready",
        )
    ):
        errors.append("cloudbank-production-qualification-readiness-overclaims")
    rehearsal = migration_rehearsal()
    if not all(rehearsal["checks"].values()) or rehearsal["production_ready"] is not False:
        errors.append("cloudbank-production-qualification-rehearsal-invalid")
    return sorted(set(errors))


def _replace_once(text: str, before: str, after: str, code: str) -> str:
    if text.count(before) != 1:
        raise ValueError(code)
    return text.replace(before, after, 1)


def _instrument_customer_pom(path: Path, target: bool) -> None:
    text = path.read_text(encoding="utf-8")
    if target:
        text = _replace_once(
            text,
            COMMON_DEPENDENCY,
            COMMON_WITH_ORACLE_EXCLUSION,
            "cloudbank-production-qualification-common-dependency-drift",
        )
    text = _replace_once(
        text,
        "    </dependencies>\n",
        SECURITY_TEST_DEPENDENCY + "    </dependencies>\n",
        "cloudbank-production-qualification-customer-pom-drift",
    )
    write_text(path, text)


def _materialize_workspaces(project_root: Path, source_root: Path, root: Path) -> tuple[Path, Path]:
    source = source_root / PINNED_SUBTREE
    oracle = root / "oracle"
    postgres = root / "postgresql"
    ignored = shutil.ignore_patterns("target", "*.pyc", "__pycache__")
    shutil.copytree(source, oracle, ignore=ignored)
    shutil.copytree(source, postgres, ignore=ignored)

    _instrument_customer_pom(oracle / "customer/pom.xml", False)
    for relative, (template, expected_source) in PATCHES.items():
        destination = postgres / relative
        if _sha256(destination) != expected_source:
            raise ValueError(f"cloudbank-production-qualification-source-drift:{relative}")
        shutil.copyfile(
            project_root / "factory/cloudbank/customer-postgresql/patches" / template,
            destination,
        )
    root_pom = postgres / "pom.xml"
    root_text = _replace_once(
        root_pom.read_text(encoding="utf-8"),
        ROOT_ORACLE_DEPENDENCY,
        "",
        "cloudbank-production-qualification-root-pom-drift",
    )
    write_text(root_pom, root_text)
    _instrument_customer_pom(postgres / "customer/pom.xml", True)

    test_template = project_root / PATCH_ROOT / "CustomerProductionQualificationTests.java"
    for workspace in (oracle, postgres):
        target = workspace / "customer/src/test/java/com/example/customer/CustomerProductionQualificationTests.java"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(test_template, target)
    return oracle, postgres


def _maven_test_result(
    workspace: Path,
    lane: str,
    env: dict[str, str],
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    result = run(
        [
            "mvn",
            "-pl",
            "customer",
            "-am",
            "-Dtest=CustomerProductionQualificationTests",
            "-Dsurefire.failIfNoSpecifiedTests=false",
            f"-Dcloudbank.qualification.lane={lane}",
            "test",
        ],
        cwd=workspace,
        env=env,
        timeout=900,
    )
    report = workspace / (
        "customer/target/surefire-reports/"
        "TEST-com.example.customer.CustomerProductionQualificationTests.xml"
    )
    totals = {"tests": -1, "failures": -1, "errors": -1, "skipped": -1}
    failed_tests: list[dict[str, str]] = []
    report_text = ""
    if report.is_file():
        report_text = report.read_text(encoding="utf-8", errors="replace")
        root = ET.parse(report).getroot()
        totals = {name: int(root.attrib.get(name, "-1")) for name in totals}
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
    marker = f"CLOUDBANK_PRODUCTION_QUALIFICATION={QUALIFICATION_MARKER}"
    marker_stdout_count = result.stdout.count(marker)
    marker_report_count = report_text.count(marker)
    marker_observed = (
        marker_stdout_count in {0, 1}
        and marker_report_count in {0, 1}
        and max(marker_stdout_count, marker_report_count) == 1
    )
    passed = (
        result.returncode == 0
        and marker_observed
        and totals == {"tests": EXPECTED_TESTS, "failures": 0, "errors": 0, "skipped": 0}
    )
    return {
        "lane": lane,
        "status": "passed" if passed else "failed",
        **totals,
        "maven_exit_code": result.returncode,
        "marker_sha256": QUALIFICATION_MARKER_SHA256 if marker_observed else None,
        "marker_stdout_count": marker_stdout_count,
        "marker_report_count": marker_report_count,
        "test_report_present": report.is_file(),
        "failed_tests": failed_tests,
        "failure_phase": None if passed else _maven_failure_phase(result, report.is_file()),
        "stdout_sha256": _sha256_bytes(result.stdout.encode()),
        "stderr_sha256": _sha256_bytes(result.stderr.encode()),
        "raw_output_persisted": False,
    }


def _maven_failure_phase(
    result: subprocess.CompletedProcess[str], test_report_present: bool = False
) -> str:
    output = f"{result.stdout}\n{result.stderr}"
    if "maven-checkstyle-plugin" in output or "Checkstyle violation" in output:
        return "checkstyle"
    if "maven-compiler-plugin" in output or "COMPILATION ERROR" in output:
        return "compilation"
    if "Could not resolve dependencies" in output or "Failed to collect dependencies" in output:
        return "dependency-resolution"
    if test_report_present or "maven-surefire-plugin" in output:
        return "test"
    return "maven-command"


def _package_result(
    workspace: Path,
    env: dict[str, str],
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    result = run(
        [
            "mvn",
            "-pl",
            "customer",
            "-am",
            "-DskipTests",
            "-Djkube.skip=true",
            "-Ddependency-check.skip=true",
            "package",
        ],
        cwd=workspace,
        env=env,
        timeout=900,
    )
    jar = workspace / "customer/target/customer-0.0.1-SNAPSHOT.jar"
    libraries: list[str] = []
    executable = False
    if result.returncode == 0 and zipfile.is_zipfile(jar):
        with zipfile.ZipFile(jar) as archive:
            names = archive.namelist()
            libraries = [Path(name).name.lower() for name in names if name.startswith("BOOT-INF/lib/")]
            executable = "BOOT-INF/classes/com/example/customer/CustomerApplication.class" in names
    markers = packaging_contract()["oracle_library_markers"]
    oracle_libraries = sorted(
        name for name in libraries if any(marker in name for marker in markers)
    )
    postgres_libraries = sorted(name for name in libraries if name.startswith("postgresql-"))
    passed = (
        result.returncode == 0
        and jar.is_file()
        and executable
        and not oracle_libraries
        and len(postgres_libraries) == 1
    )
    return {
        "status": "passed" if passed else "failed",
        "maven_exit_code": result.returncode,
        "jar_sha256": _sha256(jar) if jar.is_file() else None,
        "jar_size_bytes": jar.stat().st_size if jar.is_file() else 0,
        "spring_boot_executable": executable,
        "runtime_library_count": len(libraries),
        "oracle_runtime_library_count": len(oracle_libraries),
        "postgresql_driver_count": len(postgres_libraries),
        "oracle_runtime_libraries": oracle_libraries,
        "postgresql_drivers": postgres_libraries,
        "failure_phase": None if passed else _maven_failure_phase(result),
        "stdout_sha256": _sha256_bytes(result.stdout.encode()),
        "stderr_sha256": _sha256_bytes(result.stderr.encode()),
        "raw_output_persisted": False,
    }


def _write_failure_report(
    output_root: Path,
    run_id: str,
    oracle_lane: Mapping[str, Any],
    postgres_lane: Mapping[str, Any],
    package: Mapping[str, Any],
) -> Path:
    failure = seal(
        {
            "schema_version": "1.0",
            "report_type": "lightyear-cloudbank-customer-production-qualification-failure",
            "release": RELEASE,
            "run_id": run_id,
            "status": "failed-bounded-qualification",
            "oracle_lane": dict(oracle_lane),
            "postgresql_lane": dict(postgres_lane),
            "packaging": dict(package),
            "security": {
                "raw_maven_output_persisted": False,
                "credentials_persisted": False,
                "production_data_persisted": False,
            },
        }
    )
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / FAILURE_REPORT_NAME
    write_json(path, failure)
    return path


def _lane_passed(lane: Mapping[str, Any], name: str, image_id: str) -> bool:
    return (
        lane.get("lane") == name
        and lane.get("status") == "passed"
        and lane.get("tests") == EXPECTED_TESTS
        and all(lane.get(field) == 0 for field in ("failures", "errors", "skipped"))
        and lane.get("maven_exit_code") == 0
        and lane.get("marker_sha256") == QUALIFICATION_MARKER_SHA256
        and lane.get("database_image_id_sha256") == image_id
        and HEX_64.fullmatch(str(lane.get("stdout_sha256", ""))) is not None
        and HEX_64.fullmatch(str(lane.get("stderr_sha256", ""))) is not None
        and lane.get("raw_output_persisted") is False
    )


def _package_passed(package: Mapping[str, Any]) -> bool:
    return (
        package.get("status") == "passed"
        and package.get("maven_exit_code") == 0
        and package.get("spring_boot_executable") is True
        and package.get("oracle_runtime_library_count") == 0
        and package.get("postgresql_driver_count") == 1
        and HEX_64.fullmatch(str(package.get("jar_sha256", ""))) is not None
        and HEX_64.fullmatch(str(package.get("stdout_sha256", ""))) is not None
        and HEX_64.fullmatch(str(package.get("stderr_sha256", ""))) is not None
        and package.get("raw_output_persisted") is False
    )


def _postgresql_lane(
    workspace: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]] = _run,
    pause: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _inspect_image(POSTGRES_IMAGE, image_id, run)
    name = "lightyear-cb57-pg-" + uuid.uuid4().hex[:10]
    password = "Ly" + secrets.token_hex(12) + "A1"
    started = run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            "-p", "127.0.0.1::5432", "--read-only", "--user", "70:70",
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
        raise ValueError("cloudbank-production-qualification-postgresql-start-failed")
    try:
        _wait_postgres(name, run, pause)
        port = _container_port(name, 5432, run)
        url = f"jdbc:postgresql://127.0.0.1:{port}/cloudbank"
        env = {
            **os.environ,
            "SPRING_DATASOURCE_URL": url,
            "SPRING_DATASOURCE_USERNAME": "postgres",
            "SPRING_DATASOURCE_PASSWORD": password,
            "SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT": "org.hibernate.dialect.PostgreSQLDialect",
            "LIQUIBASE_DATASOURCE_URL": url,
            "LIQUIBASE_DATASOURCE_USERNAME": "postgres",
            "LIQUIBASE_DATASOURCE_PASSWORD": password,
            "EUREKA_CLIENT_ENABLED": "false",
            "SPRING_CLOUD_DISCOVERY_ENABLED": "false",
            "CLOUDBANK_SECURITY_REQUIRE_INTERNAL_TOKEN": "false",
        }
        lane = _maven_test_result(workspace, "postgresql", env, run)
        lane["database_image_id_sha256"] = image_id
        package = _package_result(workspace, env, run)
        return lane, package
    finally:
        password = ""
        run(["docker", "rm", "-f", name], timeout=30)


def _oracle_lane(
    workspace: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]] = _run,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    _inspect_image(ORACLE_IMAGE, image_id, run)
    name = "lightyear-cb57-oracle-" + uuid.uuid4().hex[:10]
    password = "Ly" + secrets.token_hex(12) + "A1"
    started = run(
        [
            "docker", "run", "-d", "--name", name,
            "-p", "127.0.0.1::1521", "--pids-limit", "512",
            "--memory", "4g", "--cpus", "2.0", "--shm-size", "1g",
            "-e", f"ORACLE_PASSWORD={password}",
            "-e", "APP_USER=CUSTOMER", "-e", f"APP_USER_PASSWORD={password}",
            f"sha256:{image_id}",
        ],
        timeout=120,
    )
    if started.returncode:
        raise ValueError("cloudbank-production-qualification-oracle-start-failed")
    try:
        _wait_oracle(name, run, pause)
        port = _container_port(name, 1521, run)
        url = f"jdbc:oracle:thin:@127.0.0.1:{port}/FREEPDB1"
        env = {
            **os.environ,
            "SPRING_DATASOURCE_URL": url,
            "SPRING_DATASOURCE_USERNAME": "CUSTOMER",
            "SPRING_DATASOURCE_PASSWORD": password,
            "LIQUIBASE_DATASOURCE_URL": url,
            "LIQUIBASE_DATASOURCE_USERNAME": "CUSTOMER",
            "LIQUIBASE_DATASOURCE_PASSWORD": password,
            "EUREKA_CLIENT_ENABLED": "false",
            "SPRING_CLOUD_DISCOVERY_ENABLED": "false",
            "CLOUDBANK_SECURITY_REQUIRE_INTERNAL_TOKEN": "false",
        }
        lane = _maven_test_result(workspace, "oracle", env, run)
        lane["database_image_id_sha256"] = image_id
        return lane
    finally:
        password = ""
        run(["docker", "rm", "-f", name], timeout=30)


def execute_qualification(
    project_root: Path,
    source_root: Path,
    ms56_receipt: Mapping[str, Any],
    output_root: Path,
    key: str,
    signer: str,
    run_id: str | None = None,
    oracle_runner: Callable[[Path, str], dict[str, Any]] | None = None,
    postgres_runner: Callable[[Path, str], tuple[dict[str, Any], dict[str, Any]]] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    report = progress or (lambda message: None)
    report("Validating the MS #57 contract, pinned source, and signed MS #56 receipt")
    resolved_source = source_root.resolve()
    resolved_output = output_root.resolve()
    if resolved_output == resolved_source or resolved_source in resolved_output.parents:
        raise ValueError("cloudbank-production-qualification-output-inside-source")
    errors = validate_artifacts(project_root)
    errors.extend(validate_source_patch_inputs(source_root))
    errors.extend(validate_factory_receipt(ms56_receipt, key, project_root))
    if errors:
        raise ValueError(",".join(sorted(set(errors))))
    if ms56_receipt.get("receipt_type") != FACTORY_RECEIPT_TYPE:
        raise ValueError("cloudbank-production-qualification-ms56-receipt-required")
    oracle_image_id = str(ms56_receipt.get("oracle_image_id_sha256", ""))
    postgres_image_id = str(ms56_receipt.get("postgresql_image_id_sha256", ""))
    if not HEX_64.fullmatch(oracle_image_id) or not HEX_64.fullmatch(postgres_image_id):
        raise ValueError("cloudbank-production-qualification-image-identity-invalid")
    run_name = run_id or f"cloudbank-customer-qualification-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    with tempfile.TemporaryDirectory(prefix="lightyear-cloudbank-57-") as directory:
        report("Creating isolated Oracle and PostgreSQL qualification workspaces")
        oracle_workspace, postgres_workspace = _materialize_workspaces(
            project_root, source_root, Path(directory)
        )
        report("Running the Oracle HTTP and transaction lane; startup can take several minutes")
        oracle_lane = (
            oracle_runner(oracle_workspace, oracle_image_id)
            if oracle_runner
            else _oracle_lane(oracle_workspace, oracle_image_id)
        )
        report("Running the PostgreSQL HTTP and transaction lane, then inspecting the executable JAR")
        postgres_lane, package = (
            postgres_runner(postgres_workspace, postgres_image_id)
            if postgres_runner
            else _postgresql_lane(postgres_workspace, postgres_image_id)
        )
    if not (
        _lane_passed(oracle_lane, "oracle", oracle_image_id)
        and _lane_passed(postgres_lane, "postgresql", postgres_image_id)
        and _package_passed(package)
    ):
        report(
            "Oracle lane: "
            f"status={oracle_lane.get('status')} tests={oracle_lane.get('tests')} "
            f"failures={oracle_lane.get('failures')} errors={oracle_lane.get('errors')} "
            f"phase={oracle_lane.get('failure_phase')}"
        )
        report(
            "PostgreSQL lane: "
            f"status={postgres_lane.get('status')} tests={postgres_lane.get('tests')} "
            f"failures={postgres_lane.get('failures')} errors={postgres_lane.get('errors')} "
            f"phase={postgres_lane.get('failure_phase')}"
        )
        report(
            "Packaging: "
            f"status={package.get('status')} executable={package.get('spring_boot_executable')} "
            f"oracle-libraries={package.get('oracle_runtime_library_count')} "
            f"postgresql-drivers={package.get('postgresql_driver_count')} "
            f"phase={package.get('failure_phase')}"
        )
        failure_path = _write_failure_report(
            resolved_output, run_name, oracle_lane, postgres_lane, package
        )
        report(f"Safe diagnostics written to {failure_path}")
        raise ValueError("cloudbank-production-qualification-acceptance-failed")
    report("All native gates passed; signing the bounded qualification receipt")
    receipt = sign(
        {
            "schema_version": "1.0",
            "receipt_type": RECEIPT_TYPE,
            "release": RELEASE,
            "run_id": run_name,
            "source_ms56_receipt_sha256": ms56_receipt["content_sha256"],
            "qualification_contract_sha256": qualification_contract(project_root)["content_sha256"],
            "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
            "synthetic_profile_sha256": synthetic_profile()["content_sha256"],
            "migration_rehearsal_sha256": migration_rehearsal()["content_sha256"],
            "packaging_contract_sha256": packaging_contract()["content_sha256"],
            "oracle_image_id_sha256": oracle_image_id,
            "postgresql_image_id_sha256": postgres_image_id,
            "oracle_lane": oracle_lane,
            "postgresql_lane": postgres_lane,
            "packaging": package,
            "status": "passed-bounded-customer-production-readiness-qualification",
            "http_contract_observed": True,
            "transaction_isolation_observed": True,
            "executable_jar_observed": True,
            "oracle_runtime_dependencies_removed_from_target": True,
            "offline_migration_rehearsal_complete": True,
            "production_shaped_synthetic_profile_complete": True,
            "native_cdc_observed": False,
            "oci_image_built": False,
            "production_data_observed": False,
            "whole_cloudbank_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
            "security": {
                "source_checkout_mutated": False,
                "raw_maven_output_persisted": False,
                "credentials_persisted": False,
                "production_data_persisted": False,
                "database_ports_loopback_only": True,
            },
        },
        key,
        signer,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / RECEIPT_NAME, receipt)
    return receipt


def validate_execution_receipt(
    receipt: Mapping[str, Any], key: str, project_root: Path
) -> list[str]:
    errors = []
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-production-qualification-receipt-identity-invalid")
    if receipt.get("status") != "passed-bounded-customer-production-readiness-qualification":
        errors.append("cloudbank-production-qualification-receipt-status-invalid")
    if receipt.get("content_sha256") != content_hash(dict(receipt)):
        errors.append("cloudbank-production-qualification-receipt-content-hash-invalid")
    if not key or not verify_signature(dict(receipt), key):
        errors.append("cloudbank-production-qualification-receipt-signature-invalid")
    expected = {
        "qualification_contract_sha256": qualification_contract(project_root)["content_sha256"],
        "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
        "synthetic_profile_sha256": synthetic_profile()["content_sha256"],
        "migration_rehearsal_sha256": migration_rehearsal()["content_sha256"],
        "packaging_contract_sha256": packaging_contract()["content_sha256"],
    }
    if any(receipt.get(name) != value for name, value in expected.items()):
        errors.append("cloudbank-production-qualification-receipt-binding-invalid")
    hash_fields = (
        "source_ms56_receipt_sha256",
        "oracle_image_id_sha256",
        "postgresql_image_id_sha256",
    )
    if any(not HEX_64.fullmatch(str(receipt.get(name, ""))) for name in hash_fields):
        errors.append("cloudbank-production-qualification-receipt-hash-identity-invalid")
    for lane_name in ("oracle_lane", "postgresql_lane"):
        lane = receipt.get(lane_name, {})
        name = lane_name.removesuffix("_lane")
        if not _lane_passed(lane, name, str(receipt.get(f"{name}_image_id_sha256", ""))):
            errors.append(f"cloudbank-production-qualification-receipt-lane-invalid:{lane_name}")
    package = receipt.get("packaging", {})
    if not _package_passed(package):
        errors.append("cloudbank-production-qualification-receipt-packaging-invalid")
    required_true = (
        "http_contract_observed",
        "transaction_isolation_observed",
        "executable_jar_observed",
        "oracle_runtime_dependencies_removed_from_target",
        "offline_migration_rehearsal_complete",
        "production_shaped_synthetic_profile_complete",
    )
    required_false = (
        "native_cdc_observed",
        "oci_image_built",
        "production_data_observed",
        "whole_cloudbank_equivalent",
        "migration_complete",
        "production_ready",
    )
    if any(receipt.get(name) is not True for name in required_true) or any(
        receipt.get(name) is not False for name in required_false
    ):
        errors.append("cloudbank-production-qualification-receipt-claims-invalid")
    security = receipt.get("security", {})
    if security != {
        "source_checkout_mutated": False,
        "raw_maven_output_persisted": False,
        "credentials_persisted": False,
        "production_data_persisted": False,
        "database_ports_loopback_only": True,
    }:
        errors.append("cloudbank-production-qualification-receipt-security-invalid")
    forbidden = {"password", "secret", "token", "credential", "raw_stdout", "raw_stderr"}

    def inspect(value: Any, parent: str = "") -> None:
        if isinstance(value, dict):
            for name, child in value.items():
                lowered = str(name).lower()
                if any(marker in lowered for marker in forbidden) and child not in (False, None):
                    if not lowered.endswith("_persisted"):
                        errors.append(
                            "cloudbank-production-qualification-receipt-forbidden-sensitive-field"
                        )
                inspect(child, lowered)
        elif isinstance(value, list):
            for child in value:
                inspect(child, parent)

    inspect(receipt)
    return sorted(set(errors))
