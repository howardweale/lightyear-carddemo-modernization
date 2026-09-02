from __future__ import annotations

import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.54.0"
OUTPUT_ROOT = Path("reference-estates/cloudbank/executable-baseline")
PINNED_COMMIT = "4f41b16d00c45503f691836fee8138010c969e86"
PINNED_ROOT_TREE = "6aa92e89c783f123c4da8d7ae18108004a4f4a99"
PINNED_SUBTREE = "cloudbank-v5"
PINNED_SUBTREE_TREE = "bd918386209f284a1ed31802555740eb34b75348"
ORACLE_IMAGE = "gvenzl/oracle-free:23.26.1-slim-faststart"
BUILD_RECEIPT_TYPE = "lightyear-cloudbank-source-build-execution-receipt"
ORACLE_RECEIPT_TYPE = "lightyear-cloudbank-oracle-runtime-execution-receipt"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")

REACTOR_MODULES = (
    "account",
    "azn-server",
    "buildtools",
    "chatbot",
    "checks",
    "common",
    "creditscore",
    "customer",
    "testrunner",
    "transfer",
)
UPSTREAM_IMAGE_BUILD_SERVICES = (
    "azn-server",
    "account",
    "customer",
    "transfer",
    "checks",
    "creditscore",
    "testrunner",
)
ORACLE_TEST_CLASSES = (
    "oracle.obaas.aznserver.integration.UserRepositoryOracleIT",
    "oracle.obaas.aznserver.integration.UserApiOracleIT",
    "oracle.obaas.aznserver.integration.AuthorizationServerIT",
)
ORACLE_TEST_COUNTS = {
    "oracle.obaas.aznserver.integration.UserRepositoryOracleIT": 2,
    "oracle.obaas.aznserver.integration.UserApiOracleIT": 3,
    "oracle.obaas.aznserver.integration.AuthorizationServerIT": 2,
}


def _source_identity() -> dict[str, Any]:
    return {
        "repository": "https://github.com/oracle/microservices-backend",
        "commit": PINNED_COMMIT,
        "root_tree": PINNED_ROOT_TREE,
        "subtree": PINNED_SUBTREE,
        "subtree_tree": PINNED_SUBTREE_TREE,
    }


def build_plan() -> dict[str, Any]:
    services = ",".join(UPSTREAM_IMAGE_BUILD_SERVICES)
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-source-build-plan",
            "release": RELEASE,
            "source": _source_identity(),
            "source_scope": {
                "full_pinned_subtree_required": True,
                "tracked_file_count": 189,
                "java_source_unit_count": 70,
                "sql_file_count": 9,
                "reactor_modules": list(REACTOR_MODULES),
                "upstream_image_build_services": list(UPSTREAM_IMAGE_BUILD_SERVICES),
                "excluded_from_upstream_image_build": {
                    "chatbot": "not listed by the pinned upstream 2-images_build_push.sh service set",
                },
            },
            "toolchain": {
                "java_major": 21,
                "maven_minimum": "3.6.0",
                "network_dependency_resolution_required": True,
                "docker_required": False,
            },
            "steps": [
                {
                    "id": "install-buildtools",
                    "argv": ["mvn", "clean", "install", "-pl", "buildtools", "-DskipTests"],
                },
                {
                    "id": "install-parent",
                    "argv": ["mvn", "clean", "install", "-N", "-DskipTests"],
                },
                {
                    "id": "install-common",
                    "argv": ["mvn", "clean", "install", "-pl", "common", "-DskipTests"],
                },
                {
                    "id": "package-upstream-service-set",
                    "argv": [
                        "mvn",
                        "clean",
                        "package",
                        "-pl",
                        services,
                        "-Dmaven.compiler.release=21",
                        "-DskipTests",
                    ],
                },
            ],
            "expected_artifacts": [
                {
                    "module": module,
                    "path": f"{module}/target/{module}-0.0.1-SNAPSHOT.jar",
                }
                for module in UPSTREAM_IMAGE_BUILD_SERVICES
            ],
            "claim_boundary": {
                "source_build_observed": False,
                "oracle_runtime_observed": False,
                "postgresql_mapping_complete": False,
                "target_equivalent": False,
                "migration_complete": False,
                "production_ready": False,
            },
        }
    )


def oracle_runtime_plan() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-oracle-runtime-plan",
            "release": RELEASE,
            "source": _source_identity(),
            "build_plan_sha256": build_plan()["content_sha256"],
            "scope": {
                "module": "azn-server",
                "suite": "pinned-upstream-testcontainers-oracle-integration",
                "test_classes": list(ORACLE_TEST_CLASSES),
                "expected_test_count": sum(ORACLE_TEST_COUNTS.values()),
                "oracle_image": ORACLE_IMAGE,
                "database_behavior": [
                    "Liquibase USER_REPO schema bootstrap",
                    "Oracle-backed user repository create/read/update behavior",
                    "Oracle-backed user API behavior",
                    "OAuth2 authorization-server token behavior",
                ],
            },
            "toolchain": {
                "java_major": 21,
                "maven_minimum": "3.6.0",
                "docker_daemon_required": True,
                "oracle_image_identity_required": True,
            },
            "argv": [
                "mvn",
                "-pl",
                "azn-server",
                "-Dtest=" + ",".join(name.rsplit(".", 1)[-1] for name in ORACLE_TEST_CLASSES),
                "test",
            ],
            "admission": {
                "signed_build_receipt_required": True,
                "exact_source_identity_required": True,
                "all_expected_tests_required": True,
                "failures_errors_skips_allowed": 0,
                "raw_stdout_persisted": False,
                "raw_stderr_persisted": False,
                "credentials_persisted": False,
            },
            "claim_boundary": {
                "cloudbank_oracle_source_baseline": "bounded-to-azn-server-upstream-integration-suite",
                "customer_service_runtime_observed": False,
                "production_data_observed": False,
                "postgresql_mapping_complete": False,
                "target_equivalent": False,
                "migration_complete": False,
                "production_ready": False,
            },
        }
    )


def execution_contract() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-executable-source-baseline",
            "release": RELEASE,
            "source": _source_identity(),
            "build_plan_sha256": build_plan()["content_sha256"],
            "oracle_runtime_plan_sha256": oracle_runtime_plan()["content_sha256"],
            "admitted_receipt_types": [BUILD_RECEIPT_TYPE, ORACLE_RECEIPT_TYPE],
            "receipt_security": {
                "content_addressed": True,
                "signature_algorithm": "hmac-sha256",
                "key_source": "LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY runtime environment only",
                "unsigned_receipts_admitted": False,
                "credentials_or_raw_logs_admitted": False,
            },
            "source_baseline_rule": (
                "The bounded executable source baseline is observed only after the exact pinned "
                "source produces all seven expected service JARs and the seven pinned azn-server "
                "Oracle Testcontainers integration tests pass against an identified Oracle image."
            ),
            "data_rule": (
                "Pinned sample and bootstrap data may qualify the first controlled run. Production "
                "CloudBank data requires a separately authorized, profiled, non-repository extract."
            ),
            "postgresql_rule": (
                "No PostgreSQL mapping is generated or admitted by this milestone; mapping begins "
                "only after the source execution receipt is admitted."
            ),
        }
    )


def readiness_receipt() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-executable-baseline-readiness",
            "release": RELEASE,
            "source": _source_identity(),
            "execution_contract_sha256": execution_contract()["content_sha256"],
            "gates": [
                {"id": "full-pinned-source", "status": "passed-static"},
                {"id": "java21-maven-build-contract", "status": "passed-static"},
                {"id": "oracle-native-test-contract", "status": "passed-static"},
                {"id": "signed-receipt-verifier", "status": "passed-static"},
                {"id": "source-build-execution", "status": "blocked-authorized-runtime-required"},
                {"id": "oracle-native-execution", "status": "blocked-docker-oracle-runtime-required"},
                {"id": "customer-service-baseline", "status": "blocked-first-factory-workcell"},
                {"id": "production-data-acquisition", "status": "blocked-separate-authorization-required"},
            ],
            "gate_status": "ready-to-execute-not-observed",
            "source_build_observed": False,
            "oracle_runtime_observed": False,
            "native_oracle_test_count": 0,
            "cloudbank_source_baseline_complete": False,
            "customer_service_runtime_observed": False,
            "production_data_observed": False,
            "target_selected": False,
            "postgresql_mapping_complete": False,
            "target_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def build_artifacts() -> dict[str, dict[str, Any]]:
    return {
        "build-plan.json": build_plan(),
        "oracle-runtime-plan.json": oracle_runtime_plan(),
        "execution-contract.json": execution_contract(),
        "readiness.receipt.json": readiness_receipt(),
    }


def validate_artifacts(project_root: Path) -> list[str]:
    errors: list[str] = []
    source_pin = json.loads(
        (project_root / "reference-estates/cloudbank/source-pin.json").read_text(encoding="utf-8")
    )["source"]
    if any(source_pin.get(key) != value for key, value in _source_identity().items()):
        errors.append("cloudbank-source-pin-does-not-match-executable-baseline")
    inventory = json.loads(
        (project_root / "reference-estates/cloudbank/inventory.json").read_text(encoding="utf-8")
    )
    estate = inventory["estate"]
    if tuple(estate["maven_modules"]) != REACTOR_MODULES:
        errors.append("cloudbank-reactor-module-inventory-drift")
    if estate["tracked_files"] != 189 or estate["java_source_units"] != 70:
        errors.append("cloudbank-full-source-inventory-drift")
    output = project_root / OUTPUT_ROOT
    for name, expected in build_artifacts().items():
        path = output / name
        if not path.is_file():
            errors.append(f"cloudbank-executable-baseline-missing:{name}")
            continue
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"cloudbank-executable-baseline-invalid-json:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-executable-baseline-drift:{name}")
    return sorted(set(errors))


def _run_git(source_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"git-source-identity-check-failed:{args[0]}")
    return result.stdout.strip()


def validate_source_checkout(source_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        if _run_git(source_root, "rev-parse", "HEAD") != PINNED_COMMIT:
            errors.append("cloudbank-source-commit-mismatch")
        if _run_git(source_root, "rev-parse", "HEAD^{tree}") != PINNED_ROOT_TREE:
            errors.append("cloudbank-source-root-tree-mismatch")
        if _run_git(source_root, "rev-parse", f"HEAD:{PINNED_SUBTREE}") != PINNED_SUBTREE_TREE:
            errors.append("cloudbank-source-subtree-tree-mismatch")
        if _run_git(source_root, "status", "--porcelain", "--untracked-files=no"):
            errors.append("cloudbank-source-tracked-worktree-dirty")
    except ValueError as exc:
        errors.append(str(exc))
    subtree = source_root / PINNED_SUBTREE
    if not (subtree / "pom.xml").is_file():
        errors.append("cloudbank-source-subtree-not-materialized")
    return sorted(set(errors))


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not match:
        return ()
    return tuple(int(part or 0) for part in match.groups())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _command_result(argv: Sequence[str], cwd: Path) -> dict[str, Any]:
    result = subprocess.run(list(argv), cwd=cwd, check=False, capture_output=True)
    return {
        "argv_sha256": content_hash({"argv": list(argv)}),
        "exit_code": result.returncode,
        "stdout_sha256": _sha256_bytes(result.stdout),
        "stderr_sha256": _sha256_bytes(result.stderr),
    }


def _toolchain() -> dict[str, Any]:
    try:
        java = subprocess.run(["java", "-version"], check=False, capture_output=True, text=True)
        java_text = java.stderr + java.stdout
    except OSError:
        java_text = ""
    try:
        maven = subprocess.run(["mvn", "-version"], check=False, capture_output=True, text=True)
        maven_text = maven.stdout + maven.stderr
    except OSError:
        maven_text = ""
    java_version = re.search(r'version "([^"]+)"', java_text)
    maven_version = re.search(r"Apache Maven\s+([^\s]+)", maven_text)
    return {
        "java_version": java_version.group(1) if java_version else "unresolved",
        "java_major": (_version_tuple(java_version.group(1))[0] if java_version and _version_tuple(java_version.group(1)) else 0),
        "maven_version": maven_version.group(1) if maven_version else "unresolved",
    }


def execute_source_build(source_root: Path, key: str, signer: str) -> dict[str, Any]:
    errors = validate_source_checkout(source_root)
    if errors:
        raise ValueError(",".join(errors))
    toolchain = _toolchain()
    if toolchain["java_major"] != 21:
        raise ValueError("cloudbank-source-build-requires-java-21")
    if _version_tuple(toolchain["maven_version"]) < (3, 6, 0):
        raise ValueError("cloudbank-source-build-requires-maven-3.6-or-newer")
    plan = build_plan()
    subtree = source_root / PINNED_SUBTREE
    results = [_command_result(step["argv"], subtree) for step in plan["steps"]]
    if any(item["exit_code"] != 0 for item in results):
        raise ValueError("cloudbank-source-build-command-failed")
    artifacts = []
    for expected in plan["expected_artifacts"]:
        path = subtree / expected["path"]
        if not path.is_file():
            raise ValueError(f"cloudbank-source-build-artifact-missing:{expected['module']}")
        artifacts.append(
            {
                "module": expected["module"],
                "path": expected["path"],
                "sha256": _sha256_bytes(path.read_bytes()),
                "size_bytes": path.stat().st_size,
            }
        )
    return sign(
        {
            "schema_version": "1.0",
            "receipt_type": BUILD_RECEIPT_TYPE,
            "release": RELEASE,
            "source": _source_identity(),
            "build_plan_sha256": plan["content_sha256"],
            "toolchain": toolchain,
            "commands": results,
            "artifacts": artifacts,
            "status": "passed",
            "security": {
                "raw_stdout_persisted": False,
                "raw_stderr_persisted": False,
                "credentials_persisted": False,
            },
            "source_build_observed": True,
            "oracle_runtime_observed": False,
            "cloudbank_source_baseline_complete": False,
            "postgresql_mapping_complete": False,
            "target_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        },
        key,
        signer,
    )


def _surefire_totals(report_root: Path) -> dict[str, int]:
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    observed: set[str] = set()
    for path in sorted(report_root.glob("TEST-*.xml")):
        root = ET.parse(path).getroot()
        name = root.attrib.get("name", "")
        if name not in ORACLE_TEST_CLASSES:
            continue
        observed.add(name)
        for key in totals:
            totals[key] += int(root.attrib.get(key, "0"))
    totals["classes"] = len(observed)
    return totals


def execute_oracle_runtime(
    source_root: Path,
    build_receipt: Mapping[str, Any],
    image_id: str,
    key: str,
    signer: str,
) -> dict[str, Any]:
    source_errors = validate_source_checkout(source_root)
    build_errors = validate_execution_receipt(build_receipt, key)
    if source_errors or build_errors:
        raise ValueError(",".join(source_errors + build_errors))
    if build_receipt.get("receipt_type") != BUILD_RECEIPT_TYPE:
        raise ValueError("cloudbank-oracle-runtime-requires-build-receipt")
    if not HEX_64.fullmatch(image_id):
        raise ValueError("cloudbank-oracle-image-id-must-be-sha256")
    plan = oracle_runtime_plan()
    subtree = source_root / PINNED_SUBTREE
    result = _command_result(plan["argv"], subtree)
    if result["exit_code"]:
        raise ValueError("cloudbank-oracle-runtime-test-command-failed")
    totals = _surefire_totals(subtree / "azn-server/target/surefire-reports")
    if totals != {"tests": 7, "failures": 0, "errors": 0, "skipped": 0, "classes": 3}:
        raise ValueError("cloudbank-oracle-runtime-test-results-not-admissible")
    return sign(
        {
            "schema_version": "1.0",
            "receipt_type": ORACLE_RECEIPT_TYPE,
            "release": RELEASE,
            "source": _source_identity(),
            "oracle_runtime_plan_sha256": plan["content_sha256"],
            "build_receipt_sha256": build_receipt["content_sha256"],
            "toolchain": _toolchain(),
            "oracle_image": ORACLE_IMAGE,
            "oracle_image_id_sha256": image_id,
            "command": result,
            "test_results": totals,
            "status": "passed",
            "security": {
                "raw_stdout_persisted": False,
                "raw_stderr_persisted": False,
                "credentials_persisted": False,
            },
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
        key,
        signer,
    )


def _false_claims(payload: Mapping[str, Any]) -> Iterable[str]:
    for key in (
        "postgresql_mapping_complete",
        "target_equivalent",
        "migration_complete",
        "production_ready",
    ):
        if payload.get(key) is not False:
            yield f"cloudbank-receipt-overclaims:{key}"


def _contains_forbidden_sensitive_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower()
            if normalized not in {
                "credentials_persisted",
                "raw_stdout_persisted",
                "raw_stderr_persisted",
            } and any(
                marker in normalized
                for marker in ("password", "secret", "credential_value", "token_value", "raw_stdout", "raw_stderr")
            ):
                return True
            if _contains_forbidden_sensitive_field(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_sensitive_field(item) for item in value)
    return False


def validate_execution_receipt(payload: Mapping[str, Any], key: str) -> list[str]:
    errors: list[str] = []
    receipt_type = payload.get("receipt_type")
    if receipt_type not in {BUILD_RECEIPT_TYPE, ORACLE_RECEIPT_TYPE}:
        errors.append("cloudbank-receipt-type-not-admitted")
    if payload.get("release") != RELEASE:
        errors.append("cloudbank-receipt-release-mismatch")
    if payload.get("source") != _source_identity():
        errors.append("cloudbank-receipt-source-mismatch")
    if payload.get("content_sha256") != content_hash(dict(payload)):
        errors.append("cloudbank-receipt-content-hash-invalid")
    if not key or not verify_signature(dict(payload), key):
        errors.append("cloudbank-receipt-signature-invalid")
    if payload.get("status") != "passed":
        errors.append("cloudbank-receipt-status-not-passed")
    security = payload.get("security", {})
    if security != {
        "raw_stdout_persisted": False,
        "raw_stderr_persisted": False,
        "credentials_persisted": False,
    }:
        errors.append("cloudbank-receipt-security-boundary-invalid")
    if _contains_forbidden_sensitive_field(payload):
        errors.append("cloudbank-receipt-forbidden-sensitive-field")
    errors.extend(_false_claims(payload))
    toolchain = payload.get("toolchain", {})
    if toolchain.get("java_major") != 21:
        errors.append("cloudbank-receipt-java-major-invalid")
    if _version_tuple(str(toolchain.get("maven_version", ""))) < (3, 6, 0):
        errors.append("cloudbank-receipt-maven-version-invalid")
    if receipt_type == BUILD_RECEIPT_TYPE:
        if payload.get("build_plan_sha256") != build_plan()["content_sha256"]:
            errors.append("cloudbank-build-receipt-plan-mismatch")
        if len(payload.get("commands", [])) != 4 or any(
            item.get("exit_code") != 0 for item in payload.get("commands", [])
        ):
            errors.append("cloudbank-build-receipt-command-results-invalid")
        artifacts = payload.get("artifacts", [])
        if {item.get("module") for item in artifacts} != set(UPSTREAM_IMAGE_BUILD_SERVICES):
            errors.append("cloudbank-build-receipt-artifact-set-invalid")
        expected_paths = {
            module: f"{module}/target/{module}-0.0.1-SNAPSHOT.jar"
            for module in UPSTREAM_IMAGE_BUILD_SERVICES
        }
        if any(expected_paths.get(item.get("module")) != item.get("path") for item in artifacts):
            errors.append("cloudbank-build-receipt-artifact-path-invalid")
        if any(
            not HEX_64.fullmatch(str(item.get("sha256", "")))
            or not isinstance(item.get("size_bytes"), int)
            or item.get("size_bytes", 0) <= 0
            for item in artifacts
        ):
            errors.append("cloudbank-build-receipt-artifact-evidence-invalid")
        if any(
            not all(
                HEX_64.fullmatch(str(item.get(field, "")))
                for field in ("argv_sha256", "stdout_sha256", "stderr_sha256")
            )
            for item in payload.get("commands", [])
        ):
            errors.append("cloudbank-build-receipt-command-evidence-invalid")
        if payload.get("source_build_observed") is not True:
            errors.append("cloudbank-build-receipt-source-build-not-observed")
        if payload.get("oracle_runtime_observed") is not False:
            errors.append("cloudbank-build-receipt-overclaims-oracle-runtime")
        if payload.get("cloudbank_source_baseline_complete") is not False:
            errors.append("cloudbank-build-receipt-overclaims-source-baseline")
    elif receipt_type == ORACLE_RECEIPT_TYPE:
        if payload.get("oracle_runtime_plan_sha256") != oracle_runtime_plan()["content_sha256"]:
            errors.append("cloudbank-oracle-receipt-plan-mismatch")
        if not HEX_64.fullmatch(str(payload.get("build_receipt_sha256", ""))):
            errors.append("cloudbank-oracle-receipt-build-binding-invalid")
        if payload.get("oracle_image") != ORACLE_IMAGE or not HEX_64.fullmatch(
            str(payload.get("oracle_image_id_sha256", ""))
        ):
            errors.append("cloudbank-oracle-receipt-image-identity-invalid")
        if payload.get("command", {}).get("exit_code") != 0:
            errors.append("cloudbank-oracle-receipt-command-result-invalid")
        if not all(
            HEX_64.fullmatch(str(payload.get("command", {}).get(field, "")))
            for field in ("argv_sha256", "stdout_sha256", "stderr_sha256")
        ):
            errors.append("cloudbank-oracle-receipt-command-evidence-invalid")
        if payload.get("test_results") != {
            "tests": 7,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "classes": 3,
        }:
            errors.append("cloudbank-oracle-receipt-test-results-invalid")
        for key_name in (
            "source_build_observed",
            "oracle_runtime_observed",
            "cloudbank_source_baseline_complete",
        ):
            if payload.get(key_name) is not True:
                errors.append(f"cloudbank-oracle-receipt-claim-invalid:{key_name}")
        if payload.get("customer_service_runtime_observed") is not False:
            errors.append("cloudbank-oracle-receipt-overclaims-customer-runtime")
        if payload.get("production_data_observed") is not False:
            errors.append("cloudbank-oracle-receipt-overclaims-production-data")
    return sorted(set(errors))
