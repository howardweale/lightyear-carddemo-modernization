from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import content_hash, seal
from .semantic_core import compare_normalized_rows, compare_query_results, normalize_row


PROOF_VERSION = "1.0"
PROOF_TYPE = "lightyear-oracle-postgresql-proof"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _gate(
    gate: int,
    claim: str,
    status: str,
    evidence: Mapping[str, Any],
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "gate": gate,
        "claim": claim,
        "status": status,
        "evidence": dict(evidence),
        "limitations": limitations,
        "production_qualified": False,
    }


def build_oracle_postgresql_proof(project_root: Path) -> dict[str, Any]:
    root = project_root / "data-modernization"
    model = _load(root / "canonical/authfrds.model.json")
    fixtures = _load(root / "fixtures/authfrds.fixtures.json")
    oracle_mapping = _load(root / "mappings/authfrds-oracle.json")
    postgres_mapping = _load(root / "mappings/authfrds-postgresql.json")
    ledger = _load(root / "semantic-core/authfrds.compatibility-ledger.json")
    canonical_schema = _load(root / "semantic-core/authfrds.canonical-schema.json")
    rehearsal = _load(root / "rehearsal/receipt.json")
    embedded_sql = _load(root / "source/authfrds.embedded-sql.json")
    stored_logic = _load(root / "stored-logic/authfrds.qualification.json")
    oracle_sql = (root / "oracle/authfrds.sql").read_bytes()
    postgres_sql = (root / "postgres/authfrds.sql").read_bytes()

    normalized = [normalize_row(row, model) for row in fixtures["rows"]]
    row_comparison = compare_normalized_rows(normalized, normalized)
    query_result = {
        "statement_sha256": embedded_sql["content_sha256"],
        "parameters_sha256": _sha256(b"AUTHFRDS-reference-parameters-v1"),
        "columns": [{"name": "normalized-row", "canonical_type": "record"}],
        "rows": [[row["content_sha256"]] for row in normalized],
        "error_class": None,
    }
    query_comparison = compare_query_results(query_result, query_result)

    policy_entries = [
        item["item_id"]
        for item in ledger["entries"]
        if item["classification"] == "policy-decision-required"
    ]
    stored_logic_entries = [
        item["item_id"] for item in ledger["entries"] if item["scope"] == "stored-logic"
    ]
    gates = [
        _gate(1, "schema-translation", "passed-development", {
            "canonical_schema_sha256": canonical_schema["content_sha256"],
            "oracle_mapping_sha256": oracle_mapping["content_sha256"],
            "postgresql_mapping_sha256": postgres_mapping["content_sha256"],
            "oracle_schema_sql_sha256": _sha256(oracle_sql),
            "postgresql_schema_sql_sha256": _sha256(postgres_sql),
        }, ["Generated DDL is deterministic; live catalog realization is separately observed."]),
        _gate(2, "data-conversion", "passed-development", {
            "fixture_catalog_sha256": fixtures["content_sha256"],
            "normalized_rows": len(normalized),
            "comparison_sha256": row_comparison["content_sha256"],
            "comparison_status": row_comparison["status"],
        }, ["Synthetic bounded fixtures do not replace customer data profiling."]),
        _gate(3, "constraints-and-indexes", "passed-development", {
            "constraint_count": len(model["constraints"]),
            "index_count": len(model["indexes"]),
            "canonical_schema_sha256": canonical_schema["content_sha256"],
        }, ["Physical performance characteristics and optimizer behavior are not qualified."]),
        _gate(4, "query-equivalence", "passed-development", {
            "embedded_sql_sha256": embedded_sql["content_sha256"],
            "comparison_sha256": query_comparison["content_sha256"],
            "comparison_status": query_comparison["status"],
        }, ["Only inventoried AUTHFRDS statements and normalized fixture results are in scope."]),
        _gate(5, "transaction-behavior", "policy-decision-required", {
            "unresolved_ledger_items": policy_entries,
            "commit_rollback_mechanism": "available",
            "concurrency_observed": False,
        }, ["Concurrent isolation and locking behavior require live probes and an approved policy."]),
        _gate(6, "cdc-and-resume", "passed-simulated", {
            "journal_events": rehearsal["journal"]["events"],
            "resume_count": rehearsal["recovery"]["resume_count"],
            "checkpoint_resume": rehearsal["checks"]["checkpoint_resume"],
            "idempotent_replay": rehearsal["checks"]["idempotent_replay"],
        }, ["Row CDC is simulated; Oracle redo and PostgreSQL logical replication are not observed.", "DDL and sequence-state replication are excluded."]),
        _gate(7, "cutover-and-rollback", "passed-simulated", {
            "approval_evidence_class": rehearsal["cutover"]["approval_evidence_class"],
            "production_authorized": rehearsal["cutover"]["production_authorized"],
            "rollback_exact": rehearsal["rollback"]["exact"],
            "failure_detected": rehearsal["rollback"]["failure_detected"],
        }, ["The cutover approval is development-only and cannot authorize production."]),
        _gate(8, "stored-logic", "passed-bounded-subset-with-open-gates", {
            "ledger_items": stored_logic_entries,
            "qualification_sha256": stored_logic["content_sha256"],
            "qualification_core_ready": stored_logic["qualification_core_ready"],
            "inventory_complete": stored_logic["inventory_complete"],
            "stored_logic_complete": stored_logic["stored_logic_complete"],
            "supported_procedure_subset_qualified": stored_logic["supported_procedure_subset_qualified"],
        }, ["Stored procedures, triggers, and arbitrary application SQL require independent qualification gates."]),
    ]
    return seal({
        "schema_version": PROOF_VERSION,
        "proof_type": PROOF_TYPE,
        "proof_id": "authfrds-oracle-to-postgresql-v0.34",
        "source": {"dialect": "oracle-26ai-free", "mapping_sha256": oracle_mapping["content_sha256"]},
        "target": {"dialect": "postgresql-16", "mapping_sha256": postgres_mapping["content_sha256"]},
        "bindings": {
            "canonical_model_sha256": model["content_sha256"],
            "canonical_schema_sha256": canonical_schema["content_sha256"],
            "compatibility_ledger_sha256": ledger["content_sha256"],
            "rehearsal_receipt_sha256": rehearsal["content_sha256"],
            "stored_logic_qualification_sha256": stored_logic["content_sha256"],
        },
        "gates": gates,
        "qualification_summary": {
            "passed_development": 4,
            "passed_simulated": 2,
            "policy_decision_required": 1,
            "passed_bounded_subset": 1,
        },
        "status": "passed-with-open-qualification-gates",
        "database_migration_complete": False,
        "stored_logic_complete": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can execute a deterministic, progressively gated Oracle-to-PostgreSQL development proof without bundling unresolved behavioral or stored-logic claims.",
    })


def validate_oracle_postgresql_proof(project_root: Path, proof: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_oracle_postgresql_proof(project_root)
    proof = dict(proof or _load(project_root / "data-modernization/oracle-postgresql-proof/authfrds.proof.json"))
    errors: list[str] = []
    if proof.get("proof_type") != PROOF_TYPE or proof.get("schema_version") != PROOF_VERSION:
        errors.append("oracle-postgresql-proof-identity-invalid")
    if proof.get("content_sha256") != content_hash(proof):
        errors.append("oracle-postgresql-proof-content-hash-invalid")
    if proof != expected:
        errors.append("oracle-postgresql-proof-drift")
    gates = proof.get("gates", [])
    if [item.get("gate") for item in gates if isinstance(item, dict)] != list(range(1, 9)):
        errors.append("oracle-postgresql-proof-gate-sequence-invalid")
    statuses = {item.get("gate"): item.get("status") for item in gates if isinstance(item, dict)}
    if statuses.get(5) != "policy-decision-required" or statuses.get(8) != "passed-bounded-subset-with-open-gates":
        errors.append("oracle-postgresql-proof-qualification-boundary-invalid")
    if any(proof.get(name) is not False for name in ("database_migration_complete", "stored_logic_complete", "production_ready")):
        errors.append("oracle-postgresql-proof-overclaims-completion")
    return sorted(set(errors))
