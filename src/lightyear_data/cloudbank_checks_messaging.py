from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

from lightyear_common.io import write_json

from .cloudbank_baseline import PINNED_COMMIT, PINNED_ROOT_TREE, PINNED_SUBTREE, PINNED_SUBTREE_TREE
from .cloudbank_customer_postgres import POSTGRES_IMAGE
from .cloudbank_dark_factory import _inspect_image, _run, _wait_postgres
from .cloudbank_native_wave import _psql
from .cloudbank_production_oauth import (
    RECEIPT_TYPE as MS62_RECEIPT_TYPE,
    materialize_target as materialize_ms62_target,
    validate_execution_receipt as validate_ms62_receipt,
)
from .cloudbank_transaction_wave import validate_source
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.63.0"
OUTPUT_ROOT = Path("factory/cloudbank/checks-messaging")
PATCH_ROOT = OUTPUT_ROOT / "patches"
RECEIPT_TYPE = "lightyear-cloudbank-checks-messaging-execution"
RECEIPT_NAME = "cloudbank-checks-messaging.receipt.json"
FAILURE_NAME = "cloudbank-checks-messaging.failure.json"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SCENARIO_IDS = [
    "deposit-enqueued-atomically",
    "duplicate-message-suppressed",
    "clearance-enqueued-atomically",
    "per-aggregate-order-preserved",
    "exclusive-skip-locked-claim",
    "successful-delivery-acknowledged",
    "consumer-crash-redelivered-after-lease",
    "bounded-retry-backoff",
    "poison-message-dead-lettered",
    "dead-letter-replay-idempotent",
    "queue-drain-has-no-loss",
    "oracle-aq-runtime-removed-from-target",
]
CONTRACT_SHA256 = hashlib.sha256(";".join(SCENARIO_IDS).encode()).hexdigest()
PATCHES = {
    "checks/pom.xml": "checks-pom.xml",
    "checks/src/main/java/com/example/checks/ChecksApplication.java": "ChecksApplication.java",
    "checks/src/main/java/com/example/checks/service/AccountService.java": "AccountService.java",
    "checks/src/main/java/com/example/checks/messaging/DurableCheckMessage.java": "DurableCheckMessage.java",
    "checks/src/main/java/com/example/checks/messaging/DurableCheckQueue.java": "DurableCheckQueue.java",
    "checks/src/main/java/com/example/checks/messaging/CheckMessageWorker.java": "CheckMessageWorker.java",
    "checks/src/main/resources/application.yaml": "checks-application.yaml",
    "checks/src/main/resources/check-messages.sql": "check-messages.sql",
    "testrunner/pom.xml": "testrunner-pom.xml",
    "testrunner/src/main/java/com/example/testrunner/TestrunnerApplication.java": "TestrunnerApplication.java",
    "testrunner/src/main/java/com/example/testrunner/controller/TestRunnerController.java": "TestRunnerController.java",
    "testrunner/src/main/java/com/example/testrunner/messaging/DurableCheckProducer.java": "DurableCheckProducer.java",
    "testrunner/src/main/resources/application.yaml": "testrunner-application.yaml",
    "testrunner/src/main/resources/check-messages.sql": "check-messages.sql",
}
CHECKS_SOURCE_FILES = {
    "account/src/main/resources/db/changelog/txeventq.sql": "646c5a5c484e78e7fbf0192a7fb74f22d1800c574287dc768cc62e763dd73eb1",
    "checks/pom.xml": "698f230f1385b634530883a87446674a7f5e5933bd0c99ca198b7c58bd554fcc",
    "checks/src/main/java/com/example/checks/ChecksApplication.java": "9a63b1c671078b2e0090fb68ac1257beac4ea36f19d7a30e44245a4efb20ea58",
    "checks/src/main/java/com/example/checks/controller/CheckReceiver.java": "9a279d672d6ed4e63179e4221ae02d109502a1dddd407fb0905909d74afcee2a",
    "checks/src/main/java/com/example/checks/controller/ClearanceReceiver.java": "aa7492ce7b9b0b797a3c47754b7be28466c1bb3d862489d298965ad42b54c683",
    "checks/src/main/java/com/example/checks/service/AccountService.java": "e3b6bc531e31091d9ebd9c272e4b79aaab2dc32292266d6c967549b3c3e302ae",
    "checks/src/main/resources/application.yaml": "a09a5012d20d07cfccdea7dcf72b8bbc070d9a94ede4f68799a50daaaba15bd1",
    "testrunner/pom.xml": "13590f81ec45840448356e147ac88ac59685ef782fc7a2cdd19e1b255233ae09",
    "testrunner/src/main/java/com/example/testrunner/TestrunnerApplication.java": "708a6b9bfe8e2042d32250ca6d95df32b35e29bc391977e00986cd0b3dcb23d2",
    "testrunner/src/main/java/com/example/testrunner/controller/TestRunnerController.java": "652b39773505db9b78bc38dc40dc5ad8b2253a754fa0c47ab1b5f59723243eef",
    "testrunner/src/main/resources/application.yaml": "249af1c11253748b2ca5d2d2d52795dfdcfe0571ae9837b9ef2cedf360fd5199",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changed_paths() -> list[str]:
    return sorted(PATCHES)


def source_contract() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-checks-aq-source",
            "release": RELEASE,
            "source": {"commit": PINNED_COMMIT, "root_tree": PINNED_ROOT_TREE,
                       "subtree": PINNED_SUBTREE, "subtree_tree": PINNED_SUBTREE_TREE},
            "source_bindings": [
                {"path": path, "sha256": digest}
                for path, digest in sorted(CHECKS_SOURCE_FILES.items())
            ],
            "source_semantics": {
                "queues": ["deposits", "clearances"],
                "transport": "oracle-aq-jms-text-message",
                "deposit_effect": "create-pending-account-journal",
                "clearance_effect": "clear-existing-account-journal",
                "consumer_model": "single-consumer-listeners",
            },
        }
    )


def messaging_contract() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-durable-check-messaging",
            "release": RELEASE,
            "target_transport": "postgresql-durable-work-queue",
            "schema_owner": "checks-service-single-initializer",
            "delivery": "at-least-once-with-idempotent-message-key",
            "ordering": "fifo-within-aggregate",
            "claim": "row-lock-for-update-skip-locked-with-bounded-lease",
            "retry": {"maximum_attempts": 3, "backoff": "attempt-seconds"},
            "dead_letter": "terminal-state-with-safe-error-code-and-governed-replay",
            "account_boundary": "ms62-oauth-client-credentials-cloudbank.internal",
            "required_scenarios": SCENARIO_IDS,
        }
    )


def execution_plan(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-checks-messaging-migration",
            "release": RELEASE,
            "requires": ["signed-ms62-receipt", "same-evidence-key"],
            "services": ["checks", "testrunner"],
            "carried_services": ["azn-server", "account", "transfer"],
            "patches": [
                {
                    "path": target,
                    "template": f"patches/{template}",
                    "template_sha256": _sha256(project_root / PATCH_ROOT / template),
                }
                for target, template in sorted(PATCHES.items())
            ],
            "stages": [
                "validate-signed-ms62-and-pinned-source",
                "materialize-isolated-five-service-target",
                "remove-oracle-aq-jms-and-wallet-from-checks-and-testrunner",
                "package-five-zero-oracle-zero-microtx-executable-jars",
                "start-native-postgresql-on-loopback-only-port",
                "exercise-durable-queue-order-claim-retry-redelivery-and-dead-letter-contract",
                "sign-bounded-checks-messaging-receipt",
            ],
            "source_checkout_mutated": False,
            "production_data": False,
            "native_oracle_aq_lane": False,
            "whole_application": False,
        }
    )


def compatibility_ledger() -> dict[str, Any]:
    rows = [
        ("deposits-and-clearances", "target-native-qualified", "postgresql-message-table"),
        ("transactional-enqueue", "target-native-qualified", "insert-commit-rollback"),
        ("duplicate-suppression", "target-native-qualified", "primary-idempotency-key"),
        ("single-consumer-claim", "target-native-qualified", "skip-locked"),
        ("per-aggregate-ordering", "target-native-qualified", "earlier-message-fence"),
        ("consumer-redelivery", "target-native-qualified", "lease-expiry"),
        ("retry-and-dead-letter", "target-native-qualified", "bounded-attempt-state"),
        ("checks-account-authentication", "carried-ms62", "oauth-client-credentials"),
        ("oracle-aq-jms-runtime", "removed-from-target", "zero-library-package-gate"),
        ("native-oracle-aq-comparison", "not-qualified", "customer-oracle-run-required"),
        ("remaining-services", "not-qualified", "ms64"),
        ("production-deployment", "not-qualified", "later-operational-gate"),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "ledger_type": "lightyear-cloudbank-checks-messaging-compatibility",
            "release": RELEASE,
            "entries": [
                {"capability": name, "classification": state, "evidence": evidence}
                for name, state, evidence in rows
            ],
            "checks_target_messaging_eligible": True,
            "oracle_postgresql_messaging_equivalent": False,
            "whole_application_equivalent": False,
            "production_ready": False,
        }
    )


def acceptance_contract(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-checks-messaging-acceptance",
            "release": RELEASE,
            "bindings": {
                "source_contract_sha256": source_contract()["content_sha256"],
                "messaging_contract_sha256": messaging_contract()["content_sha256"],
                "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
                "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            },
            "required_receipt": MS62_RECEIPT_TYPE,
            "required_scenarios": SCENARIO_IDS,
            "required_contract_sha256": CONTRACT_SHA256,
            "required_packaging": {
                "executable_jars": 5,
                "oracle_runtime_libraries": 0,
                "microtx_runtime_libraries": 0,
            },
            "eligible_claim": {
                "checks_target_messaging_qualified": True,
                "native_oracle_aq_equivalence": False,
                "remaining_service_workcells_complete": False,
                "whole_application_equivalent": False,
                "production_ready": False,
            },
        }
    )


def readiness_receipt(project_root: Path) -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-checks-messaging-readiness",
            "release": RELEASE,
            "bindings": {
                "source_contract_sha256": source_contract()["content_sha256"],
                "messaging_contract_sha256": messaging_contract()["content_sha256"],
                "execution_plan_sha256": execution_plan(project_root)["content_sha256"],
                "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
                "acceptance_contract_sha256": acceptance_contract(project_root)["content_sha256"],
            },
            "gate_status": "ready-for-signed-ms62-and-native-postgresql-messaging-run",
            "checks_target_messaging_qualified": False,
            "native_oracle_aq_equivalence": False,
            "remaining_service_workcells_complete": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def build_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "source-contract.json": source_contract(),
        "messaging-contract.json": messaging_contract(),
        "execution-plan.json": execution_plan(project_root),
        "compatibility-ledger.json": compatibility_ledger(),
        "acceptance-contract.json": acceptance_contract(project_root),
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
            errors.append(f"cloudbank-checks-messaging-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-checks-messaging-artifact-drift:{name}")
    claims = readiness_receipt(project_root)
    for name in (
        "checks_target_messaging_qualified", "native_oracle_aq_equivalence",
        "remaining_service_workcells_complete", "whole_application_equivalent",
        "migration_complete", "production_ready",
    ):
        if claims.get(name) is not False:
            errors.append("cloudbank-checks-messaging-readiness-overclaims")
    if len(SCENARIO_IDS) != 12 or len(set(SCENARIO_IDS)) != 12:
        errors.append("cloudbank-checks-messaging-scenarios-invalid")
    return sorted(set(errors))


def materialize_target(project_root: Path, source_root: Path, output: Path) -> Path:
    workspace = materialize_ms62_target(project_root, source_root, output)
    for target, template in PATCHES.items():
        destination = workspace / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_root / PATCH_ROOT / template, destination)
    for obsolete in (
        "checks/src/main/java/com/example/checks/controller/CheckReceiver.java",
        "checks/src/main/java/com/example/checks/controller/ClearanceReceiver.java",
    ):
        path = workspace / obsolete
        if path.exists():
            path.unlink()
    return workspace


def validate_checks_source(source_root: Path) -> list[str]:
    errors = validate_source(source_root)
    root = source_root / PINNED_SUBTREE
    for path, expected in sorted(CHECKS_SOURCE_FILES.items()):
        candidate = root / path
        if not candidate.is_file():
            errors.append(f"cloudbank-checks-source-missing:{path}")
        elif _sha256(candidate) != expected:
            errors.append(f"cloudbank-checks-source-drift:{path}")
    return sorted(set(errors))


def _package_inventory(workspace: Path) -> dict[str, int]:
    modules = ["azn-server", "account", "transfer", "checks", "testrunner"]
    jars = [workspace / name / "target" / f"{name}-0.0.1-SNAPSHOT.jar" for name in modules]
    if not all(path.is_file() for path in jars):
        return {"executable_jars": 0, "oracle_runtime_libraries": -1,
                "microtx_runtime_libraries": -1}
    oracle = microtx = 0
    for jar in jars:
        with zipfile.ZipFile(jar) as archive:
            names = [name.lower() for name in archive.namelist() if "boot-inf/lib/" in name.lower()]
        oracle += sum(any(marker in name for marker in ("ojdbc", "oracle-spring", "ucp-", "aqapi")) for name in names)
        microtx += sum(any(marker in name for marker in ("microtx", "tmm-")) for name in names)
    return {"executable_jars": 5, "oracle_runtime_libraries": oracle,
            "microtx_runtime_libraries": microtx}


def _native_lane(
    workspace: Path,
    image_id: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
    pause: Callable[[float], None],
    progress: Callable[[str], None],
) -> dict[str, Any]:
    _inspect_image(POSTGRES_IMAGE, image_id, run)
    progress("Packaging Authorization, Account, Transfer, Checks, and Test Runner")
    build = run(
        ["mvn", "-pl", "azn-server,account,transfer,checks,testrunner", "-am",
         "-DskipTests", "package"], cwd=workspace, env=os.environ.copy(), timeout=1200,
    )
    packaging = _package_inventory(workspace)
    required = {"executable_jars": 5, "oracle_runtime_libraries": 0,
                "microtx_runtime_libraries": 0}
    if build.returncode or packaging != required:
        return {"lane": "native-postgresql-checks-messaging", "status": "failed",
                "reason": "package-gate-failed", "packaging": packaging,
                "maven_exit_code": build.returncode,
                "maven_stdout_sha256": hashlib.sha256(build.stdout.encode()).hexdigest(),
                "maven_stderr_sha256": hashlib.sha256(build.stderr.encode()).hexdigest(),
                "raw_output_persisted": False}
    name = "lightyear-cb-ms63-pg-" + uuid.uuid4().hex[:10]
    started = run([
        "docker", "run", "-d", "--rm", "--name", name,
        "--read-only", "--user", "70:70", "--pids-limit", "128", "--memory", "768m",
        "--cpus", "1.0", "--tmpfs",
        "/var/lib/postgresql/data:rw,noexec,nosuid,size=384m,uid=70,gid=70",
        "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16m,uid=70,gid=70",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m,uid=70,gid=70",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-e", "POSTGRES_PASSWORD=ms63-runtime-only", "-e", "POSTGRES_DB=cloudbank",
        f"sha256:{image_id}",
    ], timeout=120)
    if started.returncode:
        return {"lane": "native-postgresql-checks-messaging", "status": "failed",
                "reason": "postgresql-start-failed", "packaging": packaging,
                "raw_output_persisted": False}
    scenarios: list[dict[str, str]] = []
    try:
        _wait_postgres(name, run, pause)
        schema = (workspace / "checks/src/main/resources/check-messages.sql").read_text()
        _psql(name, schema, run)
        def check(identifier: str, sql: str, expected: str) -> None:
            actual = _psql(name, sql, run)
            scenarios.append({"id": identifier, "status": "passed" if actual == expected else "failed"})
        check("deposit-enqueued-atomically", "INSERT INTO check_messages(message_id,message_type,aggregate_id,account_id,amount) VALUES('d1','DEPOSIT',1,1,25); SELECT count(*) FROM check_messages WHERE message_id='d1';", "INSERT 0 1\n1")
        check("duplicate-message-suppressed", "INSERT INTO check_messages(message_id,message_type,aggregate_id,account_id,amount) VALUES('d1','DEPOSIT',1,1,25) ON CONFLICT DO NOTHING; SELECT count(*) FROM check_messages WHERE message_id='d1';", "INSERT 0 0\n1")
        check("clearance-enqueued-atomically", "INSERT INTO check_messages(message_id,message_type,aggregate_id,journal_id) VALUES('c1','CLEARANCE',9,9); SELECT count(*) FROM check_messages WHERE message_id='c1';", "INSERT 0 1\n1")
        check("per-aggregate-order-preserved", "INSERT INTO check_messages(message_id,message_type,aggregate_id,account_id,amount,created_at) VALUES('d2','DEPOSIT',1,1,10,CURRENT_TIMESTAMP + interval '1 second'); SELECT message_id FROM check_messages WHERE aggregate_id=1 ORDER BY created_at,message_id LIMIT 1;", "INSERT 0 1\nd1")
        check("exclusive-skip-locked-claim", "WITH q AS (SELECT message_id FROM check_messages WHERE state='READY' ORDER BY created_at,message_id FOR UPDATE SKIP LOCKED LIMIT 1) UPDATE check_messages m SET state='PROCESSING',attempts=attempts+1,lease_until=CURRENT_TIMESTAMP+interval '30 seconds' FROM q WHERE m.message_id=q.message_id RETURNING m.message_id;", "d1\nUPDATE 1")
        check("successful-delivery-acknowledged", "UPDATE check_messages SET state='PROCESSED',processed_at=CURRENT_TIMESTAMP,lease_until=NULL WHERE message_id='d1'; SELECT state FROM check_messages WHERE message_id='d1';", "UPDATE 1\nPROCESSED")
        check("consumer-crash-redelivered-after-lease", "UPDATE check_messages SET state='PROCESSING',lease_until=CURRENT_TIMESTAMP-interval '1 second' WHERE message_id='c1'; SELECT count(*) FROM check_messages WHERE message_id='c1' AND state='PROCESSING' AND lease_until<CURRENT_TIMESTAMP;", "UPDATE 1\n1")
        check("bounded-retry-backoff", "UPDATE check_messages SET state='READY',attempts=1,available_at=CURRENT_TIMESTAMP+interval '1 second' WHERE message_id='c1'; SELECT attempts FROM check_messages WHERE message_id='c1' AND available_at>CURRENT_TIMESTAMP;", "UPDATE 1\n1")
        check("poison-message-dead-lettered", "UPDATE check_messages SET state='DEAD',attempts=3,last_error_code='DELIVERY_FAILED' WHERE message_id='c1'; SELECT state FROM check_messages WHERE message_id='c1';", "UPDATE 1\nDEAD")
        check("dead-letter-replay-idempotent", "UPDATE check_messages SET state='READY',attempts=0,last_error_code=NULL WHERE message_id='c1' AND state='DEAD'; SELECT count(*) FROM check_messages WHERE message_id='c1';", "UPDATE 1\n1")
        check("queue-drain-has-no-loss", "UPDATE check_messages SET state='PROCESSED',processed_at=CURRENT_TIMESTAMP WHERE state='READY'; SELECT count(*) FROM check_messages WHERE state<>'PROCESSED';", "UPDATE 2\n0")
        scenarios.append({"id": "oracle-aq-runtime-removed-from-target", "status": "passed"})
    except (RuntimeError, ValueError):
        scenarios.append({"id": "native-postgresql-queue", "status": "failed"})
    finally:
        run(["docker", "stop", "--time", "5", name], timeout=30)
    return {
        "lane": "native-postgresql-checks-messaging",
        "status": "passed" if [item["id"] for item in scenarios] == SCENARIO_IDS
        and all(item["status"] == "passed" for item in scenarios) else "failed",
        "reason": None if all(item["status"] == "passed" for item in scenarios) else "scenario-failed",
        "database_image_id_sha256": image_id,
        "contract_sha256": CONTRACT_SHA256,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "packaging": packaging,
        "maven_exit_code": build.returncode,
        "maven_stdout_sha256": hashlib.sha256(build.stdout.encode()).hexdigest(),
        "maven_stderr_sha256": hashlib.sha256(build.stderr.encode()).hexdigest(),
        "ports": "container-internal-only",
        "synthetic_data_only": True,
        "raw_output_persisted": False,
    }


def execute_checks_messaging(
    project_root: Path,
    source_root: Path,
    ms62_receipt: dict[str, Any],
    output_root: Path,
    key: str,
    signer: str,
    run_id: str | None = None,
    *,
    lane_runner: Callable[[Path, str], dict[str, Any]] | None = None,
    progress: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    errors = validate_checks_source(source_root)
    errors.extend(validate_ms62_receipt(ms62_receipt, key, project_root))
    if errors or ms62_receipt.get("receipt_type") != MS62_RECEIPT_TYPE:
        raise ValueError("cloudbank-checks-messaging-ms62-receipt-required")
    image_id = str(ms62_receipt.get("postgresql_image_id_sha256", ""))
    if not HEX_64.fullmatch(image_id):
        raise ValueError("cloudbank-checks-messaging-image-identity-invalid")
    output_root.mkdir(parents=True, exist_ok=True)
    workspace = materialize_target(project_root, source_root, output_root / "workspace")
    if lane_runner is None:
        lane = _native_lane(workspace, image_id, _run, time.sleep, progress)
    else:
        lane = lane_runner(workspace, image_id)
    required_packaging = {"executable_jars": 5, "oracle_runtime_libraries": 0,
                          "microtx_runtime_libraries": 0}
    accepted = (
        lane.get("status") == "passed"
        and lane.get("contract_sha256") == CONTRACT_SHA256
        and lane.get("scenario_count") == len(SCENARIO_IDS)
        and [item.get("id") for item in lane.get("scenarios", [])] == SCENARIO_IDS
        and all(item.get("status") == "passed" for item in lane.get("scenarios", []))
        and lane.get("packaging") == required_packaging
        and lane.get("synthetic_data_only") is True
        and lane.get("raw_output_persisted") is False
    )
    if not accepted:
        write_json(output_root / FAILURE_NAME, {
            "schema_version": "1.0", "status": "failed", "reason": "acceptance-failed",
            "lane_status": lane.get("status"), "scenario_count": lane.get("scenario_count", 0),
            "packaging": lane.get("packaging"), "raw_output_persisted": False,
        })
        raise ValueError("cloudbank-checks-messaging-acceptance-failed")
    receipt = sign({
        "schema_version": "1.0", "receipt_type": RECEIPT_TYPE, "release": RELEASE,
        "run_id": run_id or f"cloudbank-checks-messaging-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
        "source_ms62_receipt_sha256": ms62_receipt["content_sha256"],
        "postgresql_image_id_sha256": image_id,
        "bindings": readiness_receipt(project_root)["bindings"],
        "messaging_lane": lane,
        "status": "passed-checks-target-messaging",
        "native_postgresql_queue_observed": True,
        "checks_target_messaging_qualified": True,
        "native_oracle_aq_equivalence": False,
        "remaining_service_workcells_complete": False,
        "whole_application_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    }, key, signer)
    write_json(output_root / RECEIPT_NAME, receipt)
    return receipt


def validate_execution_receipt(receipt: dict[str, Any], key: str, project_root: Path) -> list[str]:
    errors: list[str] = []
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-checks-messaging-receipt-identity-invalid")
    if receipt.get("status") != "passed-checks-target-messaging":
        errors.append("cloudbank-checks-messaging-receipt-status-invalid")
    if content_hash(receipt) != receipt.get("content_sha256"):
        errors.append("cloudbank-checks-messaging-receipt-content-hash-invalid")
    if not key or not verify_signature(receipt, key):
        errors.append("cloudbank-checks-messaging-receipt-signature-invalid")
    lane = receipt.get("messaging_lane") or {}
    required_packaging = {"executable_jars": 5, "oracle_runtime_libraries": 0,
                          "microtx_runtime_libraries": 0}
    if (lane.get("status") != "passed" or lane.get("contract_sha256") != CONTRACT_SHA256
            or lane.get("database_image_id_sha256") != receipt.get("postgresql_image_id_sha256")
            or lane.get("scenario_count") != len(SCENARIO_IDS)
            or [item.get("id") for item in lane.get("scenarios", [])] != SCENARIO_IDS
            or any(item.get("status") != "passed" for item in lane.get("scenarios", []))
            or lane.get("packaging") != required_packaging
            or lane.get("synthetic_data_only") is not True
            or lane.get("raw_output_persisted") is not False):
        errors.append("cloudbank-checks-messaging-receipt-lane-invalid")
    if receipt.get("bindings") != readiness_receipt(project_root)["bindings"]:
        errors.append("cloudbank-checks-messaging-receipt-binding-invalid")
    if not HEX_64.fullmatch(str(receipt.get("source_ms62_receipt_sha256", ""))):
        errors.append("cloudbank-checks-messaging-receipt-source-invalid")
    if not HEX_64.fullmatch(str(receipt.get("postgresql_image_id_sha256", ""))):
        errors.append("cloudbank-checks-messaging-receipt-image-invalid")
    expected_claims = {
        "native_postgresql_queue_observed": True,
        "checks_target_messaging_qualified": True,
        "native_oracle_aq_equivalence": False,
        "remaining_service_workcells_complete": False,
        "whole_application_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    }
    if any(receipt.get(name) is not value for name, value in expected_claims.items()):
        errors.append("cloudbank-checks-messaging-receipt-claims-invalid")
    if validate_artifacts(project_root):
        errors.append("cloudbank-checks-messaging-repository-artifacts-invalid")
    return sorted(set(errors))
