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
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from lightyear_common.io import write_json, write_text

from .cloudbank_baseline import PINNED_SUBTREE
from .cloudbank_customer_postgres import POSTGRES_IMAGE
from .cloudbank_dark_factory import (
    _container_connectivity_args,
    _container_endpoint,
    _inspect_image,
    _wait_postgres,
)
from .cloudbank_transaction_wave import (
    RECEIPT_TYPE as MS58_RECEIPT_TYPE,
    SOURCE_FILES,
    transaction_behavior_contract,
    validate_admission_receipt,
    validate_source,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.59.0"
OUTPUT_ROOT = Path("factory/cloudbank/transaction-core")
PATCH_ROOT = OUTPUT_ROOT / "patches"
RECEIPT_TYPE = "lightyear-cloudbank-transaction-core-postgresql-execution"
RECEIPT_NAME = "cloudbank-transaction-core.receipt.json"
FAILURE_NAME = "cloudbank-transaction-core.failure.json"
ROOT_POM_SHA256 = "9d72b44ca06675e09f5927872a3c6fae86d98973292ffa943f2c6370cf63ace6"
EXPECTED_TESTS = 7
CONTRACT_MARKER = (
    "success:pass;invalid:pass;funds:pass;fault:pass;idempotency:pass;"
    "auth:pass;recovery:pass;replay:pass"
)
CONTRACT_SHA256 = hashlib.sha256(CONTRACT_MARKER.encode()).hexdigest()
HEX_64 = re.compile(r"^[0-9a-f]{64}$")

ROOT_ORACLE_DEPENDENCY = """        <dependency>
            <groupId>com.oracle.database.spring</groupId>
            <artifactId>oracle-spring-boot-starter-ucp</artifactId>
            <version>${oracle-springboot-starter.version}</version>
            <type>pom</type>
        </dependency>
"""

PATCHES = {
    "account/pom.xml": ("account-pom.xml", SOURCE_FILES["account/pom.xml"]),
    "account/src/main/resources/application.yaml": (
        "account-application.yaml",
        SOURCE_FILES["account/src/main/resources/application.yaml"],
    ),
    "account/src/main/resources/db/changelog/controller.yaml": (
        "controller.yaml",
        SOURCE_FILES["account/src/main/resources/db/changelog/controller.yaml"],
    ),
    "account/src/main/resources/db/changelog/table.sql": (
        "table.sql",
        SOURCE_FILES["account/src/main/resources/db/changelog/table.sql"],
    ),
    "account/src/main/resources/db/changelog/data.sql": (
        "data.sql",
        SOURCE_FILES["account/src/main/resources/db/changelog/data.sql"],
    ),
    "account/src/main/java/com/example/accounts/repository/AccountRepository.java": (
        "AccountRepository.java",
        SOURCE_FILES[
            "account/src/main/java/com/example/accounts/repository/AccountRepository.java"
        ],
    ),
    "account/src/main/java/com/example/accounts/model/TransferCommand.java": (
        "TransferCommand.java",
        None,
    ),
    "account/src/main/java/com/example/accounts/repository/TransferCommandRepository.java": (
        "TransferCommandRepository.java",
        None,
    ),
    "account/src/main/java/com/example/accounts/services/TransactionCoreService.java": (
        "TransactionCoreService.java",
        None,
    ),
    "account/src/main/java/com/example/accounts/controller/TransactionCoreController.java": (
        "TransactionCoreController.java",
        None,
    ),
    "account/src/test/java/com/example/accounts/TransactionCorePostgreSqlTests.java": (
        "TransactionCorePostgreSqlTests.java",
        None,
    ),
    "transfer/pom.xml": ("transfer-pom.xml", SOURCE_FILES["transfer/pom.xml"]),
    "transfer/src/main/resources/application.yaml": (
        "transfer-application.yaml",
        SOURCE_FILES["transfer/src/main/resources/application.yaml"],
    ),
    "transfer/src/main/java/com/example/transfer/TransferService.java": (
        "TransferService.java",
        SOURCE_FILES["transfer/src/main/java/com/example/transfer/TransferService.java"],
    ),
    "transfer/src/test/java/com/example/transfer/TransferServiceTests.java": (
        "TransferServiceTests.java",
        None,
    ),
}

DELETIONS = {
    "account/src/main/java/com/example/accounts/services/AccountTransferDAO.java": SOURCE_FILES[
        "account/src/main/java/com/example/accounts/services/AccountTransferDAO.java"
    ],
    "account/src/main/java/com/example/accounts/services/DepositService.java": SOURCE_FILES[
        "account/src/main/java/com/example/accounts/services/DepositService.java"
    ],
    "account/src/main/java/com/example/accounts/services/WithdrawService.java": SOURCE_FILES[
        "account/src/main/java/com/example/accounts/services/WithdrawService.java"
    ],
    "account/src/main/resources/db/changelog/txeventq.sql": SOURCE_FILES[
        "account/src/main/resources/db/changelog/txeventq.sql"
    ],
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _template_root(project_root: Path) -> Path:
    return project_root / PATCH_ROOT


def changed_paths() -> list[str]:
    return sorted(["pom.xml", *PATCHES, *DELETIONS])


def transformation_plan(project_root: Path) -> dict[str, Any]:
    edits = []
    for target, (template, source_sha256) in sorted(PATCHES.items()):
        edits.append(
            {
                "path": target,
                "operation": "create" if source_sha256 is None else "replace",
                "source_sha256": source_sha256,
                "template": f"patches/{template}",
                "target_sha256": _sha256(_template_root(project_root) / template),
            }
        )
    for target, source_sha256 in sorted(DELETIONS.items()):
        edits.append(
            {
                "path": target,
                "operation": "delete",
                "source_sha256": source_sha256,
                "template": None,
                "target_sha256": None,
            }
        )
    edits.append(
        {
            "path": "pom.xml",
            "operation": "remove-inherited-oracle-ucp",
            "source_sha256": ROOT_POM_SHA256,
            "template": None,
            "target_sha256": None,
        }
    )
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-transaction-core-transformation",
            "release": RELEASE,
            "services": ["account", "transfer"],
            "changes": sorted(edits, key=lambda item: item["path"]),
            "architecture_decisions": [
                "move each debit, credit, command, and journal pair into one PostgreSQL transaction",
                "replace the distributed LRA callback path with an idempotent Account command",
                "lock both accounts in stable identifier order to reduce deadlock risk",
                "require an internal service token and authenticated source-account actor",
                "retain the Transfer service as the external facade",
                "retire Oracle AQ grants from the Account schema without claiming the Checks queue migrated",
            ],
            "postgresql_target_generated": True,
            "native_execution_observed": False,
            "whole_application_migrated": False,
        }
    )


def acceptance_contract(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-transaction-core-acceptance",
            "release": RELEASE,
            "ms58_behavior_sha256": transaction_behavior_contract()["content_sha256"],
            "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
            "required_scenarios": [
                item["id"] for item in transaction_behavior_contract()["scenarios"]
            ],
            "required_native_lane": {
                "database": "postgresql-16",
                "services": ["account", "transfer"],
                "tests": EXPECTED_TESTS,
                "contract_sha256": CONTRACT_SHA256,
                "oracle_runtime_libraries": 0,
                "microtx_runtime_libraries": 0,
            },
            "claim_boundary": {
                "postgresql_transaction_core": "eligible-after-native-run",
                "oracle_postgresql_equivalence": False,
                "checks_aq_replacement": False,
                "remaining_service_workcells": False,
                "whole_application_equivalent": False,
                "production_ready": False,
            },
        }
    )


def compatibility_ledger() -> dict[str, Any]:
    entries = [
        ("account-schema", "normalized-equivalent", "native-ms59-required"),
        ("local-money-movement", "normalized-equivalent", "native-ms59-required"),
        ("microtx-lra", "policy-decision-required", "target-local-atomicity-observed"),
        ("idempotency", "normalized-equivalent", "native-ms59-required"),
        ("authorization", "normalized-equivalent", "native-ms59-required"),
        ("oracle-aq-checks-flow", "unsupported", "later-messaging-wave"),
        ("oracle-source-equivalence", "policy-decision-required", "native-dual-lane-required"),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "ledger_type": "lightyear-cloudbank-transaction-core-compatibility",
            "release": RELEASE,
            "entries": [
                {"capability": name, "classification": classification, "exit_gate": gate}
                for name, classification, gate in entries
            ],
            "aq_migrated": False,
            "oracle_postgresql_equivalent": False,
            "whole_application_equivalent": False,
        }
    )


def readiness_receipt(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-transaction-core-readiness",
            "release": RELEASE,
            "bindings": {
                "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
                "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
                "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            },
            "gate_status": "ready-for-signed-ms58-and-native-postgresql-run",
            "target_code_generated": True,
            "native_transaction_wave_observed": False,
            "native_lra_replacement_observed": False,
            "native_messaging_observed": False,
            "oracle_postgresql_equivalent": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def build_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "transformation-plan.json": transformation_plan(project_root),
        "acceptance-contract.json": acceptance_contract(project_root),
        "compatibility-ledger.json": compatibility_ledger(),
        "readiness.receipt.json": readiness_receipt(project_root),
    }


def write_artifacts(project_root: Path) -> None:
    for name, payload in build_artifacts(project_root).items():
        write_json(project_root / OUTPUT_ROOT / name, payload)


def validate_artifacts(project_root: Path) -> list[str]:
    errors: list[str] = []
    for name, expected in build_artifacts(project_root).items():
        path = project_root / OUTPUT_ROOT / name
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"cloudbank-transaction-core-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-transaction-core-artifact-drift:{name}")
    readiness = readiness_receipt(project_root)
    for claim in (
        "native_transaction_wave_observed",
        "native_lra_replacement_observed",
        "native_messaging_observed",
        "oracle_postgresql_equivalent",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    ):
        if readiness.get(claim) is not False:
            errors.append("cloudbank-transaction-core-readiness-overclaims")
    if len(transaction_behavior_contract()["scenarios"]) != 8:
        errors.append("cloudbank-transaction-core-scenario-contract-invalid")
    return sorted(set(errors))


def _validate_patch_sources(source_root: Path) -> list[str]:
    errors = validate_source(source_root)
    subtree = source_root / PINNED_SUBTREE
    root_pom = subtree / "pom.xml"
    if not root_pom.is_file() or _sha256(root_pom) != ROOT_POM_SHA256:
        errors.append("cloudbank-transaction-core-source-drift:pom.xml")
    for target, (_, expected) in PATCHES.items():
        path = subtree / target
        if expected is None:
            if path.exists():
                errors.append(f"cloudbank-transaction-core-source-collision:{target}")
        elif not path.is_file() or _sha256(path) != expected:
            errors.append(f"cloudbank-transaction-core-source-drift:{target}")
    for target, expected in DELETIONS.items():
        path = subtree / target
        if not path.is_file() or _sha256(path) != expected:
            errors.append(f"cloudbank-transaction-core-source-drift:{target}")
    return sorted(set(errors))


def materialize_target(project_root: Path, source_root: Path, output: Path) -> Path:
    errors = _validate_patch_sources(source_root)
    if errors:
        raise ValueError(",".join(errors))
    source = source_root / PINNED_SUBTREE
    if output.resolve() == source.resolve() or source.resolve() in output.resolve().parents:
        raise ValueError("cloudbank-transaction-core-output-inside-source")
    if output.exists():
        raise ValueError("cloudbank-transaction-core-output-exists")
    shutil.copytree(source, output, ignore=shutil.ignore_patterns("target", "*.pyc", "__pycache__"))
    root_pom = output / "pom.xml"
    root_text = root_pom.read_text(encoding="utf-8")
    if root_text.count(ROOT_ORACLE_DEPENDENCY) != 1:
        raise ValueError("cloudbank-transaction-core-root-pom-drift")
    write_text(root_pom, root_text.replace(ROOT_ORACLE_DEPENDENCY, ""))
    for target, (template, _) in PATCHES.items():
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_template_root(project_root) / template, destination)
    for target in DELETIONS:
        (output / target).unlink()
    return output


def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, text=True, capture_output=True, **kwargs)


def _test_totals(workspace: Path) -> dict[str, int]:
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    reports = [
        workspace / "account/target/surefire-reports/TEST-com.example.accounts.TransactionCorePostgreSqlTests.xml",
        workspace / "transfer/target/surefire-reports/TEST-com.example.transfer.TransferServiceTests.xml",
    ]
    if not all(path.is_file() for path in reports):
        return {name: -1 for name in totals}
    for path in reports:
        root = ET.parse(path).getroot()
        for name in totals:
            totals[name] += int(root.attrib.get(name, "-1"))
    return totals


def _package_inventory(workspace: Path) -> dict[str, Any]:
    jars = [
        workspace / "account/target/account-0.0.1-SNAPSHOT.jar",
        workspace / "transfer/target/transfer-0.0.1-SNAPSHOT.jar",
    ]
    if not all(path.is_file() for path in jars):
        return {
            "executable_jars": 0,
            "oracle_runtime_libraries": -1,
            "microtx_runtime_libraries": -1,
        }
    names: list[str] = []
    executable = 0
    for path in jars:
        with zipfile.ZipFile(path) as archive:
            archive_names = archive.namelist()
            names.extend(archive_names)
            launcher = "org/springframework/boot/loader/launch/JarLauncher.class"
            if "BOOT-INF/classes/" in archive_names and launcher in archive_names:
                executable += 1
    lowered = [name.lower() for name in names if name.startswith("BOOT-INF/lib/")]
    return {
        "executable_jars": executable,
        "oracle_runtime_libraries": sum("oracle" in name for name in lowered),
        "microtx_runtime_libraries": sum("microtx" in name for name in lowered),
    }


def _native_postgresql_lane(
    workspace: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
    pause: Callable[[float], None],
) -> dict[str, Any]:
    _inspect_image(POSTGRES_IMAGE, image_id, run)
    name = "lightyear-cb-ms59-pg-" + uuid.uuid4().hex[:10]
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
        raise ValueError("cloudbank-transaction-core-postgresql-start-failed")
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
            "CLOUDBANK_SECURITY_REQUIRE_INTERNAL_TOKEN": "false",
            "CLOUDBANK_TRANSACTION_INTERNAL_TOKEN": "synthetic-ms59-token",
        }
        result = run(
            [
                "mvn", "-pl", "account,transfer", "-am",
                "-Dtest=TransactionCorePostgreSqlTests,TransferServiceTests",
                "-Dsurefire.failIfNoSpecifiedTests=false", "package",
            ],
            cwd=workspace,
            env=env,
            timeout=1200,
        )
        totals = _test_totals(workspace)
        packaging = _package_inventory(workspace)
        marker = f"CLOUDBANK_TRANSACTION_CONTRACT={CONTRACT_MARKER}"
        passed = (
            result.returncode == 0
            and result.stdout.count(marker) == 1
            and totals == {"tests": EXPECTED_TESTS, "failures": 0, "errors": 0, "skipped": 0}
            and packaging == {
                "executable_jars": 2,
                "oracle_runtime_libraries": 0,
                "microtx_runtime_libraries": 0,
            }
        )
        return {
            "lane": "postgresql-transaction-core",
            "status": "passed" if passed else "failed",
            **totals,
            "maven_exit_code": result.returncode,
            "database_image_id_sha256": image_id,
            "contract_sha256": CONTRACT_SHA256 if marker in result.stdout else None,
            "packaging": packaging,
            "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
            "raw_output_persisted": False,
        }
    finally:
        password = ""
        run(["docker", "rm", "-f", name], timeout=30)


def execute_transaction_core(
    project_root: Path,
    source_root: Path,
    ms58_receipt: Mapping[str, Any],
    output_root: Path,
    key: str,
    signer: str,
    run_id: str | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = _run,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    errors = validate_artifacts(project_root)
    errors.extend(_validate_patch_sources(source_root))
    errors.extend(validate_admission_receipt(ms58_receipt, key, project_root))
    if ms58_receipt.get("receipt_type") != MS58_RECEIPT_TYPE:
        errors.append("cloudbank-transaction-core-ms58-receipt-required")
    if errors:
        raise ValueError(",".join(sorted(set(errors))))
    image_id = str(ms58_receipt.get("postgresql_image_id_sha256", ""))
    if not HEX_64.fullmatch(image_id):
        raise ValueError("cloudbank-transaction-core-image-identity-invalid")
    run_name = run_id or f"cloudbank-transaction-core-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    run_root = output_root / "runs" / run_name
    workspace = materialize_target(project_root, source_root, run_root / "workspace")
    lane = _native_postgresql_lane(workspace, image_id, run, pause)
    if lane["status"] != "passed":
        failure = {
            "schema_version": "1.0",
            "release": RELEASE,
            "run_id": run_name,
            "status": "failed",
            "lane": lane,
        }
        write_json(output_root / FAILURE_NAME, failure)
        raise ValueError("cloudbank-transaction-core-acceptance-failed")
    receipt = sign(
        {
            "schema_version": "1.0",
            "receipt_type": RECEIPT_TYPE,
            "release": RELEASE,
            "run_id": run_name,
            "source_ms58_receipt_sha256": ms58_receipt["content_sha256"],
            "postgresql_image_id_sha256": image_id,
            "transformation_plan_sha256": transformation_plan(project_root)["content_sha256"],
            "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
            "changed_paths": changed_paths(),
            "postgresql_lane": lane,
            "status": "passed-bounded-postgresql-transaction-core",
            "target_code_generated": True,
            "native_postgresql_transaction_core_observed": True,
            "bounded_local_atomicity_observed": True,
            "transfer_facade_contract_observed": True,
            "native_transaction_wave_observed": False,
            "native_lra_replacement_observed": False,
            "native_messaging_observed": False,
            "oracle_transaction_core_observed": False,
            "oracle_postgresql_equivalent": False,
            "remaining_service_workcells_complete": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
            "security": {
                "source_checkout_mutated": False,
                "synthetic_data_only": True,
                "credentials_persisted": False,
                "raw_maven_output_persisted": False,
                "database_ports": "ephemeral-loopback-only",
                "human_promotion_authorized": False,
            },
        },
        key,
        signer,
    )
    write_json(output_root / RECEIPT_NAME, receipt)
    return receipt


def validate_execution_receipt(
    receipt: Mapping[str, Any], key: str, project_root: Path
) -> list[str]:
    errors: list[str] = []
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-transaction-core-receipt-identity-invalid")
    if receipt.get("status") != "passed-bounded-postgresql-transaction-core":
        errors.append("cloudbank-transaction-core-receipt-status-invalid")
    if receipt.get("content_sha256") != content_hash(dict(receipt)):
        errors.append("cloudbank-transaction-core-receipt-content-hash-invalid")
    if not key or not verify_signature(dict(receipt), key):
        errors.append("cloudbank-transaction-core-receipt-signature-invalid")
    if receipt.get("transformation_plan_sha256") != transformation_plan(project_root)["content_sha256"]:
        errors.append("cloudbank-transaction-core-receipt-plan-invalid")
    if receipt.get("acceptance_contract_sha256") != acceptance_contract(project_root)["content_sha256"]:
        errors.append("cloudbank-transaction-core-receipt-contract-invalid")
    if receipt.get("changed_paths") != changed_paths():
        errors.append("cloudbank-transaction-core-receipt-paths-invalid")
    lane = receipt.get("postgresql_lane", {})
    if not isinstance(lane, Mapping) or any(
        (
            lane.get("status") != "passed",
            lane.get("tests") != EXPECTED_TESTS,
            lane.get("failures") != 0,
            lane.get("errors") != 0,
            lane.get("skipped") != 0,
            lane.get("contract_sha256") != CONTRACT_SHA256,
            lane.get("packaging") != {
                "executable_jars": 2,
                "oracle_runtime_libraries": 0,
                "microtx_runtime_libraries": 0,
            },
        )
    ):
        errors.append("cloudbank-transaction-core-receipt-lane-invalid")
    required_true = (
        "target_code_generated",
        "native_postgresql_transaction_core_observed",
        "bounded_local_atomicity_observed",
        "transfer_facade_contract_observed",
    )
    required_false = (
        "native_transaction_wave_observed",
        "native_lra_replacement_observed",
        "native_messaging_observed",
        "oracle_transaction_core_observed",
        "oracle_postgresql_equivalent",
        "remaining_service_workcells_complete",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    )
    if any(receipt.get(name) is not True for name in required_true) or any(
        receipt.get(name) is not False for name in required_false
    ):
        errors.append("cloudbank-transaction-core-receipt-claims-invalid")
    for name in (
        "source_ms58_receipt_sha256",
        "postgresql_image_id_sha256",
    ):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"cloudbank-transaction-core-receipt-hash-invalid:{name}")
    errors.extend(validate_artifacts(project_root))
    return sorted(set(errors))
