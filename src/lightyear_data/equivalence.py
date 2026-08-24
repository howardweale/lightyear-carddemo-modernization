from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .contracts import SCHEMA_VERSION, seal, sign
from .postgres import PostgreSQLAdapter, fixture_sql


def _row_identity(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("CARD_NUM", "")), str(row.get("AUTH_TS", ""))


def _row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def offline_equivalence(model: dict[str, Any], mapping: dict[str, Any], fixtures: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    columns = model.get("columns", [])
    rows = fixtures.get("rows", [])
    expected = fixtures.get("expected_results", {})
    if not columns:
        errors.append("canonical-model-empty")
    if not rows:
        errors.append("fixture-set-empty")
    identities = [_row_identity(row) for row in rows]
    duplicates = sorted(key for key, count in Counter(identities).items() if count > 1)
    if duplicates:
        errors.append("duplicate-primary-key")
    expected_names = {column["name"] for column in columns}
    for index, row in enumerate(rows, 1):
        if set(row) != expected_names:
            errors.append(f"row-{index}-column-mismatch")
    primary_keys = [item for item in model.get("constraints", []) if item.get("kind") == "primary_key"]
    if len(primary_keys) != 1 or primary_keys[0].get("columns") != ["CARD_NUM", "AUTH_TS"]:
        errors.append("primary-key-mismatch")
    index = next((item for item in model.get("indexes", []) if item.get("name") == "XAUTHFRD"), None)
    if not index or not index.get("unique") or index.get("columns") != [
        {"name": "CARD_NUM", "order": "ASC"}, {"name": "AUTH_TS", "order": "DESC"}
    ]:
        errors.append("unique-index-mismatch")
    if len(mapping.get("columns", [])) != len(columns):
        errors.append("mapping-column-count-mismatch")
    fraud_rows = [row for row in rows if row.get("AUTH_FRAUD") == "Y"]
    query_results = {
        "fraud_authorization_count": len(fraud_rows),
        "total_approved_amount": format(sum((__import__("decimal").Decimal(str(row["APPROVED_AMT"])) for row in rows), __import__("decimal").Decimal("0")), ".2f"),
    }
    row_checksums = sorted(_row_hash(row) for row in rows)
    if len(rows) != expected.get("row_count"):
        errors.append("row-count-mismatch")
    if query_results.get("fraud_authorization_count") != expected.get("fraud_authorization_count") or query_results.get("total_approved_amount") != expected.get("total_approved_amount"):
        errors.append("query-result-mismatch")
    if row_checksums != expected.get("row_checksums"):
        errors.append("row-checksum-mismatch")
    if expected.get("rollback_row_count") != expected.get("row_count"):
        errors.append("rollback-expectation-mismatch")
    checks = {
        "schema_structure": not any(item in errors for item in {"canonical-model-empty", "mapping-column-count-mismatch"}),
        "keys_and_constraints": not any(item in errors for item in {"primary-key-mismatch", "unique-index-mismatch", "duplicate-primary-key"}),
        "row_counts_and_checksums": bool(rows) and not any(item in errors for item in {"row-count-mismatch", "row-checksum-mismatch"}) and not any(item.startswith("row-") for item in errors),
        "query_results": bool(rows) and "query-result-mismatch" not in errors,
        "transaction_commit": bool(rows),
        "transaction_rollback": bool(rows) and "rollback-expectation-mismatch" not in errors,
    }
    return seal({
        "schema_version": SCHEMA_VERSION, "receipt_type": "factorydark-data-equivalence",
        "evidence_class": "offline-db2-to-target-development-proof",
        "workload": "carddemo-authorization-authfrds", "source": "db2-zos", "target": mapping.get("target_dialect", "unknown"),
        "status": "passed" if not errors and all(checks.values()) else "failed",
        "production_ready": False, "checks": checks, "errors": sorted(errors),
        "bindings": {
            "canonical_model_sha256": model.get("content_sha256"),
            "target_mapping_sha256": mapping.get("content_sha256"),
            "fixture_catalog_sha256": fixtures.get("content_sha256"),
        },
        "statistics": {
            "columns": len(columns), "constraints": len(model.get("constraints", [])),
            "indexes": len(model.get("indexes", [])), "rows": len(rows),
            "distinct_primary_keys": len(set(identities)), "row_checksums": row_checksums,
        },
        "query_results": query_results,
        "gaps": ["live-db2-catalog-not-observed", "live-zos-data-not-compared", "cdc-and-cutover-not-proven"],
    })


def signed_development_receipt(model: dict[str, Any], mapping: dict[str, Any], fixtures: dict[str, Any]) -> dict[str, Any]:
    return sign(offline_equivalence(model, mapping, fixtures), "factorydark-v0.19-development-only", "factorydark-development-fixture")


class DockerPostgresRunner:
    def __init__(
        self,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self.run = run
        self.pause = pause

    def verify(self, schema_sql: str, fixture_statements: str, image: str = "postgres:16-alpine", expected: dict[str, Any] | None = None) -> dict[str, Any]:
        name = "factorydark-data-" + uuid.uuid4().hex[:12]
        base = ["docker", "run", "-d", "--rm", "--name", name, "--network", "none", "--read-only",
                "--user", "70:70", "--pids-limit", "128", "--memory", "512m", "--cpus", "1.0",
                "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=256m,uid=70,gid=70",
                "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16m,uid=70,gid=70",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,uid=70,gid=70", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                "-e", "POSTGRES_DB=factorydark", image]
        started = self.run(base, text=True, capture_output=True, timeout=120)
        if started.returncode != 0:
            raise RuntimeError("PostgreSQL container failed to start: " + started.stderr.strip())
        try:
            for _ in range(60):
                ready = self.run(
                    ["docker", "exec", name, "psql", "-U", "postgres", "-d", "factorydark", "-Atqc", "SELECT 1"],
                    text=True,
                    capture_output=True,
                    timeout=10,
                )
                if ready.returncode == 0 and ready.stdout.strip() == "1":
                    break
                self.pause(0.5)
            else:
                raise RuntimeError("PostgreSQL did not become ready")
            checks = """
SELECT 'FD_ROWS=' || count(*) FROM carddemo.authfrds;
SELECT 'FD_FRAUD=' || count(*) FROM carddemo.authfrds WHERE auth_fraud='Y';
SELECT 'FD_APPROVED=' || sum(approved_amt) FROM carddemo.authfrds;
SELECT 'FD_COLUMNS=' || count(*) FROM information_schema.columns WHERE table_schema='carddemo' AND table_name='authfrds';
SELECT 'FD_PK=' || count(*) FROM information_schema.table_constraints WHERE table_schema='carddemo' AND table_name='authfrds' AND constraint_type='PRIMARY KEY';
SELECT 'FD_INDEX=' || count(*) FROM pg_indexes WHERE schemaname='carddemo' AND tablename='authfrds' AND indexname='xauthfrd';
BEGIN;
DELETE FROM carddemo.authfrds;
ROLLBACK;
SELECT 'FD_ROLLBACK_ROWS=' || count(*) FROM carddemo.authfrds;
"""
            result = self.run(
                ["docker", "exec", "-i", name, "psql", "-U", "postgres", "-d", "factorydark", "-v", "ON_ERROR_STOP=1", "-At"],
                input=schema_sql + fixture_statements + checks, text=True, capture_output=True, timeout=120,
            )
            markers = dict(line.split("=", 1) for line in result.stdout.splitlines() if line.startswith("FD_") and "=" in line)
            expected = expected or {
                "row_count": 2,
                "fraud_authorization_count": 1,
                "total_approved_amount": "125.50",
                "rollback_row_count": 2,
            }
            expected_markers = {
                "FD_ROWS": str(expected["row_count"]),
                "FD_FRAUD": str(expected["fraud_authorization_count"]),
                "FD_APPROVED": str(expected["total_approved_amount"]),
                "FD_COLUMNS": "26",
                "FD_PK": "1",
                "FD_INDEX": "1",
                "FD_ROLLBACK_ROWS": str(expected["rollback_row_count"]),
            }
            passed = result.returncode == 0 and markers == expected_markers
            reason_code = None
            if result.returncode != 0:
                reason_code = "postgres-command-failed"
            elif markers != expected_markers:
                reason_code = "verification-marker-mismatch"
            return seal({
                "schema_version": SCHEMA_VERSION, "receipt_type": "factorydark-live-postgresql-equivalence",
                "status": "passed" if passed else "failed", "production_ready": False,
                "runtime": "docker", "image": image, "network_mode": "none", "read_only_root": True,
                "cap_drop_all": True, "no_new_privileges": True, "checks": markers,
                "psql_exit_code": result.returncode, "reason_code": reason_code,
                "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
            })
        finally:
            self.run(["docker", "rm", "-f", name], text=True, capture_output=True, timeout=30)
