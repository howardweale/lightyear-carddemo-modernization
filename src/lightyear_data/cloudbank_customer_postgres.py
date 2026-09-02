from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

from .cloudbank_baseline import (
    ORACLE_RECEIPT_TYPE,
    PINNED_COMMIT,
    PINNED_ROOT_TREE,
    PINNED_SUBTREE,
    PINNED_SUBTREE_TREE,
    validate_execution_receipt as validate_baseline_receipt,
    validate_source_checkout,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.55.0"
OUTPUT_ROOT = Path("reference-estates/cloudbank/customer-postgresql")
RECEIPT_TYPE = "lightyear-cloudbank-customer-postgresql-execution-receipt"
POSTGRES_IMAGE = "postgres:16-alpine"
HEX_64 = re.compile(r"[0-9a-f]{64}")

SOURCE_FILES = {
    "table-ddl": (
        "customer/src/main/resources/db/changelog/table.sql",
        "c7732c5fe70581c94d1d52a646b4b7e772de6404505c08ede08fe9ae9d82d2af",
    ),
    "bootstrap-data": (
        "customer/src/main/resources/db/changelog/data.sql",
        "174524ede252be4a382e916859da12af37127672b92087b2b07302dd2fcbfb1d",
    ),
    "jpa-entity": (
        "customer/src/main/java/com/example/customer/model/Customers.java",
        "1e44410b114c5f9ec333b323a8c1b157b1960c81e4a9d8dc8093f556f15914a8",
    ),
    "repository": (
        "customer/src/main/java/com/example/customer/repository/CustomersRepository.java",
        "04e73f3100980f993f743f01e7eb5674907060ee99f157a27ef7d5318f1d6930",
    ),
    "controller": (
        "customer/src/main/java/com/example/customer/controller/CustomerController.java",
        "23ce8b89b93927f8c3262eea808210dda36a81845ccc4558f04156d8234f6ab3",
    ),
    "runtime-configuration": (
        "customer/src/main/resources/application.yaml",
        "3caa27fae2fcb936947cebb5e660835e09c294395dceb123499b408cfa303dd9",
    ),
    "maven-module": (
        "customer/pom.xml",
        "8715304d7f327604565c49d7b4e0616150469fe082633ca6487f14b8bf72ca8b",
    ),
}

COLUMNS = (
    ("CUSTOMER_ID", "VARCHAR2(20)", "customer_id", 'VARCHAR(20) COLLATE "C"', False),
    ("CUSTOMER_NAME", "VARCHAR2(40)", "customer_name", 'VARCHAR(40) COLLATE "C"', True),
    ("CUSTOMER_EMAIL", "VARCHAR2(40)", "customer_email", 'VARCHAR(40) COLLATE "C"', True),
    ("DATE_BECAME_CUSTOMER", "DATE DEFAULT SYSDATE", "date_became_customer", "TIMESTAMP(0) WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0)", False),
    ("CUSTOMER_OTHER_DETAILS", "VARCHAR2(4000)", "customer_other_details", 'VARCHAR(4000) COLLATE "C"', True),
    ("PASSWORD", "VARCHAR2(40)", "password", 'VARCHAR(40) COLLATE "C"', True),
    ("ROLE", "VARCHAR2(40)", "role", 'VARCHAR(40) COLLATE "C"', True),
)


def _source() -> dict[str, Any]:
    return {
        "repository": "https://github.com/oracle/microservices-backend",
        "commit": PINNED_COMMIT,
        "root_tree": PINNED_ROOT_TREE,
        "subtree": PINNED_SUBTREE,
        "subtree_tree": PINNED_SUBTREE_TREE,
        "module": "customer",
    }


def source_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-customer-oracle-source",
        "release": RELEASE,
        "source": _source(),
        "source_files": [
            {"role": role, "path": path, "sha256": digest}
            for role, (path, digest) in SOURCE_FILES.items()
        ],
        "table": {
            "qualified_name": "CUSTOMER.CUSTOMERS",
            "columns": 7,
            "primary_key": {"name": "CUSTOMERS_PK", "columns": ["CUSTOMER_ID"]},
            "bootstrap_rows": 3,
            "liquibase_changesets": ["customer:1", "customer:2"],
        },
        "application_behavior": {
            "jpa_entity": "com.example.customer.model.Customers",
            "repository_methods": [
                "findAll", "findById", "existsById", "saveAndFlush", "save", "deleteById",
                "findByCustomerNameIsContaining", "findByCustomerEmailIsContaining",
            ],
            "api_operations": ["list", "find-by-id", "find-by-name-fragment", "find-by-email-fragment", "create", "update", "delete"],
            "json_ignored_columns": ["PASSWORD"],
            "schema_only_columns": ["ROLE"],
        },
        "data_boundary": {
            "upstream_password_values_persisted": False,
            "synthetic_rows_only": True,
            "production_data_observed": False,
        },
    })


def target_mapping() -> dict[str, Any]:
    columns = []
    for source, source_type, target, target_type, nullable in COLUMNS:
        transform = "identity-with-unquoted-identifier-normalization"
        if source.startswith("CUSTOMER_") or source in {"PASSWORD", "ROLE"}:
            transform = "oracle-empty-string-to-null-then-identity"
        if source == "DATE_BECAME_CUSTOMER":
            transform = "oracle-date-second-precision-to-timestamp-without-time-zone"
        columns.append({
            "source": source,
            "source_type": source_type,
            "target": target,
            "target_type": target_type,
            "nullable": nullable,
            "transformation": transform,
        })
    return seal({
        "schema_version": "1.0",
        "mapping_type": "lightyear-cloudbank-oracle-postgresql-mapping",
        "release": RELEASE,
        "source_contract_sha256": source_contract()["content_sha256"],
        "source_dialect": "oracle-cloudbank-v5",
        "source_table": "CUSTOMER.CUSTOMERS",
        "target_dialect": "postgresql-16",
        "target_image": POSTGRES_IMAGE,
        "target_table": "cloudbank_customer.customers",
        "columns": columns,
        "constraints": [{
            "source": "CUSTOMERS_PK",
            "target": "customers_pk",
            "kind": "primary-key",
            "columns": ["customer_id"],
            "classification": "exact",
        }],
        "decisions": {
            "identifier_case": "unquoted Oracle uppercase maps to unquoted PostgreSQL lowercase",
            "empty_string": "all character inputs use NULLIF(value, '') before persistence",
            "date": "Oracle DATE maps to second-precision timestamp without time zone; controlled runs set UTC",
            "collation": "C collation qualifies bounded case-sensitive ASCII fragment searches",
            "schema_only_role": "preserve nullable ROLE column; MS #56 must reconcile the missing JPA field",
            "credentials": "preserve column shape but never copy upstream sample password values into evidence",
        },
        "mapping_generated": True,
        "native_postgresql_observed": False,
        "application_refactored": False,
        "target_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    })


def compatibility_ledger() -> dict[str, Any]:
    entries = [
        ("column:customer-id", "column", "normalized-equivalent", "PostgreSQL VARCHAR counts characters while the Oracle DDL does not pin BYTE or CHAR length semantics.", "bounded-workcell-approved", ["ascii-boundary-fixtures", "production-nls-length-profile"]),
        ("column:customer-name", "column", "normalized-equivalent", "C collation preserves bounded case-sensitive ASCII fragment behavior.", "bounded-workcell-approved", ["fragment-query-probe", "production-collation-profile"]),
        ("column:customer-email", "column", "normalized-equivalent", "C collation preserves bounded case-sensitive ASCII fragment behavior.", "bounded-workcell-approved", ["fragment-query-probe", "production-collation-profile"]),
        ("column:date-became-customer", "column", "policy-decision-required", "Oracle DATE stores seconds and SYSDATE uses database wall-clock semantics; PostgreSQL CURRENT_TIMESTAMP is transaction-scoped.", "use-utc-second-precision-and-block-production-equivalence", ["default-value-probe", "long-transaction-time-policy"]),
        ("column:customer-other-details", "column", "normalized-equivalent", "Oracle empty strings collapse to NULL and PostgreSQL values are normalized with NULLIF.", "bounded-workcell-approved", ["empty-string-null-probe"]),
        ("column:password", "security", "policy-decision-required", "The upstream bootstrap contains demonstration plaintext credentials that must not enter committed fixtures or receipts.", "synthetic-noncredential-values-only", ["sensitive-value-negative-gate"]),
        ("column:role", "orm-schema", "policy-decision-required", "ROLE exists in the table and bootstrap rows but is absent from the JPA entity.", "preserve-column-and-block-application-equivalence-until-ms56", ["generated-entity-change", "dual-run-api-proof"]),
        ("behavior:primary-key", "constraint", "exact", "A single-column non-null primary key is directly representable.", "accepted", ["native-catalog-probe"]),
        ("behavior:contains-search", "repository-query", "normalized-equivalent", "Spring Data containing queries map to LIKE; C collation and ASCII fixtures bound the proof.", "bounded-workcell-approved", ["name-fragment-probe", "email-fragment-probe"]),
        ("behavior:crud-transaction", "transaction", "normalized-equivalent", "Insert, update, delete, commit, and rollback mechanics are directly testable; concurrency is excluded.", "bounded-workcell-approved", ["native-commit-rollback-probe"]),
        ("behavior:oracle-ucp-wallet", "application-runtime", "unsupported", "Oracle JDBC, UCP, and wallet configuration are application refactoring concerns, not database-DDL mapping.", "excluded-until-ms56", ["generated-postgresql-runtime-configuration"]),
        ("behavior:api-authorization", "application-runtime", "unsupported", "HTTP authorization and ownership checks are not proven by a database-only target execution.", "excluded-until-ms56", ["dual-run-api-and-security-proof"]),
    ]
    rendered = [
        {
            "item_id": item_id,
            "scope": scope,
            "source_semantics": "pinned CloudBank customer Oracle behavior",
            "target_semantics": "bounded PostgreSQL 16 mapping",
            "classification": classification,
            "rationale": rationale,
            "evidence_required": evidence,
            "decision": decision,
        }
        for item_id, scope, classification, rationale, decision, evidence in entries
    ]
    counts = Counter(item["classification"] for item in rendered)
    return seal({
        "schema_version": "1.0",
        "ledger_type": "lightyear-cloudbank-customer-compatibility-ledger",
        "release": RELEASE,
        "mapping_sha256": target_mapping()["content_sha256"],
        "entries": rendered,
        "statistics": dict(sorted(counts.items())),
        "unresolved_decisions": [],
        "bounded_database_mapping_blocked": False,
        "application_equivalence_blocked": True,
        "production_equivalence_blocked": True,
    })


def behavior_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-customer-postgresql-behavior",
        "release": RELEASE,
        "mapping_sha256": target_mapping()["content_sha256"],
        "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
        "synthetic_fixture_rows": 4,
        "required_native_checks": {
            "CB_ROWS": "4",
            "CB_COLUMNS": "7",
            "CB_PK": "1",
            "CB_DEFAULTED_DATES": "4",
            "CB_EMPTY_TO_NULL": "1",
            "CB_NAME_CONTAINS": "2",
            "CB_EMAIL_CONTAINS": "2",
            "CB_MUTATED_ROWS": "4",
            "CB_ROLLBACK_ROWS": "4",
            "CB_ROLLBACK_EMAIL": "alice@example.test",
            "CB_COMMIT_ROWS": "1",
            "CB_FINAL_ROWS": "4",
        },
        "claim_scope": ["schema", "column-types", "primary-key", "synthetic-data", "fragment-queries", "crud-commit-rollback"],
        "excluded": ["Spring application refactoring", "HTTP/API equivalence", "authorization equivalence", "concurrency", "CDC", "cutover", "production data"],
    })


def readiness_receipt() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-cloudbank-customer-postgresql-readiness",
        "release": RELEASE,
        "source_contract_sha256": source_contract()["content_sha256"],
        "mapping_sha256": target_mapping()["content_sha256"],
        "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
        "behavior_contract_sha256": behavior_contract()["content_sha256"],
        "gate_status": "mapping-generated-native-execution-pending",
        "source_oracle_receipt_required": True,
        "source_oracle_receipt_committed": False,
        "target_selected": True,
        "target_dialect": "postgresql-16",
        "postgresql_mapping_complete": True,
        "native_postgresql_observed": False,
        "bounded_database_mapping_qualified": False,
        "application_refactored": False,
        "target_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    })


def schema_sql() -> str:
    return """-- Generated by LIGHTYEAR MS #55; bounded CloudBank customer mapping.
CREATE SCHEMA IF NOT EXISTS cloudbank_customer;
DROP TABLE IF EXISTS cloudbank_customer.customers;
CREATE TABLE cloudbank_customer.customers (
  customer_id VARCHAR(20) COLLATE \"C\" NOT NULL,
  customer_name VARCHAR(40) COLLATE \"C\",
  customer_email VARCHAR(40) COLLATE \"C\",
  date_became_customer TIMESTAMP(0) WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
  customer_other_details VARCHAR(4000) COLLATE \"C\",
  password VARCHAR(40) COLLATE \"C\",
  role VARCHAR(40) COLLATE \"C\",
  CONSTRAINT customers_pk PRIMARY KEY (customer_id)
);
COMMENT ON TABLE cloudbank_customer.customers IS 'CLOUDBANK CUSTOMERS TABLE';
"""


def fixture_sql() -> str:
    return """SET TIME ZONE 'UTC';
INSERT INTO cloudbank_customer.customers
  (customer_id, customer_name, customer_email, date_became_customer, customer_other_details, password, role)
VALUES
  ('cust-001', 'Alice', 'alice@example.test', TIMESTAMP '2026-09-01 10:15:30', 'Synthetic alpha', 'synthetic-hash-a', 'USER_ROLE'),
  ('cust-002', 'Alicia', 'ops@example.test', TIMESTAMP '2026-09-01 10:16:30', 'Synthetic beta', 'synthetic-hash-b', 'USER_ROLE'),
  ('cust-003', 'Bob', NULL, TIMESTAMP '2026-09-01 10:17:30', NULL, NULL, NULL);
INSERT INTO cloudbank_customer.customers
  (customer_id, customer_name, customer_email, customer_other_details, password, role)
VALUES
  ('cust-004', 'Zed', 'zed@elsewhere.test', NULLIF('', ''), 'synthetic-hash-d', 'USER_ROLE');
"""


def build_artifacts() -> dict[str, Any]:
    return {
        "source-contract.json": source_contract(),
        "mapping.json": target_mapping(),
        "compatibility-ledger.json": compatibility_ledger(),
        "behavior-contract.json": behavior_contract(),
        "readiness.receipt.json": readiness_receipt(),
        "postgresql.sql": schema_sql(),
        "fixtures.sql": fixture_sql(),
    }


def validate_source_files(source_root: Path) -> list[str]:
    errors = validate_source_checkout(source_root)
    subtree = source_root / PINNED_SUBTREE
    for role, (relative, expected) in SOURCE_FILES.items():
        path = subtree / relative
        if not path.is_file():
            errors.append(f"cloudbank-customer-source-file-missing:{role}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f"cloudbank-customer-source-file-drift:{role}")
    return sorted(set(errors))


def validate_artifacts(project_root: Path) -> list[str]:
    root = project_root / OUTPUT_ROOT
    errors: list[str] = []
    for name, expected in build_artifacts().items():
        path = root / name
        if not path.is_file():
            errors.append(f"cloudbank-customer-artifact-missing:{name}")
            continue
        if isinstance(expected, str):
            if path.read_text(encoding="utf-8") != expected:
                errors.append(f"cloudbank-customer-artifact-drift:{name}")
        else:
            try:
                actual = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                errors.append(f"cloudbank-customer-artifact-invalid:{name}")
                continue
            if actual != expected:
                errors.append(f"cloudbank-customer-artifact-drift:{name}")
    forbidden = ("SuperSecret", "Welcome", "Important Info", "andy@andy.com", "sanjay@sanjay.com", "mark@mark.com")
    for path in root.glob("*"):
        if path.is_file() and path.suffix in {".json", ".sql", ".md"}:
            text = path.read_text(encoding="utf-8")
            if any(value in text for value in forbidden):
                errors.append(f"cloudbank-customer-sensitive-bootstrap-value-persisted:{path.name}")
    ledger = compatibility_ledger()
    if ledger["unresolved_decisions"] or ledger["bounded_database_mapping_blocked"]:
        errors.append("cloudbank-customer-bounded-mapping-blocked")
    if not ledger["application_equivalence_blocked"] or not ledger["production_equivalence_blocked"]:
        errors.append("cloudbank-customer-ledger-overclaims-equivalence")
    return sorted(set(errors))


def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, text=True, capture_output=True, **kwargs)


def execute_postgresql(
    source_root: Path,
    oracle_receipt: Mapping[str, Any],
    postgres_image_id: str,
    key: str,
    signer: str,
    run: Callable[..., subprocess.CompletedProcess[str]] = _run,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    errors = validate_source_files(source_root) + validate_baseline_receipt(oracle_receipt, key)
    if errors:
        raise ValueError(",".join(errors))
    if oracle_receipt.get("receipt_type") != ORACLE_RECEIPT_TYPE:
        raise ValueError("cloudbank-customer-postgresql-requires-oracle-runtime-receipt")
    if not HEX_64.fullmatch(postgres_image_id):
        raise ValueError("cloudbank-customer-postgresql-image-id-must-be-sha256")
    inspected = run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", POSTGRES_IMAGE],
        timeout=30,
    )
    actual_image_id = inspected.stdout.strip().removeprefix("sha256:")
    if inspected.returncode or actual_image_id != postgres_image_id:
        raise ValueError("cloudbank-customer-postgresql-image-id-mismatch")
    name = "lightyear-cloudbank-customer-" + uuid.uuid4().hex[:12]
    start = [
        "docker", "run", "-d", "--rm", "--name", name, "--network", "none", "--read-only",
        "--user", "70:70", "--pids-limit", "128", "--memory", "512m", "--cpus", "1.0",
        "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=256m,uid=70,gid=70",
        "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16m,uid=70,gid=70",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,uid=70,gid=70", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
        "-e", "POSTGRES_DB=cloudbank", f"sha256:{postgres_image_id}",
    ]
    started = run(start, timeout=120)
    if started.returncode:
        raise ValueError("cloudbank-customer-postgresql-container-start-failed")
    try:
        for _ in range(120):
            ready = run(["docker", "exec", name, "psql", "-U", "postgres", "-d", "cloudbank", "-Atqc", "SELECT 1"], timeout=10)
            if ready.returncode == 0 and ready.stdout.strip() == "1":
                break
            pause(0.5)
        else:
            raise ValueError("cloudbank-customer-postgresql-not-ready")
        probes = """
SELECT 'CB_ROWS=' || count(*) FROM cloudbank_customer.customers;
SELECT 'CB_COLUMNS=' || count(*) FROM information_schema.columns WHERE table_schema='cloudbank_customer' AND table_name='customers';
SELECT 'CB_PK=' || count(*) FROM information_schema.table_constraints WHERE table_schema='cloudbank_customer' AND table_name='customers' AND constraint_type='PRIMARY KEY';
SELECT 'CB_DEFAULTED_DATES=' || count(*) FROM cloudbank_customer.customers WHERE date_became_customer IS NOT NULL;
SELECT 'CB_EMPTY_TO_NULL=' || count(*) FROM cloudbank_customer.customers WHERE customer_id='cust-004' AND customer_other_details IS NULL;
SELECT 'CB_NAME_CONTAINS=' || count(*) FROM cloudbank_customer.customers WHERE customer_name LIKE '%Ali%';
SELECT 'CB_EMAIL_CONTAINS=' || count(*) FROM cloudbank_customer.customers WHERE customer_email LIKE '%example.test%';
BEGIN;
UPDATE cloudbank_customer.customers SET customer_email='changed@example.test' WHERE customer_id='cust-001';
DELETE FROM cloudbank_customer.customers WHERE customer_id='cust-003';
INSERT INTO cloudbank_customer.customers (customer_id, customer_name) VALUES ('cust-txn', 'Transient');
SELECT 'CB_MUTATED_ROWS=' || count(*) FROM cloudbank_customer.customers;
ROLLBACK;
SELECT 'CB_ROLLBACK_ROWS=' || count(*) FROM cloudbank_customer.customers;
SELECT 'CB_ROLLBACK_EMAIL=' || customer_email FROM cloudbank_customer.customers WHERE customer_id='cust-001';
BEGIN;
INSERT INTO cloudbank_customer.customers (customer_id, customer_name) VALUES ('cust-commit', 'Committed');
COMMIT;
SELECT 'CB_COMMIT_ROWS=' || count(*) FROM cloudbank_customer.customers WHERE customer_id='cust-commit';
DELETE FROM cloudbank_customer.customers WHERE customer_id='cust-commit';
SELECT 'CB_FINAL_ROWS=' || count(*) FROM cloudbank_customer.customers;
"""
        result = run(
            ["docker", "exec", "-i", name, "psql", "-U", "postgres", "-d", "cloudbank", "-v", "ON_ERROR_STOP=1", "-At"],
            input=schema_sql() + fixture_sql() + probes,
            timeout=180,
        )
        markers = dict(
            line.split("=", 1) for line in result.stdout.splitlines()
            if line.startswith("CB_") and "=" in line
        )
        expected = behavior_contract()["required_native_checks"]
        if result.returncode or markers != expected:
            raise ValueError("cloudbank-customer-postgresql-native-checks-failed")
        return sign({
            "schema_version": "1.0",
            "receipt_type": RECEIPT_TYPE,
            "release": RELEASE,
            "source": _source(),
            "source_oracle_receipt_sha256": oracle_receipt["content_sha256"],
            "source_oracle_image_id_sha256": oracle_receipt["oracle_image_id_sha256"],
            "mapping_sha256": target_mapping()["content_sha256"],
            "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            "behavior_contract_sha256": behavior_contract()["content_sha256"],
            "postgresql_image": POSTGRES_IMAGE,
            "postgresql_image_id_sha256": postgres_image_id,
            "checks": markers,
            "psql_exit_code": result.returncode,
            "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
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
        }, key, signer)
    finally:
        run(["docker", "rm", "-f", name], timeout=30)


def validate_postgresql_receipt(payload: Mapping[str, Any], key: str) -> list[str]:
    receipt = dict(payload)
    errors: list[str] = []
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-customer-postgresql-receipt-identity-invalid")
    if receipt.get("content_sha256") != content_hash(receipt):
        errors.append("cloudbank-customer-postgresql-receipt-content-hash-invalid")
    if not verify_signature(receipt, key):
        errors.append("cloudbank-customer-postgresql-receipt-signature-invalid")
    if receipt.get("source") != _source():
        errors.append("cloudbank-customer-postgresql-receipt-source-invalid")
    if receipt.get("mapping_sha256") != target_mapping()["content_sha256"]:
        errors.append("cloudbank-customer-postgresql-receipt-mapping-invalid")
    if receipt.get("compatibility_ledger_sha256") != compatibility_ledger()["content_sha256"]:
        errors.append("cloudbank-customer-postgresql-receipt-ledger-invalid")
    if receipt.get("behavior_contract_sha256") != behavior_contract()["content_sha256"]:
        errors.append("cloudbank-customer-postgresql-receipt-behavior-invalid")
    if receipt.get("postgresql_image") != POSTGRES_IMAGE or not HEX_64.fullmatch(str(receipt.get("postgresql_image_id_sha256", ""))):
        errors.append("cloudbank-customer-postgresql-receipt-image-invalid")
    if receipt.get("checks") != behavior_contract()["required_native_checks"] or receipt.get("psql_exit_code") != 0:
        errors.append("cloudbank-customer-postgresql-receipt-checks-invalid")
    required_true = ("postgresql_mapping_complete", "native_postgresql_observed", "bounded_database_mapping_qualified")
    if any(receipt.get(key_name) is not True for key_name in required_true):
        errors.append("cloudbank-customer-postgresql-receipt-qualification-incomplete")
    required_false = ("application_refactored", "application_equivalent", "target_equivalent", "migration_complete", "production_ready")
    if any(receipt.get(key_name) is not False for key_name in required_false):
        errors.append("cloudbank-customer-postgresql-receipt-overclaims")
    security = receipt.get("security", {})
    if security != {"raw_stdout_persisted": False, "raw_stderr_persisted": False, "credentials_persisted": False, "production_data_persisted": False}:
        errors.append("cloudbank-customer-postgresql-receipt-security-invalid")
    forbidden = ("password", "secret", "token", "credential")
    allowed = {"credentials_persisted"}
    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for name, child in value.items():
                current = f"{path}.{name}" if path else str(name)
                if any(term in str(name).lower() for term in forbidden) and str(name) not in allowed:
                    errors.append("cloudbank-customer-postgresql-receipt-forbidden-sensitive-field")
                walk(child, current)
        elif isinstance(value, list):
            for child in value:
                walk(child, path)
    walk(receipt)
    return sorted(set(errors))
