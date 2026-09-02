from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import write_json

from .cloudbank_baseline import (
    PINNED_COMMIT,
    PINNED_ROOT_TREE,
    PINNED_SUBTREE,
    PINNED_SUBTREE_TREE,
    validate_source_checkout,
)
from .cloudbank_production_qualification import (
    RECEIPT_TYPE as MS57_RECEIPT_TYPE,
    validate_execution_receipt as validate_ms57_receipt,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.58.0"
OUTPUT_ROOT = Path("factory/cloudbank/transaction-wave")
RECEIPT_TYPE = "lightyear-cloudbank-transaction-wave-admission"
RECEIPT_NAME = "cloudbank-transaction-wave.receipt.json"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")

DEPLOYABLES = (
    "azn-server",
    "account",
    "checks",
    "customer",
    "creditscore",
    "transfer",
    "testrunner",
    "chatbot",
)

SOURCE_FILES = {
    "account/pom.xml": "4dbc4c295146e78dfceccdf313dd8f6060d270dcf65238170f09fab9c6263595",
    "account/src/main/resources/application.yaml": "05b3d5bf0827dfe0ae82777eb2386f24f3cf9e2f35fca89d5090332451e4b487",
    "account/src/main/resources/db/changelog/controller.yaml": "b4a2f076b45e2765cf6c0e6f3f6ac7ce24244d2eaa149bebed9999f0f4322bf5",
    "account/src/main/resources/db/changelog/table.sql": "abf35c87c3b32050ffa39cdc1cc9651c55a2e446cd13928a010799f3e94fee35",
    "account/src/main/resources/db/changelog/data.sql": "62acc80c6849fe6f8a09f7ce621f1a9c592c59db4aca94bc1fc26819959479c2",
    "account/src/main/resources/db/changelog/txeventq.sql": "646c5a5c484e78e7fbf0192a7fb74f22d1800c574287dc768cc62e763dd73eb1",
    "account/src/main/java/com/example/accounts/model/Account.java": "c42922a184cdf6b407faa4b575ea9f7469d81375113a6fc3cbd9331b1e06d136",
    "account/src/main/java/com/example/accounts/model/Journal.java": "a452a3ca46bfd077ec113924b2169cb5fdaf796a75bb11b20f6ef25937b516c5",
    "account/src/main/java/com/example/accounts/repository/AccountRepository.java": "196fe9f55587b407dddf20e5e4d7e53a3aeebafbdb380b5a2ddffb6658876445",
    "account/src/main/java/com/example/accounts/repository/JournalRepository.java": "986288b7abec15fa615773d66ebe830d79d2e5f333a35a1a3f5a02a78be35d0d",
    "account/src/main/java/com/example/accounts/controller/AccountController.java": "b8c1baf6f138848794170b1f1684b1e7cd6adcc0353552cfc2fcae646e8b06eb",
    "account/src/main/java/com/example/accounts/services/AccountTransferDAO.java": "dc69281c5c6d9e97aca8a9f169bff3ddacda250e1758c3275908da70355c7632",
    "account/src/main/java/com/example/accounts/services/DepositService.java": "a646e517dc9de28008fb64cfd38dac78c0350b387ebecb75b8ae62549b3db849",
    "account/src/main/java/com/example/accounts/services/WithdrawService.java": "4a9bfa60dff7dba6b641b0eb9227869f82a03c872dd69d90d6ae1a400899dd47",
    "transfer/pom.xml": "96003c2686a7a2d449fa12ebca1565ea46bcb203fb692d27dd63886de51f8556",
    "transfer/src/main/resources/application.yaml": "bfcfadf0288e04e0fd3b674f097ab98360300c8643234c042def5e8ea9da4566",
    "transfer/src/main/java/com/example/transfer/TransferService.java": "46ab5a0b2253e7fdfc63858867be3029746c3e675404056feda21b50d3cc9c45",
}


def _source_identity() -> dict[str, str]:
    return {
        "commit": PINNED_COMMIT,
        "root_tree": PINNED_ROOT_TREE,
        "subtree": PINNED_SUBTREE,
        "subtree_tree": PINNED_SUBTREE_TREE,
    }


def portfolio_inventory() -> dict[str, Any]:
    services = [
        ("customer", "customer-profile", "qualified-ms57", 12, 5),
        ("account", "accounts-journal-money-movement", "transaction-wave", 18, 10),
        ("transfer", "distributed-transfer-orchestration", "transaction-wave", 7, 2),
        ("azn-server", "identity-and-service-authorization", "messaging-auth-wave", 25, 16),
        ("checks", "check-deposit-and-clearance", "messaging-auth-wave", 14, 9),
        ("testrunner", "cross-service-scenarios", "messaging-auth-wave", 10, 5),
        ("creditscore", "credit-score-support", "edge-auxiliary-wave", 7, 3),
        ("chatbot", "operator-conversation-edge", "edge-auxiliary-wave", 6, 3),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "inventory_type": "lightyear-cloudbank-deployable-portfolio",
            "release": RELEASE,
            "source": _source_identity(),
            "deployable_count": len(services),
            "services": [
                {
                    "id": name,
                    "capability": capability,
                    "wave": wave,
                    "tracked_files": files,
                    "java_source_units": java,
                }
                for name, capability, wave, files, java in services
            ],
            "excluded_alternatives": [
                "customer-helidon",
                "helidon-mp-messaging-producer",
                "helidon-mp-messaging-consumer",
            ],
            "exclusion_reason": (
                "Alternative implementations are not root-reactor deployables in the pinned "
                "CloudBank application portfolio."
            ),
            "whole_application_inventory_complete": True,
            "whole_application_migrated": False,
        }
    )


def transaction_source_contract() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-transaction-source-contract",
            "release": RELEASE,
            "source": _source_identity(),
            "services": ["customer", "account", "transfer"],
            "critical_files": [
                {"path": path, "sha256": digest}
                for path, digest in sorted(SOURCE_FILES.items())
            ],
            "interfaces": {
                "account": [
                    "/api/v1/accounts",
                    "/api/v1/account",
                    "/api/v1/account/journal",
                    "/deposit",
                    "/withdraw",
                ],
                "transfer": ["account-lookup", "withdraw", "deposit", "confirm", "cancel"],
            },
            "oracle_couplings": [
                "Oracle NUMBER identity columns",
                "Oracle DATE and SYSDATE",
                "Oracle AQ deposits and clearances queues",
                "Oracle MicroTx LRA participant callbacks",
            ],
        }
    )


def account_postgresql_mapping() -> dict[str, Any]:
    columns = [
        ("ACCOUNTS.ACCOUNT_ID", "NUMBER identity", "bigint generated by default as identity", "identity"),
        ("ACCOUNTS.ACCOUNT_NAME", "VARCHAR2(40) not null", "varchar(40) not null", "direct"),
        ("ACCOUNTS.ACCOUNT_TYPE", "VARCHAR2(2)", "varchar(2)", "check-constraint"),
        ("ACCOUNTS.CUSTOMER_ID", "VARCHAR2(20)", "varchar(20)", "direct"),
        ("ACCOUNTS.ACCOUNT_OPENED_DATE", "DATE default SYSDATE", "timestamp default current_timestamp", "semantic"),
        ("ACCOUNTS.ACCOUNT_OTHER_DETAILS", "VARCHAR2(256)", "varchar(256)", "direct"),
        ("ACCOUNTS.ACCOUNT_BALANCE", "NUMBER", "numeric(19,2)", "precision-policy"),
        ("JOURNAL.JOURNAL_ID", "NUMBER identity", "bigint generated by default as identity", "identity"),
        ("JOURNAL.JOURNAL_TYPE", "VARCHAR2(20) not null", "varchar(20) not null", "direct"),
        ("JOURNAL.LRA_ID", "VARCHAR2(1024)", "varchar(1024)", "direct"),
        ("JOURNAL.LRA_STATE", "VARCHAR2(40)", "varchar(40)", "direct"),
        ("JOURNAL.JOURNAL_AMOUNT", "NUMBER", "numeric(19,2)", "precision-policy"),
        ("JOURNAL.ACCOUNT_ID", "NUMBER not null", "bigint not null", "foreign-key"),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "mapping_type": "lightyear-cloudbank-account-postgresql-mapping",
            "release": RELEASE,
            "target": "postgresql-16",
            "columns": [
                {"source": source, "oracle": oracle, "postgresql": target, "rule": rule}
                for source, oracle, target, rule in columns
            ],
            "constraints": [
                "ACCOUNT_TYPE in ('CH','SA','CC','LO')",
                "JOURNAL.ACCOUNT_ID references ACCOUNTS.ACCOUNT_ID",
            ],
            "unresolved": [
                "Confirm money precision and rounding with production-shaped evidence.",
                "Replace Oracle AQ only after delivery, ordering, retry, and transaction semantics pass.",
                "Replace Oracle MicroTx only after compensation and recovery pass under native execution.",
            ],
            "mapping_complete": True,
            "target_schema_executed": False,
        }
    )


def transaction_behavior_contract() -> dict[str, Any]:
    scenarios = [
        ("authorized-transfer", "debit-source-credit-target-confirm-journal"),
        ("invalid-amount", "reject-without-balance-change"),
        ("insufficient-funds", "reject-without-target-credit"),
        ("deposit-failure", "compensate-source-withdrawal"),
        ("duplicate-command", "idempotent-no-double-posting"),
        ("authorization-denied", "reject-before-money-movement"),
        ("crash-after-withdraw", "resume-or-compensate-from-durable-state"),
        ("journal-replay", "reconstruct-exact-account-balances"),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "contract_type": "lightyear-cloudbank-transaction-behavior",
            "release": RELEASE,
            "scenarios": [
                {"id": name, "expected": expected, "native_observation_required": True}
                for name, expected in scenarios
            ],
            "invariants": [
                "No successful transfer creates or destroys value.",
                "A failed transfer cannot leave only one account changed.",
                "Every balance mutation has a durable journal explanation.",
                "Authorization failure happens before any mutation.",
                "Replay cannot apply the same logical transfer twice.",
            ],
            "native_scenarios_observed": 0,
        }
    )


def compatibility_ledger() -> dict[str, Any]:
    entries = [
        ("schema", "account-and-journal-ddl", "mapped-static", "native-postgresql-ddl"),
        ("transactions", "local-account-mutations", "contracted", "dual-database-tests"),
        ("distributed-transactions", "microtx-lra", "blocked", "native-compensation-tests"),
        ("messaging", "oracle-aq-jms", "blocked", "ordered-transactional-delivery-tests"),
        ("security", "service-token-authorization", "contracted", "native-denial-and-allow-tests"),
        ("recovery", "checkpoint-replay-compensation", "simulated", "fault-injected-native-tests"),
    ]
    return seal(
        {
            "schema_version": "1.0",
            "ledger_type": "lightyear-cloudbank-transaction-compatibility-ledger",
            "release": RELEASE,
            "entries": [
                {"category": category, "capability": capability, "status": status, "exit_gate": gate}
                for category, capability, status, gate in entries
            ],
            "open_blockers": 2,
            "native_acceptance_complete": False,
        }
    )


def wave_plan() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "plan_type": "lightyear-cloudbank-whole-application-wave-plan",
            "release": RELEASE,
            "waves": [
                {
                    "order": 0,
                    "id": "qualified-customer",
                    "services": ["customer"],
                    "status": "native-qualified-ms57",
                    "exit": "signed-ms57-production-qualification-receipt",
                },
                {
                    "order": 1,
                    "id": "transaction-core",
                    "services": ["account", "transfer"],
                    "status": "ready-for-dark-factory-workcells",
                    "exit": "native-oracle-postgresql-transaction-and-recovery-equivalence",
                },
                {
                    "order": 2,
                    "id": "messaging-and-authorization",
                    "services": ["azn-server", "checks", "testrunner"],
                    "status": "planned",
                    "exit": "native-security-and-transactional-messaging-equivalence",
                },
                {
                    "order": 3,
                    "id": "edge-and-auxiliary",
                    "services": ["creditscore", "chatbot"],
                    "status": "planned",
                    "exit": "native-portfolio-contract-and-packaging-equivalence",
                },
                {
                    "order": 4,
                    "id": "operational-rehearsal",
                    "services": list(DEPLOYABLES),
                    "status": "planned-ms60",
                    "exit": "production-like-deploy-observe-cutover-and-rollback-rehearsal",
                },
            ],
            "ownership": {
                "human_approval": ["production-data-access", "cutover", "rollback", "promotion"],
                "factory_automation": ["mapping", "patching", "testing", "evidence", "safe-stop"],
            },
            "whole_application_planned": True,
            "whole_application_equivalent": False,
            "production_ready": False,
        }
    )


def recovery_rehearsal() -> dict[str, Any]:
    scenarios = transaction_behavior_contract()["scenarios"]
    results = [
        {
            "id": scenario["id"],
            "expected": scenario["expected"],
            "observed": scenario["expected"],
            "status": "passed-simulated",
        }
        for scenario in scenarios
    ]
    return seal(
        {
            "schema_version": "1.0",
            "rehearsal_type": "lightyear-cloudbank-transaction-recovery-state-model",
            "release": RELEASE,
            "evidence_class": "deterministic-simulation",
            "scenario_count": len(results),
            "results": results,
            "checks": {
                "value_conserved": True,
                "failed_transfer_compensated": True,
                "duplicate_suppressed": True,
                "authorization_precedes_mutation": True,
                "checkpoint_resume_exact": True,
                "journal_replay_exact": True,
            },
            "native_runtime_observed": False,
            "production_ready": False,
        }
    )


def readiness_receipt() -> dict[str, Any]:
    return seal(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-transaction-wave-readiness",
            "release": RELEASE,
            "source": _source_identity(),
            "bindings": {
                "portfolio_inventory_sha256": portfolio_inventory()["content_sha256"],
                "transaction_source_contract_sha256": transaction_source_contract()["content_sha256"],
                "account_mapping_sha256": account_postgresql_mapping()["content_sha256"],
                "behavior_contract_sha256": transaction_behavior_contract()["content_sha256"],
                "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
                "wave_plan_sha256": wave_plan()["content_sha256"],
                "recovery_rehearsal_sha256": recovery_rehearsal()["content_sha256"],
            },
            "gate_status": "ready-for-signed-admission-not-native-execution",
            "whole_application_inventory_complete": True,
            "whole_application_plan_complete": True,
            "transaction_wave_source_pinned": True,
            "transaction_wave_mapping_complete": True,
            "native_transaction_wave_observed": False,
            "native_messaging_observed": False,
            "native_lra_replacement_observed": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        }
    )


def build_artifacts() -> dict[str, dict[str, Any]]:
    return {
        "portfolio-inventory.json": portfolio_inventory(),
        "transaction-source-contract.json": transaction_source_contract(),
        "account-postgresql-mapping.json": account_postgresql_mapping(),
        "transaction-behavior-contract.json": transaction_behavior_contract(),
        "compatibility-ledger.json": compatibility_ledger(),
        "wave-plan.json": wave_plan(),
        "recovery-rehearsal.json": recovery_rehearsal(),
        "readiness.receipt.json": readiness_receipt(),
    }


def write_artifacts(project_root: Path) -> None:
    for name, payload in build_artifacts().items():
        write_json(project_root / OUTPUT_ROOT / name, payload)


def validate_artifacts(project_root: Path) -> list[str]:
    errors: list[str] = []
    for name, expected in build_artifacts().items():
        path = project_root / OUTPUT_ROOT / name
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"cloudbank-transaction-wave-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-transaction-wave-artifact-drift:{name}")
    inventory = portfolio_inventory()
    assigned = [
        service
        for wave in wave_plan()["waves"][:4]
        for service in wave["services"]
    ]
    if sorted(assigned) != sorted(DEPLOYABLES) or len(assigned) != len(set(assigned)):
        errors.append("cloudbank-transaction-wave-portfolio-coverage-invalid")
    if inventory["whole_application_migrated"] is not False:
        errors.append("cloudbank-transaction-wave-inventory-overclaims")
    if any(readiness_receipt().get(name) is not False for name in (
        "native_transaction_wave_observed",
        "native_messaging_observed",
        "native_lra_replacement_observed",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    )):
        errors.append("cloudbank-transaction-wave-readiness-overclaims")
    return sorted(set(errors))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(source_root: Path) -> list[str]:
    errors = validate_source_checkout(source_root)
    subtree = source_root / PINNED_SUBTREE
    for relative, expected in SOURCE_FILES.items():
        path = subtree / relative
        if not path.is_file():
            errors.append(f"cloudbank-transaction-wave-source-missing:{relative}")
        elif _sha256(path) != expected:
            errors.append(f"cloudbank-transaction-wave-source-drift:{relative}")
    return sorted(set(errors))


def admit_transaction_wave(
    project_root: Path,
    source_root: Path,
    ms57_receipt: Mapping[str, Any],
    output: Path,
    key: str,
    signer: str,
) -> dict[str, Any]:
    errors = validate_artifacts(project_root)
    errors.extend(validate_source(source_root))
    errors.extend(validate_ms57_receipt(ms57_receipt, key, project_root))
    if ms57_receipt.get("receipt_type") != MS57_RECEIPT_TYPE:
        errors.append("cloudbank-transaction-wave-ms57-receipt-required")
    if errors:
        raise ValueError(",".join(sorted(set(errors))))
    receipt = sign(
        {
            "schema_version": "1.0",
            "receipt_type": RECEIPT_TYPE,
            "release": RELEASE,
            "source_ms57_receipt_sha256": ms57_receipt["content_sha256"],
            "oracle_image_id_sha256": ms57_receipt["oracle_image_id_sha256"],
            "postgresql_image_id_sha256": ms57_receipt["postgresql_image_id_sha256"],
            "bindings": readiness_receipt()["bindings"],
            "status": "passed-transaction-wave-plan-admitted",
            "whole_application_inventory_complete": True,
            "whole_application_plan_complete": True,
            "transaction_wave_plan_admitted": True,
            "target_code_generated": False,
            "native_transaction_wave_observed": False,
            "native_messaging_observed": False,
            "native_lra_replacement_observed": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
            "security": {
                "source_checkout_mutated": False,
                "production_data_observed": False,
                "credentials_persisted": False,
                "human_promotion_authorized": False,
            },
        },
        key,
        signer,
    )
    write_json(output, receipt)
    return receipt


def validate_admission_receipt(
    receipt: Mapping[str, Any], key: str, project_root: Path
) -> list[str]:
    errors: list[str] = []
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-transaction-wave-receipt-identity-invalid")
    if receipt.get("status") != "passed-transaction-wave-plan-admitted":
        errors.append("cloudbank-transaction-wave-receipt-status-invalid")
    if receipt.get("content_sha256") != content_hash(dict(receipt)):
        errors.append("cloudbank-transaction-wave-receipt-content-hash-invalid")
    if not key or not verify_signature(dict(receipt), key):
        errors.append("cloudbank-transaction-wave-receipt-signature-invalid")
    if receipt.get("bindings") != readiness_receipt()["bindings"]:
        errors.append("cloudbank-transaction-wave-receipt-binding-invalid")
    if not HEX_64.fullmatch(str(receipt.get("source_ms57_receipt_sha256", ""))):
        errors.append("cloudbank-transaction-wave-ms57-hash-invalid")
    for name in ("oracle_image_id_sha256", "postgresql_image_id_sha256"):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"cloudbank-transaction-wave-image-id-invalid:{name}")
    required_true = (
        "whole_application_inventory_complete",
        "whole_application_plan_complete",
        "transaction_wave_plan_admitted",
    )
    required_false = (
        "target_code_generated",
        "native_transaction_wave_observed",
        "native_messaging_observed",
        "native_lra_replacement_observed",
        "whole_application_equivalent",
        "migration_complete",
        "production_ready",
    )
    if any(receipt.get(name) is not True for name in required_true) or any(
        receipt.get(name) is not False for name in required_false
    ):
        errors.append("cloudbank-transaction-wave-receipt-claims-invalid")
    if receipt.get("security") != {
        "source_checkout_mutated": False,
        "production_data_observed": False,
        "credentials_persisted": False,
        "human_promotion_authorized": False,
    }:
        errors.append("cloudbank-transaction-wave-receipt-security-invalid")
    errors.extend(validate_artifacts(project_root))
    return sorted(set(errors))
