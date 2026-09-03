from __future__ import annotations

import hashlib
import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Mapping

from lightyear_factory.contracts import WorkOrder
from lightyear_factory.orchestrator import FactoryOrchestrator

from .cloudbank_baseline import (
    ORACLE_IMAGE,
    ORACLE_RECEIPT_TYPE,
    PINNED_SUBTREE,
    validate_execution_receipt as validate_baseline_receipt,
)
from .cloudbank_customer_postgres import (
    POSTGRES_IMAGE,
    RECEIPT_TYPE as POSTGRES_RECEIPT_TYPE,
    behavior_contract,
    target_mapping,
    validate_postgresql_receipt,
    validate_source_files,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.56.0"
OUTPUT_ROOT = Path("factory/cloudbank/customer-postgresql")
PATCH_ROOT = OUTPUT_ROOT / "patches"
FACTORY_RECEIPT_TYPE = "lightyear-cloudbank-customer-dark-factory-execution-receipt"
SHARED_CONTRACT = "rows:4;name:2;email:2;case:0;empty:null;crud:pass;default:pass;auth:pass"
SHARED_CONTRACT_SHA256 = hashlib.sha256(SHARED_CONTRACT.encode("utf-8")).hexdigest()
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
LANE_MARKER = "CLOUDBANK_LANE_RESULT="
ORACLE_READY_ATTEMPTS = 600
ORACLE_READY_MARKER = "CLOUDBANK_ORACLE_READY"

PATCHES = {
    "customer/pom.xml": (
        "customer-pom.xml",
        "8715304d7f327604565c49d7b4e0616150469fe082633ca6487f14b8bf72ca8b",
    ),
    "customer/src/main/resources/application.yaml": (
        "application.yaml",
        "3caa27fae2fcb936947cebb5e660835e09c294395dceb123499b408cfa303dd9",
    ),
    "customer/src/main/resources/db/changelog/table.sql": (
        "table.sql",
        "c7732c5fe70581c94d1d52a646b4b7e772de6404505c08ede08fe9ae9d82d2af",
    ),
    "customer/src/main/resources/db/changelog/data.sql": (
        "data.sql",
        "174524ede252be4a382e916859da12af37127672b92087b2b07302dd2fcbfb1d",
    ),
    "customer/src/main/java/com/example/customer/model/Customers.java": (
        "Customers.java",
        "1e44410b114c5f9ec333b323a8c1b157b1960c81e4a9d8dc8093f556f15914a8",
    ),
    "customer/src/test/java/com/example/customer/CustomerApplicationTests.java": (
        "CustomerApplicationTests.java",
        "584ac017e27dcfdb2dea995dfc944ed15a55f2f331f4955b5cdf5f340bad92c5",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _template_root(project_root: Path) -> Path:
    return project_root / PATCH_ROOT


def transformation_plan(project_root: Path) -> dict[str, Any]:
    root = _template_root(project_root)
    changes = []
    for target in sorted(PATCHES):
        template, source_sha256 = PATCHES[target]
        path = root / template
        changes.append(
            {
                "path": target,
                "source_sha256": source_sha256,
                "template": f"patches/{template}",
                "target_sha256": _sha256(path),
                "classification": "generated-bounded-edit",
            }
        )
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-customer-dark-factory-transformation",
            "release": RELEASE,
            "mapping_sha256": target_mapping()["content_sha256"],
            "behavior_contract_sha256": behavior_contract()["content_sha256"],
            "workcell": "cloudbank-reference:workload:customer-account-management",
            "changes": changes,
            "decisions": [
                "replace the Oracle wallet starter with the PostgreSQL JDBC driver in the customer module",
                "override the inherited Oracle Hibernate dialect and UCP datasource configuration",
                "generate PostgreSQL Liquibase DDL and synthetic bootstrap data from MS #55",
                "map the schema-only ROLE column into the JPA entity",
                "normalize Java empty strings before persistence to preserve Oracle semantics",
                "replace the disabled context test with a shared Oracle/PostgreSQL application contract",
            ],
            "application_refactored": False,
            "native_dual_run_observed": False,
            "production_ready": False,
        }
    )


def work_order_template(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "template_type": "lightyear-cloudbank-customer-dark-factory-work-order",
            "release": RELEASE,
            "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
            "id": "cloudbank-customer-oracle-to-postgresql-v0.56.0",
            "title": "CloudBank customer Oracle-to-PostgreSQL application transformation",
            "goal": "Apply the sealed MS #55 mapping to the customer Spring/JPA service and pass the shared Oracle/PostgreSQL application contract.",
            "scope": {
                "allowed_paths": sorted(PATCHES),
                "graph_node_ids": ["cloudbank-reference:workload:customer-account-management"],
                "source": "complete pinned cloudbank-v5 checkout copied into an isolated workspace",
            },
            "roles": ["controller", "planner", "builder", "failure-analyst", "verifier", "evidence-recorder"],
            "acceptance": {
                "baseline_first": True,
                "max_attempts": 1,
                "source_lane": "shared contract executed on the unchanged Oracle customer service",
                "target_lane": "same shared contract plus ROLE mapping executed on PostgreSQL 16",
                "shared_contract_sha256": SHARED_CONTRACT_SHA256,
            },
            "policy": {
                "audience": "implementer",
                "dependency_resolution_network_allowed": True,
                "max_files_changed": 6,
                "max_patch_bytes": 100_000,
                "max_changed_lines": 1_200,
                "human_promotion_required": True,
            },
            "receipt_inputs": [ORACLE_RECEIPT_TYPE, POSTGRES_RECEIPT_TYPE],
            "claim_boundary": {
                "bounded_customer_application_equivalence": "eligible-only-after-native-dual-run",
                "whole_cloudbank_equivalence": False,
                "production_data_equivalence": False,
                "migration_complete": False,
                "production_ready": False,
            },
        }
    )


def acceptance_contract(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-customer-dark-factory-acceptance",
            "release": RELEASE,
            "work_order_template_sha256": work_order_template(project_root)["content_sha256"],
            "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
            "required_receipts": {
                "oracle_source": ORACLE_RECEIPT_TYPE,
                "postgresql_mapping": POSTGRES_RECEIPT_TYPE,
            },
            "required_outcomes": {
                "factory_status": "passed",
                "attempts": 1,
                "changed_paths": sorted(PATCHES),
                "oracle_lane": {"tests": 2, "shared_contract_sha256": SHARED_CONTRACT_SHA256},
                "postgresql_lane": {"tests": 2, "shared_contract_sha256": SHARED_CONTRACT_SHA256},
            },
            "security": {
                "source_checkout_mutated": False,
                "isolated_workspace_required": True,
                "database_ports": "ephemeral-loopback-only",
                "database_containers": "immutable-image-id-and-ephemeral",
                "raw_maven_output_persisted": False,
                "credentials_persisted": False,
                "synthetic_data_only": True,
                "dependency_resolution_network": "explicitly-allowed-development-boundary",
            },
            "promotion": "human authorization remains mandatory after technical acceptance",
        }
    )


def readiness_receipt(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-customer-dark-factory-readiness",
            "release": RELEASE,
            "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
            "work_order_template_sha256": work_order_template(project_root)["content_sha256"],
            "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
            "gate_status": "ready-to-run-operator-receipts-required",
            "source_oracle_receipt_required": True,
            "postgresql_mapping_receipt_required": True,
            "factory_contract_complete": True,
            "native_dual_run_observed": False,
            "application_refactored": False,
            "bounded_customer_application_equivalent": False,
            "human_promotion_authorized": False,
            "target_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def build_artifacts(project_root: Path) -> dict[str, Any]:
    return {
        "transformation-plan.json": transformation_plan(project_root),
        "work-order.template.json": work_order_template(project_root),
        "acceptance-contract.json": acceptance_contract(project_root),
        "readiness.receipt.json": readiness_receipt(project_root),
    }


def validate_artifacts(project_root: Path) -> list[str]:
    errors: list[str] = []
    root = project_root / OUTPUT_ROOT
    for name, expected in build_artifacts(project_root).items():
        path = root / name
        if not path.is_file():
            errors.append(f"cloudbank-dark-factory-artifact-missing:{name}")
            continue
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"cloudbank-dark-factory-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-dark-factory-artifact-drift:{name}")
    forbidden = ("SuperSecret", "Welcome", "Important Info", "andy@andy.com", "sanjay@sanjay.com", "mark@mark.com")
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".xml", ".yaml", ".sql", ".java", ".md"}:
            text = path.read_text(encoding="utf-8")
            if any(value in text for value in forbidden):
                errors.append(f"cloudbank-dark-factory-sensitive-source-value-persisted:{path.relative_to(root).as_posix()}")
    template_checks = {
        "customer-pom.xml": ("org.postgresql", "<artifactId>postgresql</artifactId>"),
        "application.yaml": ("org.postgresql.Driver", "org.hibernate.dialect.PostgreSQLDialect"),
        "table.sql": ("CREATE SCHEMA IF NOT EXISTS cloudbank_customer", "role VARCHAR(40)"),
        "data.sql": ("TRUNCATE TABLE cloudbank_customer.customers", "NULLIF('', '')"),
        "Customers.java": ('@Table(name = "customers", schema = "cloudbank_customer")', "@PrePersist", 'name = "role"'),
        "CustomerApplicationTests.java": ("CLOUDBANK_SHARED_CONTRACT=", "targetRoleMappingIsExplicit", "HttpStatus.FORBIDDEN"),
    }
    for name, required in template_checks.items():
        path = root / "patches" / name
        if not path.is_file():
            errors.append(f"cloudbank-dark-factory-template-missing:{name}")
            continue
        value = path.read_text(encoding="utf-8")
        if any(marker not in value for marker in required):
            errors.append(f"cloudbank-dark-factory-template-contract-invalid:{name}")
    pom = root / "patches/customer-pom.xml"
    app = root / "patches/application.yaml"
    test = root / "patches/CustomerApplicationTests.java"
    if pom.is_file() and "oracle-spring-boot-starter-wallet" in pom.read_text(encoding="utf-8"):
        errors.append("cloudbank-dark-factory-oracle-wallet-not-removed")
    if app.is_file() and "oracle.jdbc" in app.read_text(encoding="utf-8"):
        errors.append("cloudbank-dark-factory-oracle-driver-not-removed")
    if test.is_file() and "@Disabled" in test.read_text(encoding="utf-8"):
        errors.append("cloudbank-dark-factory-shared-contract-disabled")
    return sorted(set(errors))


def validate_source_patch_inputs(source_root: Path) -> list[str]:
    errors = validate_source_files(source_root)
    subtree = source_root / PINNED_SUBTREE
    for relative, (_, expected) in PATCHES.items():
        path = subtree / relative
        if not path.is_file():
            errors.append(f"cloudbank-dark-factory-source-file-missing:{relative}")
        elif _sha256(path) != expected:
            errors.append(f"cloudbank-dark-factory-source-file-drift:{relative}")
    return sorted(set(errors))


class CloudBankCustomerAgentSet:
    name = "cloudbank-customer-deterministic-generated-worker"

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def plan(self, order: WorkOrder, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": "Apply the sealed six-file customer transformation inside the isolated workspace.",
            "tasks": [
                {
                    "id": "transform-customer-application",
                    "objective": order.goal,
                    "paths": list(order.allowed_paths),
                    "graph_node_ids": list(order.graph_node_ids),
                    "evidence_capsule_ids": [item["capsule_id"] for item in context.get("source_excerpts", [])[:8]],
                }
            ],
            "risks": [
                "The shared parent still supplies Oracle libraries to other CloudBank modules.",
                "Dependency resolution uses an explicitly admitted development network boundary.",
                "One customer workcell cannot establish whole-CloudBank equivalence.",
            ],
        }

    def build(
        self,
        order: WorkOrder,
        plan: dict[str, Any],
        failure: dict[str, Any],
        workspace_root: Path,
        attempt: int,
    ) -> dict[str, Any]:
        edits = []
        for relative, (template, expected_source) in PATCHES.items():
            source = workspace_root / relative
            if _sha256(source) != expected_source:
                return {
                    "summary": "The pinned source no longer matches the sealed transformation.",
                    "edits": [],
                    "blocked_reason": f"source-drift:{relative}",
                }
            edits.append(
                {
                    "path": relative,
                    "find": source.read_text(encoding="utf-8"),
                    "replace": (_template_root(self.project_root) / template).read_text(encoding="utf-8"),
                    "rationale": "Apply the content-addressed MS #56 target template.",
                }
            )
        return {
            "summary": f"Generated {len(edits)} bounded customer-service edits on attempt {attempt}.",
            "edits": edits,
            "blocked_reason": None,
        }

    def analyze_failure(self, order: WorkOrder, verification: dict[str, Any], attempt: int) -> dict[str, Any]:
        failed = [item["id"] for item in verification.get("gates", []) if item.get("status") != "passed"]
        return {
            "summary": "The Oracle source lane established the baseline; the target transformation is still required.",
            "failure_codes": [f"GATE_FAILED:{item}" for item in failed],
            "builder_guidance": "Apply only the sealed MS #56 templates to the six authorized customer-service paths.",
            "risk": "high",
        }

    def drain_evidence(self) -> list[dict[str, Any]]:
        return []

    def intelligence_summary(self) -> dict[str, Any]:
        return {
            "mode": "deterministic-generated-transformation",
            "provider": self.name,
            "model": None,
            "calls": 0,
            "input_bytes": 0,
            "output_bytes": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "cost_estimate_available": True,
            "limitations": ["This run proves the governed workcell mechanics, not model generalization."],
        }


def factory_work_order(project_root: Path, oracle_image_id: str, postgres_image_id: str) -> WorkOrder:
    payload = {
        "schema_version": "1.0",
        "id": "cloudbank-customer-oracle-to-postgresql-v0.56.0",
        "title": "CloudBank customer Oracle-to-PostgreSQL application transformation",
        "goal": "Apply the sealed MS #55 mapping and pass the same application contract on Oracle and PostgreSQL.",
        "non_goals": [
            "Modify the pinned source checkout",
            "Refactor another CloudBank service",
            "Use or compare production data",
            "Authorize promotion or claim whole-CloudBank equivalence",
        ],
        "scope": {
            "allowed_paths": sorted(PATCHES),
            "graph_node_ids": ["cloudbank-reference:workload:customer-account-management"],
        },
        "acceptance": {
            "baseline_first": True,
            "max_attempts": 1,
            "gates": [
                {
                    "id": "cloudbank-customer-native-dual-run",
                    "command": [
                        sys.executable,
                        "-m",
                        "lightyear_data.cloudbank_dark_factory",
                        "gate",
                        "--oracle-image-id-sha256",
                        oracle_image_id,
                        "--postgresql-image-id-sha256",
                        postgres_image_id,
                    ],
                    "timeout_seconds": 1200,
                    "expose_output_to_builder": False,
                }
            ],
        },
        "policy": {
            "audience": "implementer",
            "allow_network": True,
            "max_files_changed": 6,
            "max_patch_bytes": 100_000,
            "max_changed_lines": 1_200,
            "max_context_bytes": 500_000,
            "max_file_bytes": 200_000,
            "max_model_calls": 1,
            "max_model_input_bytes": 10_000,
            "max_model_output_bytes": 10_000,
            "max_model_tokens": 10_000,
            "max_model_cost_usd": 0,
            "max_elapsed_seconds": 2400,
        },
        "metadata": {
            "release": RELEASE,
            "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
            "mapping_sha256": target_mapping()["content_sha256"],
            "success_limitation": "The bounded customer application contract passed on Oracle and PostgreSQL; whole-CloudBank and production equivalence remain unproven.",
        },
    }
    return WorkOrder.from_dict(payload)


def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, text=True, capture_output=True, **kwargs)


def _inspect_image(tag: str, expected: str, run: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    result = run(["docker", "image", "inspect", "--format", "{{.Id}}", tag], timeout=30)
    actual = result.stdout.strip().removeprefix("sha256:")
    if result.returncode or actual != expected:
        raise ValueError(f"cloudbank-dark-factory-image-id-mismatch:{tag}")


def _container_port(name: str, port: int, run: Callable[..., subprocess.CompletedProcess[str]]) -> int:
    result = run(["docker", "port", name, f"{port}/tcp"], timeout=30)
    if result.returncode or not result.stdout.strip():
        raise ValueError("cloudbank-dark-factory-container-port-unavailable")
    value = result.stdout.strip().splitlines()[0].rsplit(":", 1)[-1]
    if not value.isdigit():
        raise ValueError("cloudbank-dark-factory-container-port-invalid")
    return int(value)


def _wait_postgres(name: str, run: Callable[..., subprocess.CompletedProcess[str]], pause: Callable[[float], None]) -> None:
    for _ in range(120):
        ready = run(["docker", "exec", name, "psql", "-U", "postgres", "-d", "cloudbank", "-Atqc", "SELECT 1"], timeout=10)
        if ready.returncode == 0 and ready.stdout.strip() == "1":
            return
        pause(0.5)
    raise ValueError("cloudbank-dark-factory-postgresql-not-ready")


def _wait_oracle(name: str, run: Callable[..., subprocess.CompletedProcess[str]], pause: Callable[[float], None]) -> None:
    for _ in range(ORACLE_READY_ATTEMPTS):
        inspection = run(
            ["docker", "inspect", "--format", "{{json .State}}", name],
            timeout=10,
        )
        if inspection.returncode:
            pause(1)
            continue
        try:
            state = json.loads(inspection.stdout)
        except json.JSONDecodeError:
            pause(1)
            continue
        if state.get("OOMKilled") is True:
            raise ValueError("cloudbank-dark-factory-oracle-oom-killed")
        status = state.get("Status")
        if status in {"dead", "exited"}:
            raise ValueError("cloudbank-dark-factory-oracle-container-exited")
        ready = run(
            [
                "docker", "exec", "-i", name, "bash", "-lc",
                'sqlplus -L -s "$APP_USER"/"$APP_USER_PASSWORD"@//localhost:1521/FREEPDB1',
            ],
            input=(
                "WHENEVER OSERROR EXIT FAILURE\n"
                "WHENEVER SQLERROR EXIT SQL.SQLCODE\n"
                "SET HEADING OFF FEEDBACK OFF PAGESIZE 0 VERIFY OFF ECHO OFF\n"
                f"SELECT '{ORACLE_READY_MARKER}' FROM DUAL;\n"
                "EXIT\n"
            ),
            timeout=20,
        )
        markers = {line.strip() for line in ready.stdout.splitlines()}
        if ready.returncode == 0 and ORACLE_READY_MARKER in markers:
            return
        pause(1)
    raise ValueError("cloudbank-dark-factory-oracle-not-ready")


def _maven_result(workspace: Path, lane: str, env: dict[str, str], run: Callable[..., subprocess.CompletedProcess[str]]) -> dict[str, Any]:
    result = run(
        [
            "mvn",
            "-pl",
            "customer",
            "-Dtest=CustomerApplicationTests",
            f"-Dcloudbank.factory.lane={lane}",
            "test",
        ],
        cwd=workspace,
        env=env,
        timeout=900,
    )
    marker = f"CLOUDBANK_SHARED_CONTRACT={SHARED_CONTRACT}"
    report = workspace / "customer/target/surefire-reports/TEST-com.example.customer.CustomerApplicationTests.xml"
    tests = failures = errors = skipped = -1
    if report.is_file():
        root = ET.parse(report).getroot()
        tests = int(root.attrib.get("tests", "-1"))
        failures = int(root.attrib.get("failures", "-1"))
        errors = int(root.attrib.get("errors", "-1"))
        skipped = int(root.attrib.get("skipped", "-1"))
    passed = (
        result.returncode == 0
        and result.stdout.count(marker) == 1
        and tests == 2
        and failures == errors == skipped == 0
    )
    return {
        "lane": lane,
        "status": "passed" if passed else "failed",
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "shared_contract_sha256": SHARED_CONTRACT_SHA256 if marker in result.stdout else None,
        "maven_exit_code": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
        "raw_output_persisted": False,
    }


def _execute_postgresql_lane(
    workspace: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
    pause: Callable[[float], None],
) -> dict[str, Any]:
    _inspect_image(POSTGRES_IMAGE, image_id, run)
    name = "lightyear-cb-factory-pg-" + uuid.uuid4().hex[:10]
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
        raise ValueError("cloudbank-dark-factory-postgresql-start-failed")
    try:
        _wait_postgres(name, run, pause)
        port = _container_port(name, 5432, run)
        url = f"jdbc:postgresql://127.0.0.1:{port}/cloudbank"
        env = {
            **os.environ,
            "SPRING_DATASOURCE_URL": url,
            "SPRING_DATASOURCE_USERNAME": "postgres",
            "SPRING_DATASOURCE_PASSWORD": password,
            # common.yaml is shared with the Oracle source estate and imports an
            # Oracle Hibernate dialect. Environment properties outrank imported
            # configuration, so the target lane must explicitly select the
            # PostgreSQL dialect rather than querying Oracle catalog views.
            "SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT": "org.hibernate.dialect.PostgreSQLDialect",
            "LIQUIBASE_DATASOURCE_URL": url,
            "LIQUIBASE_DATASOURCE_USERNAME": "postgres",
            "LIQUIBASE_DATASOURCE_PASSWORD": password,
            "EUREKA_CLIENT_ENABLED": "false",
            "SPRING_CLOUD_DISCOVERY_ENABLED": "false",
            "CLOUDBANK_SECURITY_REQUIRE_INTERNAL_TOKEN": "false",
        }
        result = _maven_result(workspace, "postgresql", env, run)
        result["database_image_id_sha256"] = image_id
        return result
    finally:
        password = ""
        run(["docker", "rm", "-f", name], timeout=30)


def _execute_oracle_lane(
    workspace: Path,
    project_root: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
    pause: Callable[[float], None],
) -> dict[str, Any]:
    _inspect_image(ORACLE_IMAGE, image_id, run)
    name = "lightyear-cb-factory-oracle-" + uuid.uuid4().hex[:10]
    password = "Ly" + secrets.token_hex(12) + "A1"
    started = run(
        [
            # Oracle's entrypoint performs a privilege transition, so this lane
            # deliberately matches the repository's proven Oracle runner: keep
            # the container inspectable on failure and do not set
            # no-new-privileges. The finally block still removes it.
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
        raise ValueError("cloudbank-dark-factory-oracle-start-failed")
    try:
        _wait_oracle(name, run, pause)
        port = _container_port(name, 1521, run)
        with tempfile.TemporaryDirectory(prefix="lightyear-cloudbank-oracle-lane-") as directory:
            lane_root = Path(directory) / "cloudbank-v5"
            shutil.copytree(workspace, lane_root, ignore=shutil.ignore_patterns("target", "*.pyc", "__pycache__"))
            test_path = lane_root / "customer/src/test/java/com/example/customer/CustomerApplicationTests.java"
            test_path.write_text(
                (_template_root(project_root) / "CustomerApplicationTests.java").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
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
            result = _maven_result(lane_root, "oracle", env, run)
        result["database_image_id_sha256"] = image_id
        return result
    finally:
        password = ""
        run(["docker", "rm", "-f", name], timeout=30)


def _target_files_match(workspace: Path, project_root: Path) -> bool:
    return all(
        _sha256(workspace / relative) == _sha256(_template_root(project_root) / template)
        for relative, (template, _) in PATCHES.items()
    )


def _source_files_match(workspace: Path) -> bool:
    return all(_sha256(workspace / relative) == expected for relative, (_, expected) in PATCHES.items())


def run_gate(
    workspace: Path,
    project_root: Path,
    oracle_image_id: str,
    postgres_image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]] = _run,
    pause: Callable[[float], None] = time.sleep,
) -> tuple[int, dict[str, Any]]:
    if _source_files_match(workspace):
        result = _execute_oracle_lane(workspace, project_root, oracle_image_id, run, pause)
        return (10 if result["status"] == "passed" else 11), result
    if _target_files_match(workspace, project_root):
        result = _execute_postgresql_lane(workspace, postgres_image_id, run, pause)
        return (0 if result["status"] == "passed" else 12), result
    return 13, {"lane": "unknown", "status": "failed", "reason": "workspace-content-not-admitted"}


def _parse_lane_result(text: str) -> dict[str, Any]:
    matches = [line[len(LANE_MARKER):] for line in text.splitlines() if line.startswith(LANE_MARKER)]
    if len(matches) != 1:
        raise ValueError("cloudbank-dark-factory-lane-marker-invalid")
    return json.loads(matches[0])


def _diagnostic_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and -1 <= value <= 10_000:
        return value
    return None


def _lane_acceptance_diagnostic(
    lane: Mapping[str, Any], expected_lane: str
) -> dict[str, Any]:
    status = lane.get("status")
    return {
        "lane_match": lane.get("lane") == expected_lane,
        "status": status if status in {"passed", "failed"} else "invalid",
        "tests": _diagnostic_int(lane.get("tests")),
        "failures": _diagnostic_int(lane.get("failures")),
        "errors": _diagnostic_int(lane.get("errors")),
        "skipped": _diagnostic_int(lane.get("skipped")),
        "maven_exit_code": _diagnostic_int(lane.get("maven_exit_code")),
        "shared_contract_match": lane.get("shared_contract_sha256") == SHARED_CONTRACT_SHA256,
    }


def _acceptance_diagnostic(
    factory_receipt: Mapping[str, Any],
    expected_paths: list[str],
    source_lane: Mapping[str, Any],
    target_lane: Mapping[str, Any],
) -> dict[str, Any]:
    checks = {
        "factory-status": factory_receipt.get("status") == "passed",
        "factory-attempts": factory_receipt.get("attempts") == 1,
        "changed-paths": factory_receipt.get("changed_paths") == expected_paths,
        "oracle-lane": source_lane.get("lane") == "oracle",
        "postgresql-lane": target_lane.get("lane") == "postgresql",
        "oracle-status": source_lane.get("status") == "passed",
        "postgresql-status": target_lane.get("status") == "passed",
        "oracle-contract": source_lane.get("shared_contract_sha256") == SHARED_CONTRACT_SHA256,
        "postgresql-contract": target_lane.get("shared_contract_sha256") == SHARED_CONTRACT_SHA256,
    }
    return {
        "failed_checks": sorted(name for name, passed in checks.items() if not passed),
        "factory": {
            "status_match": checks["factory-status"],
            "attempts": _diagnostic_int(factory_receipt.get("attempts")),
            "changed_paths_match": checks["changed-paths"],
        },
        "oracle": _lane_acceptance_diagnostic(source_lane, "oracle"),
        "postgresql": _lane_acceptance_diagnostic(target_lane, "postgresql"),
        "raw_output_persisted": False,
        "credentials_persisted": False,
    }


def execute_dark_factory(
    project_root: Path,
    source_root: Path,
    oracle_receipt: Mapping[str, Any],
    postgres_receipt: Mapping[str, Any],
    output_root: Path,
    key: str,
    signer: str,
    run_id: str | None = None,
    orchestrator_factory: Callable[..., Any] = FactoryOrchestrator,
) -> dict[str, Any]:
    errors = validate_source_patch_inputs(source_root)
    errors.extend(validate_baseline_receipt(oracle_receipt, key))
    errors.extend(validate_postgresql_receipt(postgres_receipt, key))
    if errors:
        raise ValueError(",".join(sorted(set(errors))))
    if oracle_receipt.get("receipt_type") != ORACLE_RECEIPT_TYPE:
        raise ValueError("cloudbank-dark-factory-oracle-receipt-required")
    if postgres_receipt.get("receipt_type") != POSTGRES_RECEIPT_TYPE:
        raise ValueError("cloudbank-dark-factory-postgresql-receipt-required")
    if postgres_receipt.get("source_oracle_receipt_sha256") != oracle_receipt.get("content_sha256"):
        raise ValueError("cloudbank-dark-factory-receipt-chain-invalid")
    oracle_image_id = str(oracle_receipt.get("oracle_image_id_sha256", ""))
    postgres_image_id = str(postgres_receipt.get("postgresql_image_id_sha256", ""))
    if not HEX_64.fullmatch(oracle_image_id) or not HEX_64.fullmatch(postgres_image_id):
        raise ValueError("cloudbank-dark-factory-image-identity-invalid")
    if postgres_receipt.get("source_oracle_image_id_sha256") != oracle_image_id:
        raise ValueError("cloudbank-dark-factory-source-image-chain-invalid")

    order = factory_work_order(project_root, oracle_image_id, postgres_image_id)
    run_name = run_id or f"cloudbank-customer-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    orchestrator = orchestrator_factory(
        source_root / PINNED_SUBTREE,
        output_root / "runs",
        CloudBankCustomerAgentSet(project_root),
        graph_path=project_root / "knowledge/composite/estate.snapshot.json.gz",
        evidence_path=project_root / "knowledge/composite/source.pack.json.gz",
    )
    factory_receipt = orchestrator.run(order, run_name)
    run_dir = output_root / "runs" / run_name
    reports = []
    for path in sorted((run_dir / "artifacts").glob("*-verification-report.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        gate = payload.get("content", {}).get("gates", [{}])[0]
        reports.append(_parse_lane_result(str(gate.get("stdout", ""))))
    if len(reports) != 2:
        raise ValueError("cloudbank-dark-factory-dual-run-evidence-incomplete")
    source_lane, target_lane = reports
    expected_paths = sorted(PATCHES)
    diagnostic = _acceptance_diagnostic(
        factory_receipt, expected_paths, source_lane, target_lane
    )
    if diagnostic["failed_checks"]:
        print(
            "CLOUDBANK_DARK_FACTORY_ACCEPTANCE_DIAGNOSTIC="
            + json.dumps(diagnostic, sort_keys=True, separators=(",", ":")),
            file=sys.stderr,
        )
        raise ValueError(
            "cloudbank-dark-factory-acceptance-failed:"
            + "/".join(diagnostic["failed_checks"])
        )

    receipt = sign(
        {
            "schema_version": "1.0",
            "receipt_type": FACTORY_RECEIPT_TYPE,
            "release": RELEASE,
            "run_id": run_name,
            "source_oracle_receipt_sha256": oracle_receipt["content_sha256"],
            "postgresql_mapping_receipt_sha256": postgres_receipt["content_sha256"],
            "oracle_image_id_sha256": oracle_image_id,
            "postgresql_image_id_sha256": postgres_image_id,
            "mapping_sha256": target_mapping()["content_sha256"],
            "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
            "work_order_sha256": order.content_sha256,
            "factory_run_receipt_sha256": factory_receipt["content_sha256"],
            "changed_paths": expected_paths,
            "oracle_lane": source_lane,
            "postgresql_lane": target_lane,
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
        key,
        signer,
    )
    from lightyear_common.io import write_json

    write_json(output_root / "cloudbank-customer-dark-factory.receipt.json", receipt)
    return receipt


def validate_factory_receipt(payload: Mapping[str, Any], key: str, project_root: Path) -> list[str]:
    receipt = dict(payload)
    errors: list[str] = []
    if receipt.get("receipt_type") != FACTORY_RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-dark-factory-receipt-identity-invalid")
    if receipt.get("content_sha256") != content_hash(receipt):
        errors.append("cloudbank-dark-factory-receipt-content-hash-invalid")
    if not key or not verify_signature(receipt, key):
        errors.append("cloudbank-dark-factory-receipt-signature-invalid")
    if receipt.get("mapping_sha256") != target_mapping()["content_sha256"]:
        errors.append("cloudbank-dark-factory-receipt-mapping-invalid")
    if receipt.get("transformation_plan_sha256") != transformation_plan(project_root)["content_sha256"]:
        errors.append("cloudbank-dark-factory-receipt-plan-invalid")
    if receipt.get("changed_paths") != sorted(PATCHES):
        errors.append("cloudbank-dark-factory-receipt-paths-invalid")
    hash_fields = (
        "source_oracle_receipt_sha256",
        "postgresql_mapping_receipt_sha256",
        "oracle_image_id_sha256",
        "postgresql_image_id_sha256",
        "work_order_sha256",
        "factory_run_receipt_sha256",
    )
    if any(not HEX_64.fullmatch(str(receipt.get(name, ""))) for name in hash_fields):
        errors.append("cloudbank-dark-factory-receipt-hash-identity-invalid")
    if receipt.get("shared_contract_sha256") != SHARED_CONTRACT_SHA256:
        errors.append("cloudbank-dark-factory-receipt-shared-contract-invalid")
    for lane, name in (("oracle_lane", "oracle"), ("postgresql_lane", "postgresql")):
        value = receipt.get(lane, {})
        expected_image = receipt.get(
            "oracle_image_id_sha256" if name == "oracle" else "postgresql_image_id_sha256"
        )
        if (
            value.get("lane") != name
            or value.get("status") != "passed"
            or value.get("tests") != 2
            or value.get("failures") != 0
            or value.get("errors") != 0
            or value.get("skipped") != 0
            or value.get("shared_contract_sha256") != SHARED_CONTRACT_SHA256
            or value.get("database_image_id_sha256") != expected_image
            or value.get("maven_exit_code") != 0
            or not HEX_64.fullmatch(str(value.get("stdout_sha256", "")))
            or not HEX_64.fullmatch(str(value.get("stderr_sha256", "")))
            or value.get("raw_output_persisted") is not False
        ):
            errors.append(f"cloudbank-dark-factory-receipt-{name}-lane-invalid")
    required_true = (
        "source_oracle_application_observed",
        "target_postgresql_application_observed",
        "native_dual_run_observed",
        "application_refactored",
        "bounded_customer_application_equivalent",
    )
    if any(receipt.get(name) is not True for name in required_true):
        errors.append("cloudbank-dark-factory-receipt-acceptance-incomplete")
    required_false = ("human_promotion_authorized", "target_equivalent", "migration_complete", "production_ready")
    if any(receipt.get(name) is not False for name in required_false):
        errors.append("cloudbank-dark-factory-receipt-overclaims")
    if receipt.get("status") != "passed-bounded-customer-dark-factory-run":
        errors.append("cloudbank-dark-factory-receipt-status-invalid")
    security = receipt.get("security", {})
    if (
        security.get("source_checkout_mutated") is not False
        or security.get("raw_maven_output_persisted") is not False
        or security.get("credentials_persisted") is not False
        or security.get("production_data_persisted") is not False
        or security.get("database_ports") != "ephemeral-loopback-only"
        or security.get("dependency_resolution_network_allowed") is not True
    ):
        errors.append("cloudbank-dark-factory-receipt-security-invalid")
    forbidden = ("password", "secret", "token", "credential")
    allowed = {"credentials_persisted"}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for name, child in value.items():
                if any(term in str(name).lower() for term in forbidden) and str(name) not in allowed:
                    errors.append("cloudbank-dark-factory-receipt-forbidden-sensitive-field")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(receipt)
    return sorted(set(errors))


def _safe_controller_reason(exc: Exception) -> str:
    detail = str(exc)
    if (
        isinstance(exc, ValueError)
        and detail.startswith("cloudbank-dark-factory-")
        and re.fullmatch(r"[a-z0-9:./-]+", detail)
    ):
        return detail
    return type(exc).__name__


def _gate_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private CloudBank customer dual-run gate")
    parser.add_argument("command", choices=("gate",))
    parser.add_argument("--oracle-image-id-sha256", required=True)
    parser.add_argument("--postgresql-image-id-sha256", required=True)
    args = parser.parse_args(argv)
    workspace = Path(os.environ.get("LIGHTYEAR_FACTORY_WORKSPACE", ".")).resolve()
    project_root = Path(__file__).resolve().parents[2]
    try:
        code, result = run_gate(
            workspace,
            project_root,
            args.oracle_image_id_sha256,
            args.postgresql_image_id_sha256,
        )
    except Exception as exc:
        code = 14
        result = {
            "lane": "unknown",
            "status": "failed",
            "reason": f"controller-safe-stop:{_safe_controller_reason(exc)}",
        }
    print(LANE_MARKER + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(_gate_main())
