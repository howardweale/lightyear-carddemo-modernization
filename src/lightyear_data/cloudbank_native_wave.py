from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Mapping

from lightyear_common.io import write_json

from .cloudbank_customer_postgres import POSTGRES_IMAGE
from .cloudbank_dark_factory import (
    _container_connectivity_args,
    _container_endpoint,
    _inspect_image,
    _wait_postgres,
)
from .cloudbank_transaction_core import (
    RECEIPT_TYPE as MS59_RECEIPT_TYPE,
    _package_inventory,
    materialize_target as materialize_ms59_target,
    validate_execution_receipt as validate_ms59_receipt,
)
from .cloudbank_transaction_wave import validate_source
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.60.0"
OUTPUT_ROOT = Path("factory/cloudbank/native-transaction-wave")
PATCH_ROOT = OUTPUT_ROOT / "patches"
RECEIPT_TYPE = "lightyear-cloudbank-native-transaction-wave-execution"
RECEIPT_NAME = "cloudbank-native-transaction-wave.receipt.json"
FAILURE_NAME = "cloudbank-native-transaction-wave.failure.json"
EXPECTED_SCENARIOS = 11
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SCENARIO_IDS = [
    "services-healthy",
    "external-authentication-required",
    "internal-token-rejected",
    "invalid-amount-rejected",
    "owner-authorization-rejected",
    "insufficient-funds-rejected",
    "successful-value-conservation",
    "duplicate-command-replayed",
    "transfer-restart-replayed",
    "concurrent-opposite-transfers-conserve-value",
    "account-restart-replayed",
]
CONTRACT_SHA256 = hashlib.sha256(";".join(SCENARIO_IDS).encode()).hexdigest()
PATCHES = {
    "account/src/main/java/com/example/accounts/config/AccountWaveSecurityConfiguration.java": (
        "AccountWaveSecurityConfiguration.java"
    ),
    "transfer/src/main/java/com/example/transfer/config/TransferWaveSecurityConfiguration.java": (
        "TransferWaveSecurityConfiguration.java"
    ),
    "transfer/src/main/java/com/example/transfer/TransferService.java": "TransferService.java",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changed_paths() -> list[str]:
    return sorted(PATCHES)


def execution_plan(project_root: Path) -> dict[str, Any]:
    patches = []
    for target, template in sorted(PATCHES.items()):
        patches.append(
            {
                "path": target,
                "template": f"patches/{template}",
                "target_sha256": _sha256(project_root / PATCH_ROOT / template),
                "operation": "replace-generated" if template == "TransferService.java" else "create",
            }
        )
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-native-transaction-wave",
            "release": RELEASE,
            "services": ["account", "transfer"],
            "database": "postgresql-16",
            "base_target": "ms59-generated-account-transfer",
            "patches": patches,
            "stages": [
                "validate-signed-ms59-receipt",
                "materialize-isolated-ms59-target",
                "package-account-and-transfer",
                "start-loopback-postgresql-account-transfer",
                "exercise-authenticated-http-and-database-contract",
                "restart-transfer-and-account",
                "inspect-packaging-and-sign-receipt",
            ],
            "scenario_ids": SCENARIO_IDS,
            "production_security_profile": False,
            "production_data": False,
            "whole_application_migrated": False,
        }
    )


def acceptance_contract(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-native-transaction-wave-acceptance",
            "release": RELEASE,
            "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
            "contract_sha256": CONTRACT_SHA256,
            "required_scenarios": SCENARIO_IDS,
            "required_service_starts": {"account": 2, "transfer": 2},
            "required_packaging": {
                "executable_jars": 2,
                "oracle_runtime_libraries": 0,
                "microtx_runtime_libraries": 0,
            },
            "required_runtime_boundaries": {
                "database_port": "ephemeral-loopback-only",
                "service_ports": "ephemeral-loopback-only",
                "raw_logs_persisted": False,
                "synthetic_data_only": True,
            },
            "eligible_claims_after_signed_run": {
                "native_transaction_wave_observed": True,
                "native_lra_replacement_observed": True,
                "oracle_postgresql_equivalent": False,
                "whole_application_equivalent": False,
                "production_ready": False,
            },
        }
    )


def compatibility_ledger() -> dict[str, Any]:
    entries = [
        ("two-service-http-path", "exact", "native-ms60-required"),
        ("value-conservation", "normalized-equivalent", "native-ms60-required"),
        ("durable-idempotency", "normalized-equivalent", "restart-replay-required"),
        ("stable-lock-ordering", "normalized-equivalent", "concurrent-wave-required"),
        ("target-lra-removal", "normalized-equivalent", "native-integrated-wave-required"),
        ("development-basic-authentication", "exact", "loopback-profile-only"),
        ("production-oauth2-oidc", "policy-decision-required", "authorization-wave"),
        ("oracle-source-equivalence", "policy-decision-required", "native-dual-lane-required"),
        ("oracle-aq-checks-flow", "unsupported", "messaging-wave"),
        ("remaining-five-services", "unsupported", "later-service-waves"),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "ledger_type": "lightyear-cloudbank-native-transaction-wave-compatibility",
            "release": RELEASE,
            "entries": [
                {"capability": name, "classification": classification, "exit_gate": gate}
                for name, classification, gate in entries
            ],
            "bounded_target_lra_replacement_eligible": True,
            "production_identity_qualified": False,
            "oracle_postgresql_equivalent": False,
            "whole_application_equivalent": False,
        }
    )


def readiness_receipt(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-native-transaction-wave-readiness",
            "release": RELEASE,
            "bindings": {
                "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
                "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
                "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            },
            "gate_status": "ready-for-signed-ms59-and-native-integrated-run",
            "integrated_target_generated": True,
            "native_transaction_wave_observed": False,
            "native_lra_replacement_observed": False,
            "production_identity_qualified": False,
            "native_messaging_observed": False,
            "oracle_postgresql_equivalent": False,
            "remaining_service_workcells_complete": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def build_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "execution-plan.json": execution_plan(project_root),
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
        try:
            actual = json.loads((project_root / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"cloudbank-native-wave-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-native-wave-artifact-drift:{name}")
    if len(SCENARIO_IDS) != EXPECTED_SCENARIOS or len(set(SCENARIO_IDS)) != EXPECTED_SCENARIOS:
        errors.append("cloudbank-native-wave-scenarios-invalid")
    readiness = readiness_receipt(project_root)
    false_claims = (
        "native_transaction_wave_observed",
        "native_lra_replacement_observed",
        "production_identity_qualified",
        "native_messaging_observed",
        "oracle_postgresql_equivalent",
        "remaining_service_workcells_complete",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    )
    if any(readiness.get(name) is not False for name in false_claims):
        errors.append("cloudbank-native-wave-readiness-overclaims")
    return sorted(set(errors))


def materialize_target(project_root: Path, source_root: Path, output: Path) -> Path:
    workspace = materialize_ms59_target(project_root, source_root, output)
    for target, template in PATCHES.items():
        destination = workspace / target
        if template != "TransferService.java" and destination.exists():
            raise ValueError(f"cloudbank-native-wave-target-collision:{target}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_root / PATCH_ROOT / template, destination)
    return workspace


def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, text=True, capture_output=True, **kwargs)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _request(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    method: str = "GET",
    timeout: float = 10,
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=b"" if method == "POST" else None, method=method)
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(65536)
    except urllib.error.HTTPError as error:
        return int(error.code), error.read(65536)


def _wait_health(
    service: str,
    port: int,
    process: subprocess.Popen[bytes],
    pause: Callable[[float], None],
) -> None:
    url = f"http://127.0.0.1:{port}/actuator/health"
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError(f"{service}-exited-before-health")
        try:
            status, body = _request(url, timeout=1)
            if status == 200 and b'"status":"UP"' in body:
                return
        except (OSError, TimeoutError, urllib.error.URLError):
            pass
        pause(1)
    raise RuntimeError(f"{service}-health-timeout")


def _start_service(
    service: str,
    jar: Path,
    port: int,
    env: Mapping[str, str],
    pause: Callable[[float], None],
) -> tuple[subprocess.Popen[bytes], Any]:
    log = tempfile.TemporaryFile()
    process = subprocess.Popen(
        ["java", "-jar", str(jar)],
        cwd=jar.parent,
        env=dict(env),
        stdout=log,
        stderr=log,
    )
    _wait_health(service, port, process, pause)
    return process, log


def _stop_service(process: subprocess.Popen[bytes] | None, log: Any | None) -> str | None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if log is None:
        return None
    log.seek(0)
    digest = hashlib.sha256(log.read()).hexdigest()
    log.close()
    return digest


def _psql(container: str, sql: str, run: Callable[..., subprocess.CompletedProcess[str]]) -> str:
    result = run(
        ["docker", "exec", container, "psql", "-U", "postgres", "-d", "cloudbank", "-Atc", sql],
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("postgresql-query-failed")
    return result.stdout.strip()


def _seed(container: str, run: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    sql = """
TRUNCATE transfer_commands, journal, accounts RESTART IDENTITY CASCADE;
INSERT INTO accounts
    (account_id, account_name, account_type, customer_id, account_other_details, account_balance)
VALUES
    (1, 'Source', 'CH', 'cust-source', 'MS60 synthetic', 1000),
    (2, 'Target', 'CH', 'cust-target', 'MS60 synthetic', 250),
    (3, 'Empty', 'CH', 'cust-empty', 'MS60 synthetic', 5);
SELECT setval(pg_get_serial_sequence('accounts', 'account_id'), 3, true);
"""
    _psql(container, sql, run)


def _state(container: str, run: Callable[..., subprocess.CompletedProcess[str]]) -> dict[str, int]:
    sql = """
SELECT json_build_object(
    'balance_1', COALESCE((SELECT account_balance FROM accounts WHERE account_id = 1), -1),
    'balance_2', COALESCE((SELECT account_balance FROM accounts WHERE account_id = 2), -1),
    'balance_3', COALESCE((SELECT account_balance FROM accounts WHERE account_id = 3), -1),
    'journal_count', (SELECT count(*) FROM journal),
    'command_count', (SELECT count(*) FROM transfer_commands),
    'journal_net', COALESCE((SELECT sum(CASE WHEN journal_type = 'WITHDRAW'
        THEN -journal_amount ELSE journal_amount END) FROM journal), 0)
)::text;
"""
    payload = json.loads(_psql(container, sql, run))
    return {name: int(value) for name, value in payload.items()}


def _basic(user: str, password: str) -> str:
    encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {encoded}"


def _transfer(
    port: int,
    password: str,
    command_id: str,
    source: int,
    target: int,
    amount: int,
    user: str | None,
) -> tuple[int, dict[str, Any]]:
    query = urllib.parse.urlencode(
        {"fromAccount": source, "toAccount": target, "amount": amount}
    )
    headers = {"Idempotency-Key": command_id}
    if user is not None:
        headers["Authorization"] = _basic(user, password)
    status, body = _request(
        f"http://127.0.0.1:{port}/transfer?{query}",
        headers=headers,
        method="POST",
    )
    try:
        payload = json.loads(body.decode()) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    return status, payload


def _direct_account_wrong_token(port: int) -> int:
    query = urllib.parse.urlencode({"fromAccount": 1, "toAccount": 2, "amount": 1})
    status, _ = _request(
        f"http://127.0.0.1:{port}/api/v1/transfers?{query}",
        headers={
            "Idempotency-Key": "wrong-internal-token",
            "X-CloudBank-Actor": "cust-source",
            "X-CloudBank-Internal-Token": "incorrect",
        },
        method="POST",
    )
    return status


def _native_wave_lane(
    workspace: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
    pause: Callable[[float], None],
    progress: Callable[[str], None],
) -> dict[str, Any]:
    _inspect_image(POSTGRES_IMAGE, image_id, run)
    progress("Packaging Account and Transfer with the integrated-wave profile")
    build = run(
        ["mvn", "-pl", "account,transfer", "-am", "-DskipTests", "package"],
        cwd=workspace,
        env=os.environ.copy(),
        timeout=1200,
    )
    packaging = _package_inventory(workspace)
    if build.returncode or packaging != {
        "executable_jars": 2,
        "oracle_runtime_libraries": 0,
        "microtx_runtime_libraries": 0,
    }:
        return {
            "lane": "native-account-transfer-http",
            "status": "failed",
            "reason": "package-gate-failed",
            "maven_exit_code": build.returncode,
            "packaging": packaging,
            "stdout_sha256": hashlib.sha256(build.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(build.stderr.encode()).hexdigest(),
            "raw_output_persisted": False,
        }

    name = "lightyear-cb-ms60-pg-" + uuid.uuid4().hex[:10]
    database_password = "Ly" + secrets.token_hex(12) + "A1"
    internal_token = secrets.token_urlsafe(24)
    wave_password = secrets.token_urlsafe(18)
    account_port, transfer_port = _free_port(), _free_port()
    account_process: subprocess.Popen[bytes] | None = None
    transfer_process: subprocess.Popen[bytes] | None = None
    account_log = None
    transfer_log = None
    service_log_hashes: dict[str, list[str]] = {"account": [], "transfer": []}
    service_starts = {"account": 0, "transfer": 0}
    scenarios: list[dict[str, Any]] = []
    failure_reason: str | None = None
    started = run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            *_container_connectivity_args(5432), "--read-only", "--user", "70:70",
            "--pids-limit", "128", "--memory", "768m", "--cpus", "1.0",
            "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=384m,uid=70,gid=70",
            "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16m,uid=70,gid=70",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m,uid=70,gid=70",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "-e", f"POSTGRES_PASSWORD={database_password}", "-e", "POSTGRES_DB=cloudbank",
            f"sha256:{image_id}",
        ],
        timeout=120,
    )
    if started.returncode:
        return {
            "lane": "native-account-transfer-http",
            "status": "failed",
            "reason": "postgresql-start-failed",
            "packaging": packaging,
            "raw_output_persisted": False,
        }

    def record(identifier: str, passed: bool, **evidence: Any) -> None:
        scenarios.append(
            {"id": identifier, "status": "passed" if passed else "failed", **evidence}
        )

    try:
        progress("Starting native PostgreSQL, Account, and Transfer on loopback-only ports")
        _wait_postgres(name, run, pause)
        database_host, database_port = _container_endpoint(name, 5432, run)
        jdbc_url = f"jdbc:postgresql://{database_host}:{database_port}/cloudbank"
        common = {
            **os.environ,
            "SPRING_PROFILES_ACTIVE": "cloudbank-wave",
            "SERVER_ADDRESS": "127.0.0.1",
            "EUREKA_CLIENT_ENABLED": "false",
            "SPRING_CLOUD_DISCOVERY_ENABLED": "false",
            "SPRING_CLOUD_CONFIG_ENABLED": "false",
            "CLOUDBANK_SECURITY_REQUIRE_INTERNAL_TOKEN": "false",
            "CLOUDBANK_TRANSACTION_INTERNAL_TOKEN": internal_token,
        }
        account_env = {
            **common,
            "SERVER_PORT": str(account_port),
            "SPRING_DATASOURCE_URL": jdbc_url,
            "SPRING_DATASOURCE_USERNAME": "postgres",
            "SPRING_DATASOURCE_PASSWORD": database_password,
            "LIQUIBASE_DATASOURCE_URL": jdbc_url,
            "LIQUIBASE_DATASOURCE_USERNAME": "postgres",
            "LIQUIBASE_DATASOURCE_PASSWORD": database_password,
            "SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT": "org.hibernate.dialect.PostgreSQLDialect",
        }
        transfer_env = {
            **common,
            "SERVER_PORT": str(transfer_port),
            "ACCOUNT_TRANSACTION_URL": (
                f"http://127.0.0.1:{account_port}/api/v1/transfers"
            ),
            "CLOUDBANK_WAVE_USER_PASSWORD": wave_password,
        }
        account_jar = workspace / "account/target/account-0.0.1-SNAPSHOT.jar"
        transfer_jar = workspace / "transfer/target/transfer-0.0.1-SNAPSHOT.jar"
        account_process, account_log = _start_service(
            "account", account_jar, account_port, account_env, pause
        )
        service_starts["account"] += 1
        transfer_process, transfer_log = _start_service(
            "transfer", transfer_jar, transfer_port, transfer_env, pause
        )
        service_starts["transfer"] += 1
        record("services-healthy", True, account=True, transfer=True)

        progress("Exercising authentication, authorization, rejection, and success paths")
        _seed(name, run)
        initial = _state(name, run)
        status, _ = _transfer(transfer_port, wave_password, "no-auth", 1, 2, 1, None)
        record("external-authentication-required", status == 401, http_status=status)
        direct_status = _direct_account_wrong_token(account_port)
        record("internal-token-rejected", direct_status == 403, http_status=direct_status)
        status, _ = _transfer(
            transfer_port, wave_password, "invalid", 1, 2, 0, "cust-source"
        )
        record(
            "invalid-amount-rejected",
            status == 400 and _state(name, run) == initial,
            http_status=status,
        )
        status, _ = _transfer(
            transfer_port, wave_password, "wrong-owner", 1, 2, 10, "cust-attacker"
        )
        record(
            "owner-authorization-rejected",
            status == 400 and _state(name, run) == initial,
            http_status=status,
        )
        status, _ = _transfer(
            transfer_port, wave_password, "no-funds", 3, 2, 10, "cust-empty"
        )
        record(
            "insufficient-funds-rejected",
            status == 400 and _state(name, run) == initial,
            http_status=status,
        )

        status, body = _transfer(
            transfer_port, wave_password, "wave-success", 1, 2, 125, "cust-source"
        )
        successful = _state(name, run)
        expected_success = {
            "balance_1": 875,
            "balance_2": 375,
            "balance_3": 5,
            "journal_count": 2,
            "command_count": 1,
            "journal_net": 0,
        }
        record(
            "successful-value-conservation",
            status == 200 and body.get("accepted") is True and successful == expected_success,
            http_status=status,
            database_state=successful,
        )
        status, body = _transfer(
            transfer_port, wave_password, "wave-success", 1, 2, 125, "cust-source"
        )
        record(
            "duplicate-command-replayed",
            status == 200 and body.get("replayed") is True and _state(name, run) == successful,
            http_status=status,
        )

        progress("Restarting Transfer and proving durable replay through the live HTTP boundary")
        digest = _stop_service(transfer_process, transfer_log)
        if digest:
            service_log_hashes["transfer"].append(digest)
        transfer_process, transfer_log = None, None
        transfer_process, transfer_log = _start_service(
            "transfer", transfer_jar, transfer_port, transfer_env, pause
        )
        service_starts["transfer"] += 1
        status, body = _transfer(
            transfer_port, wave_password, "wave-success", 1, 2, 125, "cust-source"
        )
        record(
            "transfer-restart-replayed",
            status == 200 and body.get("replayed") is True and _state(name, run) == successful,
            http_status=status,
        )

        progress("Running concurrent opposite transfers and checking conservation and lock ordering")
        _seed(name, run)
        requests = []
        for index in range(4):
            requests.append((f"forward-{index}", 1, 2, "cust-source"))
            requests.append((f"reverse-{index}", 2, 1, "cust-target"))
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(
                    _transfer, transfer_port, wave_password, command, source, target, 10, user
                )
                for command, source, target, user in requests
            ]
            responses = [future.result() for future in futures]
        concurrent = _state(name, run)
        expected_concurrent = {
            "balance_1": 1000,
            "balance_2": 250,
            "balance_3": 5,
            "journal_count": 16,
            "command_count": 8,
            "journal_net": 0,
        }
        record(
            "concurrent-opposite-transfers-conserve-value",
            all(status == 200 for status, _ in responses)
            and concurrent == expected_concurrent,
            requests=len(responses),
            database_state=concurrent,
        )

        progress("Restarting Account and proving command replay survives process loss")
        digest = _stop_service(account_process, account_log)
        if digest:
            service_log_hashes["account"].append(digest)
        account_process, account_log = None, None
        account_process, account_log = _start_service(
            "account", account_jar, account_port, account_env, pause
        )
        service_starts["account"] += 1
        status, body = _transfer(
            transfer_port, wave_password, "forward-0", 1, 2, 10, "cust-source"
        )
        record(
            "account-restart-replayed",
            status == 200 and body.get("replayed") is True and _state(name, run) == concurrent,
            http_status=status,
        )
    except Exception as exception:
        safe_reason = str(exception)
        if safe_reason not in {
            "account-exited-before-health",
            "account-health-timeout",
            "transfer-exited-before-health",
            "transfer-health-timeout",
            "postgresql-query-failed",
        }:
            safe_reason = type(exception).__name__
        failure_reason = f"runtime-gate-failed:{safe_reason}"
    finally:
        digest = _stop_service(transfer_process, transfer_log)
        if digest:
            service_log_hashes["transfer"].append(digest)
        digest = _stop_service(account_process, account_log)
        if digest:
            service_log_hashes["account"].append(digest)
        database_password = ""
        internal_token = ""
        wave_password = ""
        run(["docker", "rm", "-f", name], timeout=30)

    passed = (
        failure_reason is None
        and [item["id"] for item in scenarios] == SCENARIO_IDS
        and all(item["status"] == "passed" for item in scenarios)
        and service_starts == {"account": 2, "transfer": 2}
    )
    return {
        "lane": "native-account-transfer-http",
        "status": "passed" if passed else "failed",
        "reason": failure_reason,
        "database_image_id_sha256": image_id,
        "contract_sha256": CONTRACT_SHA256 if passed else None,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "service_starts": service_starts,
        "service_log_sha256": service_log_hashes,
        "packaging": packaging,
        "maven_exit_code": build.returncode,
        "maven_stdout_sha256": hashlib.sha256(build.stdout.encode()).hexdigest(),
        "maven_stderr_sha256": hashlib.sha256(build.stderr.encode()).hexdigest(),
        "ports": "ephemeral-loopback-only",
        "synthetic_data_only": True,
        "raw_output_persisted": False,
    }


def execute_native_wave(
    project_root: Path,
    source_root: Path,
    ms59_receipt: Mapping[str, Any],
    output_root: Path,
    key: str,
    signer: str,
    run_id: str | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = _run,
    pause: Callable[[float], None] = time.sleep,
    progress: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    progress("Validating MS #60 artifacts, pinned source, and signed MS #59 receipt")
    errors = validate_artifacts(project_root)
    errors.extend(validate_source(source_root))
    errors.extend(validate_ms59_receipt(ms59_receipt, key, project_root))
    if ms59_receipt.get("receipt_type") != MS59_RECEIPT_TYPE:
        errors.append("cloudbank-native-wave-ms59-receipt-required")
    if errors:
        raise ValueError(",".join(sorted(set(errors))))
    image_id = str(ms59_receipt.get("postgresql_image_id_sha256", ""))
    if not HEX_64.fullmatch(image_id):
        raise ValueError("cloudbank-native-wave-image-identity-invalid")
    run_name = run_id or f"cloudbank-native-wave-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    run_root = output_root / "runs" / run_name
    progress("Materializing the isolated MS #59 target and MS #60 integration profile")
    workspace = materialize_target(project_root, source_root, run_root / "workspace")
    lane = _native_wave_lane(workspace, image_id, run, pause, progress)
    if lane["status"] != "passed":
        write_json(
            output_root / FAILURE_NAME,
            {
                "schema_version": "1.0",
                "release": RELEASE,
                "run_id": run_name,
                "status": "failed",
                "lane": lane,
            },
        )
        raise ValueError("cloudbank-native-wave-acceptance-failed")
    progress("All integrated gates passed; signing the bounded MS #60 receipt")
    receipt = sign(
        {
            "schema_version": "1.0",
            "receipt_type": RECEIPT_TYPE,
            "release": RELEASE,
            "run_id": run_name,
            "source_ms59_receipt_sha256": ms59_receipt["content_sha256"],
            "postgresql_image_id_sha256": image_id,
            "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
            "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
            "changed_paths": changed_paths(),
            "native_wave_lane": lane,
            "status": "passed-bounded-native-account-transfer-wave",
            "integrated_target_generated": True,
            "native_postgresql_transaction_core_observed": True,
            "native_transaction_wave_observed": True,
            "native_lra_replacement_observed": True,
            "durable_restart_replay_observed": True,
            "concurrent_value_conservation_observed": True,
            "production_identity_qualified": False,
            "native_messaging_observed": False,
            "oracle_transaction_wave_observed": False,
            "oracle_postgresql_equivalent": False,
            "remaining_service_workcells_complete": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
            "security": {
                "source_checkout_mutated": False,
                "synthetic_data_only": True,
                "credentials_persisted": False,
                "raw_service_logs_persisted": False,
                "ports": "ephemeral-loopback-only",
                "authentication_profile": "development-basic-auth-only",
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
        errors.append("cloudbank-native-wave-receipt-identity-invalid")
    if receipt.get("status") != "passed-bounded-native-account-transfer-wave":
        errors.append("cloudbank-native-wave-receipt-status-invalid")
    if receipt.get("content_sha256") != content_hash(dict(receipt)):
        errors.append("cloudbank-native-wave-receipt-content-hash-invalid")
    if not key or not verify_signature(dict(receipt), key):
        errors.append("cloudbank-native-wave-receipt-signature-invalid")
    if receipt.get("execution_plan_sha256") != execution_plan(project_root)["content_sha256"]:
        errors.append("cloudbank-native-wave-receipt-plan-invalid")
    if receipt.get("acceptance_contract_sha256") != acceptance_contract(project_root)["content_sha256"]:
        errors.append("cloudbank-native-wave-receipt-contract-invalid")
    if receipt.get("changed_paths") != changed_paths():
        errors.append("cloudbank-native-wave-receipt-paths-invalid")
    lane = receipt.get("native_wave_lane", {})
    if not isinstance(lane, Mapping):
        errors.append("cloudbank-native-wave-receipt-lane-invalid")
    else:
        scenarios = lane.get("scenarios", [])
        if any(
            (
                lane.get("status") != "passed",
                lane.get("scenario_count") != EXPECTED_SCENARIOS,
                not isinstance(scenarios, list),
                [item.get("id") for item in scenarios] != SCENARIO_IDS
                if isinstance(scenarios, list) else True,
                any(item.get("status") != "passed" for item in scenarios)
                if isinstance(scenarios, list) else True,
                lane.get("service_starts") != {"account": 2, "transfer": 2},
                lane.get("contract_sha256") != CONTRACT_SHA256,
                lane.get("packaging") != {
                    "executable_jars": 2,
                    "oracle_runtime_libraries": 0,
                    "microtx_runtime_libraries": 0,
                },
                lane.get("ports") != "ephemeral-loopback-only",
                lane.get("synthetic_data_only") is not True,
                lane.get("raw_output_persisted") is not False,
            )
        ):
            errors.append("cloudbank-native-wave-receipt-lane-invalid")
    required_true = (
        "integrated_target_generated",
        "native_postgresql_transaction_core_observed",
        "native_transaction_wave_observed",
        "native_lra_replacement_observed",
        "durable_restart_replay_observed",
        "concurrent_value_conservation_observed",
    )
    required_false = (
        "production_identity_qualified",
        "native_messaging_observed",
        "oracle_transaction_wave_observed",
        "oracle_postgresql_equivalent",
        "remaining_service_workcells_complete",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    )
    if any(receipt.get(name) is not True for name in required_true) or any(
        receipt.get(name) is not False for name in required_false
    ):
        errors.append("cloudbank-native-wave-receipt-claims-invalid")
    for name in ("source_ms59_receipt_sha256", "postgresql_image_id_sha256"):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"cloudbank-native-wave-receipt-hash-invalid:{name}")
    errors.extend(validate_artifacts(project_root))
    return sorted(set(errors))
