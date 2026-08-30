from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import content_hash, verify_signature
from .equivalence import offline_equivalence
from .oracle import OracleAdapter
from .postgres import PostgreSQLAdapter
from .semantic_core import (
    adapter_conformance_receipt,
    build_compatibility_ledger,
    build_canonical_schema,
    build_profile_contract,
    build_semantic_core_contract,
    build_transformation_plan,
    validate_compatibility_ledger,
)


DEVELOPMENT_KEY = "factorydark-v0.19-development-only"


def validate_assets(root: Path) -> dict[str, Any]:
    base = root / "data-modernization"
    paths = {
        "model": base / "canonical/authfrds.model.json",
        "dcl": base / "source/authfrds.dcl-contract.json",
        "sql": base / "source/authfrds.embedded-sql.json",
        "mapping": base / "mappings/authfrds-postgresql.json",
        "oracle_mapping": base / "mappings/authfrds-oracle.json",
        "fixtures": base / "fixtures/authfrds.fixtures.json",
        "receipt": base / "receipts/authfrds.offline.receipt.json",
        "postgres": base / "postgres/authfrds.sql",
        "oracle": base / "oracle/authfrds.sql",
        "oracle_receipt": base / "receipts/authfrds.oracle-offline.receipt.json",
        "target_plan": base / "receipts/authfrds.target-plan.json",
        "semantic_core": base / "semantic-core/database-semantic-core.json",
        "canonical_schema": base / "semantic-core/authfrds.canonical-schema.json",
        "profile_contract": base / "semantic-core/authfrds.profile-contract.json",
        "transformation_plan": base / "semantic-core/authfrds.schema-transformation-plan.json",
        "compatibility_ledger": base / "semantic-core/authfrds.compatibility-ledger.json",
        "conformance_receipt": base / "semantic-core/authfrds.adapter-conformance.receipt.json",
    }
    errors = [f"missing:{name}" for name, path in paths.items() if not path.is_file()]
    if errors:
        return {"status": "failed", "errors": errors}
    payloads = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items() if name not in {"postgres", "oracle"}}
    for name, payload in payloads.items():
        if payload.get("content_sha256") != content_hash(payload):
            errors.append(f"content-hash:{name}")
    model = payloads["model"]
    dcl = payloads["dcl"]
    sql = payloads["sql"]
    if [column["name"] for column in model.get("columns", [])] != dcl.get("declared_columns"):
        errors.append("ddl-dcl-column-mismatch")
    operations = [item["operation"] for item in sql.get("statements", [])]
    if "INSERT" not in operations or "UPDATE" not in operations:
        errors.append("embedded-sql-write-coverage")
    expected_receipt = offline_equivalence(model, payloads["mapping"], payloads["fixtures"])
    receipt = payloads["receipt"]
    if receipt.get("status") != "passed" or expected_receipt.get("content_sha256") != receipt.get("content_sha256"):
        errors.append("offline-equivalence-receipt-mismatch")
    if not verify_signature(receipt, DEVELOPMENT_KEY):
        errors.append("development-signature-invalid")
    expected_oracle = offline_equivalence(model, payloads["oracle_mapping"], payloads["fixtures"])
    oracle_receipt = payloads["oracle_receipt"]
    if expected_oracle.get("content_sha256") != oracle_receipt.get("content_sha256"):
        errors.append("oracle-offline-equivalence-receipt-mismatch")
    if not verify_signature(oracle_receipt, DEVELOPMENT_KEY):
        errors.append("oracle-development-signature-invalid")
    plan_targets = {item.get("dialect") for item in payloads["target_plan"].get("targets", [])}
    if plan_targets != {"postgresql-16", "oracle-26ai-free"}:
        errors.append("target-plan-incomplete")
    mappings = (payloads["mapping"], payloads["oracle_mapping"])
    expected_semantic = {
        "semantic_core": build_semantic_core_contract(),
        "canonical_schema": build_canonical_schema(model),
        "profile_contract": build_profile_contract(model),
        "transformation_plan": build_transformation_plan(model, mappings),
        "compatibility_ledger": build_compatibility_ledger(model, mappings),
    }
    for name, expected in expected_semantic.items():
        if payloads[name] != expected:
            errors.append(f"semantic-core-drift:{name}")
    errors.extend(validate_compatibility_ledger(payloads["compatibility_ledger"], model, mappings))
    expected_conformance = adapter_conformance_receipt(
        (PostgreSQLAdapter(), OracleAdapter()), model,
        payloads["compatibility_ledger"], payloads["fixtures"],
    )
    if payloads["conformance_receipt"] != expected_conformance:
        errors.append("adapter-conformance-receipt-mismatch")
    return {
        "status": "passed" if not errors else "failed", "errors": sorted(errors),
        "statistics": {"columns": len(model.get("columns", [])), "sql_statements": len(sql.get("statements", [])), "fixture_rows": len(payloads["fixtures"].get("rows", []))},
        "limitations": ["Development signature is not a customer production credential.", "Live Db2 and z/OS equivalence remain pending.", "Unresolved compatibility decisions block equivalence."],
    }
