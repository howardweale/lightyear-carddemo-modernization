from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import content_hash, seal


QUALIFICATION_TYPE = "lightyear-stored-logic-qualification"
QUALIFICATION_VERSION = "1.0"
OBJECT_KINDS = (
    "procedure", "function", "package", "package-body", "trigger",
    "view", "materialized-view", "application-sql",
)
QUALIFICATION_GATES = (
    "inventory-completeness", "dependency-closure", "translation",
    "result-and-side-effect-equivalence", "transaction-and-exception-behavior",
    "security-context", "performance-and-operability",
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def build_stored_logic_qualification(project_root: Path) -> dict[str, Any]:
    root = project_root / "data-modernization"
    model = _load(root / "canonical/authfrds.model.json")
    embedded = _load(root / "source/authfrds.embedded-sql.json")
    ledger = _load(root / "semantic-core/authfrds.compatibility-ledger.json")
    application_sql = []
    for statement in embedded.get("statements", []):
        if statement.get("operation") not in {"INSERT", "UPDATE", "DELETE", "SELECT"}:
            continue
        application_sql.append({
            "object_id": statement["id"],
            "kind": "application-sql",
            "source_path": embedded["path"],
            "operation": statement["operation"],
            "dependencies": [statement["table"]] if statement.get("table") else [],
            "classification": "policy-decision-required",
            "qualification_status": "not-qualified",
            "required_evidence": [
                "oracle-execution-baseline", "postgresql-execution-result",
                "side-effect-comparison", "error-and-sqlstate-mapping",
            ],
        })
    object_counts = {kind: 0 for kind in OBJECT_KINDS}
    object_counts["application-sql"] = len(application_sql)
    gates = [
        {"gate": "inventory-completeness", "status": "blocked-live-catalog-required", "evidence": {"source_only_objects": len(application_sql), "oracle_catalog_observed": False}},
        {"gate": "dependency-closure", "status": "passed-source-only", "evidence": {"objects": len(application_sql), "unresolved_external_dependencies": 0}},
        {"gate": "translation", "status": "policy-decision-required", "evidence": {"qualified_objects": 0, "objects_requiring_policy": len(application_sql)}},
        {"gate": "result-and-side-effect-equivalence", "status": "blocked-no-execution-baseline", "evidence": {"qualified_objects": 0}},
        {"gate": "transaction-and-exception-behavior", "status": "blocked-no-live-probes", "evidence": {"autonomous_transactions_qualified": False, "exception_mapping_qualified": False}},
        {"gate": "security-context", "status": "blocked-no-privilege-capture", "evidence": {"definer_invoker_rights_qualified": False, "grants_qualified": False}},
        {"gate": "performance-and-operability", "status": "blocked-no-operational-baseline", "evidence": {"plans_compared": 0, "scheduler_jobs_qualified": 0}},
    ]
    return seal({
        "schema_version": QUALIFICATION_VERSION,
        "qualification_type": QUALIFICATION_TYPE,
        "qualification_id": "authfrds-stored-logic-v0.35",
        "source_dialect": "oracle-26ai-free",
        "target_dialect": "postgresql-16",
        "bindings": {
            "canonical_model_sha256": model["content_sha256"],
            "embedded_sql_sha256": embedded["content_sha256"],
            "compatibility_ledger_sha256": ledger["content_sha256"],
        },
        "inventory_contract": {
            "object_kinds": list(OBJECT_KINDS),
            "required_sources": ["oracle-catalog", "application-source", "deployment-ddl", "scheduler-and-grants"],
            "source_only_inventory": True,
            "live_catalog_observed": False,
        },
        "object_counts": object_counts,
        "objects": application_sql,
        "qualification_gates": gates,
        "classification_policy": {
            "allowed": ["exact", "normalized-equivalent", "policy-decision-required", "lossy", "unsupported"],
            "unresolved_policy_blocks_completion": True,
            "lossy_blocks_completion": True,
            "unsupported_requires_explicit_exclusion": True,
        },
        "qualification_core_ready": True,
        "inventory_complete": False,
        "stored_logic_complete": False,
        "database_migration_complete": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can inventory and independently qualify stored logic without bundling unobserved Oracle behavior into a database migration claim.",
    })


def validate_stored_logic_qualification(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_stored_logic_qualification(project_root)
    payload = dict(payload or _load(project_root / "data-modernization/stored-logic/authfrds.qualification.json"))
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE or payload.get("schema_version") != QUALIFICATION_VERSION:
        errors.append("stored-logic-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("stored-logic-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("stored-logic-qualification-drift")
    gates = payload.get("qualification_gates", [])
    if [item.get("gate") for item in gates if isinstance(item, dict)] != list(QUALIFICATION_GATES):
        errors.append("stored-logic-qualification-gates-incomplete")
    if any(payload.get(name) is not False for name in ("inventory_complete", "stored_logic_complete", "database_migration_complete", "production_ready")):
        errors.append("stored-logic-qualification-overclaims-completion")
    objects = payload.get("objects", [])
    if any(item.get("classification") not in payload.get("classification_policy", {}).get("allowed", []) for item in objects if isinstance(item, dict)):
        errors.append("stored-logic-qualification-classification-invalid")
    return sorted(set(errors))
