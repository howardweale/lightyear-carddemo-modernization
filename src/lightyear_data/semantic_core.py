from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Mapping

from .contracts import SCHEMA_VERSION, content_hash, seal


SEMANTIC_CORE_VERSION = "1.0"


class CompatibilityClass(str, Enum):
    EXACT = "exact"
    NORMALIZED_EQUIVALENT = "normalized-equivalent"
    POLICY_DECISION_REQUIRED = "policy-decision-required"
    LOSSY = "lossy"
    UNSUPPORTED = "unsupported"


COMPATIBILITY_CLASSES = tuple(item.value for item in CompatibilityClass)
CANONICAL_TYPES = (
    "boolean",
    "signed-integer",
    "exact-decimal",
    "fixed-character",
    "variable-character",
    "fixed-binary",
    "variable-binary",
    "date",
    "time",
    "timestamp",
    "timestamp-with-time-zone",
    "interval",
    "uuid",
    "json",
    "large-text",
    "large-binary",
)


class SourceAdapter(ABC):
    adapter_id: str
    adapter_version: str
    dialect: str

    @abstractmethod
    def discover_schema(self) -> dict[str, Any]: ...

    @abstractmethod
    def profile_data(self, profile_contract: Mapping[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def read_rows(self, extraction_contract: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]: ...

    @abstractmethod
    def capture_changes(self, resume_token: Mapping[str, Any] | None) -> Iterable[Mapping[str, Any]]: ...

    @abstractmethod
    def transaction_capabilities(self) -> Mapping[str, Any]: ...


class TargetAdapter(ABC):
    adapter_id: str
    adapter_version: str
    dialect: str
    default_image: str

    @abstractmethod
    def mapping(self, model: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def schema_sql(self, model: dict[str, Any]) -> str: ...

    @abstractmethod
    def fixture_sql(self, fixtures: dict[str, Any], model: dict[str, Any]) -> str: ...

    @abstractmethod
    def catalog_expectation(self, model: dict[str, Any]) -> dict[str, Any]: ...


def canonical_type(column: Mapping[str, Any]) -> dict[str, Any]:
    source_type = str(column.get("source_type", "")).upper()
    if source_type == "CHAR":
        result = {"kind": "fixed-character", "length": int(column["length"]), "encoding": "unicode-scalar"}
    elif source_type == "VARCHAR":
        result = {"kind": "variable-character", "length": int(column["length"]), "encoding": "unicode-scalar"}
    elif source_type == "DECIMAL":
        result = {"kind": "exact-decimal", "precision": int(column["precision"]), "scale": int(column.get("scale") or 0)}
    elif source_type in {"SMALLINT", "INTEGER"}:
        result = {"kind": "signed-integer", "bits": 16 if source_type == "SMALLINT" else 32}
    elif source_type == "DATE":
        result = {"kind": "date", "calendar": "proleptic-gregorian"}
    elif source_type == "TIMESTAMP":
        result = {"kind": "timestamp", "fractional_seconds": 6, "time_zone": "absent"}
    else:
        raise ValueError(f"unsupported-canonical-source-type:{source_type or 'missing'}")
    result["nullable"] = bool(column.get("nullable"))
    return result


def build_semantic_core_contract() -> dict[str, Any]:
    return seal({
        "schema_version": SCHEMA_VERSION,
        "contract_type": "lightyear-database-semantic-core",
        "semantic_core_version": SEMANTIC_CORE_VERSION,
        "canonical_type_system": {
            "types": list(CANONICAL_TYPES),
            "exact_numeric_required": True,
            "implicit_time_zone_conversion_allowed": False,
            "implicit_truncation_allowed": False,
            "null_distinct_from_empty_string": True,
        },
        "source_adapter_interface": {
            "required_operations": ["discover_schema", "profile_data", "read_rows", "capture_changes", "transaction_capabilities"],
            "resume_tokens_must_be_content_bound": True,
        },
        "target_adapter_interface": {
            "required_operations": ["mapping", "schema_sql", "fixture_sql", "catalog_expectation"],
            "generated_schema_must_be_deterministic": True,
        },
        "data_profiling_contract": {
            "required_metrics": [
                "row_count", "null_count", "empty_string_count", "minimum", "maximum",
                "maximum_character_length", "distinct_count", "invalid_encoding_count",
                "decimal_overflow_count", "timestamp_precision_observed",
            ],
            "customer_values_may_be_persisted": False,
        },
        "normalized_row_contract": {
            "cell_fields": ["canonical_type", "is_null", "value"],
            "column_order_is_schema_order": True,
            "fixed_character_comparison": "right-space-normalized",
            "decimal_representation": "non-exponent-canonical-string",
            "timestamps_require_explicit-zone-policy": True,
        },
        "comparison_contracts": {
            "rows": ["primary-key-identity", "duplicate-detection", "typed-cell-identity", "order-independent-table-comparison"],
            "queries": ["statement-identity", "parameter-identity", "column-contract", "typed-result-multiset", "error-class"],
            "transactions": ["initial-state", "ordered-operations", "commit-outcome", "rollback-outcome", "isolation-observations"],
        },
        "cdc_event_contract": {
            "operations": ["insert", "update", "delete"],
            "required_fields": ["source_adapter", "stream_id", "partition", "position", "transaction_id", "operation", "table", "key", "before", "after", "occurred_at"],
            "ddl_is_a_separate_event_class": True,
            "resume_requires_last_applied_event_hash": True,
        },
        "cutover_contract": {
            "required_gates": ["initial-load-reconciled", "cdc-caught-up", "write-freeze-observed", "final-delta-reconciled", "human-approval-valid", "rollback-checkpoint-valid"],
            "automatic_approval_allowed": False,
        },
        "rollback_contract": {
            "required_evidence": ["pre-cutover-checkpoint", "reverse-or-replay-plan", "identity-after-restore", "divergence-report"],
            "production_claim_from_rehearsal_allowed": False,
        },
        "compatibility_ledger_contract": {
            "allowed_classifications": list(COMPATIBILITY_CLASSES),
            "exactly_one_classification_per_item": True,
            "required_fields": ["item_id", "scope", "source_semantics", "target_semantics", "classification", "rationale", "evidence_required", "decision"],
            "unresolved_policy_or_loss_blocks_equivalence": True,
            "unsupported_blocks_claim_scope": True,
        },
        "adapter_conformance_contract": {
            "required_checks": ["interface", "determinism", "column-coverage", "canonical-type-coverage", "compatibility-ledger-coverage", "unsafe-classification-gates", "normalized-row-round-trip"],
            "production_qualification_implied": False,
        },
        "mainframe_equivalent": False,
        "production_ready": False,
    })


def build_profile_contract(model: Mapping[str, Any]) -> dict[str, Any]:
    return seal({
        "schema_version": SCHEMA_VERSION,
        "contract_type": "lightyear-data-profile",
        "table": f"{model['schema']}.{model['name']}",
        "model_sha256": model["content_sha256"],
        "columns": [
            {
                "name": column["name"],
                "canonical_type": canonical_type(column),
                "metrics": ["null_count", "distinct_count"] + (
                    ["empty_string_count", "maximum_character_length", "invalid_encoding_count"]
                    if column["source_type"] in {"CHAR", "VARCHAR"}
                    else ["minimum", "maximum", "decimal_overflow_count"]
                    if column["source_type"] in {"DECIMAL", "SMALLINT", "INTEGER"}
                    else ["minimum", "maximum", "timestamp_precision_observed"]
                ),
            }
            for column in model["columns"]
        ],
        "raw_values_persisted": False,
        "profile_observed": False,
        "production_ready": False,
    })


def build_canonical_schema(model: Mapping[str, Any]) -> dict[str, Any]:
    return seal({
        "schema_version": SCHEMA_VERSION,
        "schema_type": "lightyear-canonical-database-schema",
        "source_model_sha256": model["content_sha256"],
        "namespace": str(model["schema"]),
        "name": str(model["name"]),
        "columns": [
            {
                "name": column["name"],
                "ordinal": column["ordinal"],
                "type": canonical_type(column),
            }
            for column in model["columns"]
        ],
        "constraints": list(model.get("constraints", [])),
        "indexes": list(model.get("indexes", [])),
        "stored_logic": [],
        "production_ready": False,
    })


def _column_classification(column: Mapping[str, Any], target: str) -> tuple[str, str, list[str]]:
    source_type = str(column["source_type"])
    if target == "postgresql-16" and source_type in {"DECIMAL", "SMALLINT", "INTEGER", "DATE"}:
        return CompatibilityClass.EXACT.value, "Target type preserves the bounded source value domain.", []
    if target == "oracle-26ai-free" and source_type in {"CHAR", "VARCHAR"}:
        return (
            CompatibilityClass.POLICY_DECISION_REQUIRED.value,
            "Oracle collapses zero-length character values to NULL; profiling and an explicit empty-string policy are required.",
            ["empty-string-profile", "approved-null-empty-string-policy"],
        )
    return (
        CompatibilityClass.NORMALIZED_EQUIVALENT.value,
        "The value domain is preserved under the declared canonical normalization.",
        ["typed-boundary-fixtures"],
    )


def build_transformation_plan(
    model: Mapping[str, Any], mappings: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    mappings = tuple(mappings)
    targets = []
    for mapping in sorted(mappings, key=lambda item: str(item["target_dialect"])):
        targets.append({
            "target_dialect": mapping["target_dialect"],
            "mapping_sha256": mapping["content_sha256"],
            "steps": [
                {"order": 1, "operation": "create-namespace", "rollback": "drop-created-namespace"},
                {"order": 2, "operation": "create-table", "rollback": "drop-created-table"},
                {"order": 3, "operation": "load-normalized-rows", "rollback": "truncate-created-table"},
                {"order": 4, "operation": "create-constraints-and-indexes", "rollback": "drop-created-constraints-and-indexes"},
                {"order": 5, "operation": "compare-schema-data-query-and-transaction-evidence", "rollback": "retain-evidence-and-reject-cutover"},
            ],
        })
    return seal({
        "schema_version": SCHEMA_VERSION,
        "plan_type": "lightyear-schema-transformation-plan",
        "source_model_sha256": model["content_sha256"],
        "source_table": f"{model['schema']}.{model['name']}",
        "targets": targets,
        "stored_logic_in_scope": False,
        "automatic_cutover_allowed": False,
        "production_ready": False,
    })


def build_compatibility_ledger(
    model: Mapping[str, Any], mappings: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    mappings = tuple(mappings)
    entries: list[dict[str, Any]] = []
    for mapping in sorted(mappings, key=lambda item: str(item["target_dialect"])):
        target = str(mapping["target_dialect"])
        mapped = {str(item["source"]): item for item in mapping["columns"]}
        for column in model["columns"]:
            item = mapped[column["name"]]
            classification, rationale, evidence = _column_classification(column, target)
            entries.append({
                "item_id": f"column:{target}:{column['name']}",
                "scope": "column-type-and-value-semantics",
                "source_semantics": {"dialect": "db2-zos", "name": column["name"], "type": item["source_type"], "nullable": column["nullable"]},
                "target_semantics": {"dialect": target, "name": item["target"], "type": item["target_type"], "nullable": item["nullable"]},
                "classification": classification,
                "rationale": rationale,
                "evidence_required": evidence,
                "decision": "unresolved" if classification == CompatibilityClass.POLICY_DECISION_REQUIRED.value else "accepted-by-core-policy",
            })
        behavior = [
            ("transaction-isolation", CompatibilityClass.POLICY_DECISION_REQUIRED.value, "Isolation levels and locking outcomes require observed workload-specific policy.", ["concurrent-transaction-probes", "approved-isolation-policy"]),
            ("cdc-ddl", CompatibilityClass.UNSUPPORTED.value, "The bounded CDC contract carries row changes; DDL propagation is outside this claim.", ["separate-ddl-migration-plan"]),
            ("cdc-sequence-state", CompatibilityClass.UNSUPPORTED.value, "Sequence state is not represented by the AUTHFRDS model or row-change stream.", ["separate-sequence-state-plan"]),
            ("stored-logic", CompatibilityClass.UNSUPPORTED.value, "Stored procedures, triggers, and arbitrary application SQL require separate qualification gates.", ["stored-logic-inventory-and-qualification"]),
        ]
        for name, classification, rationale, evidence in behavior:
            entries.append({
                "item_id": f"behavior:{target}:{name}",
                "scope": name,
                "source_semantics": {"dialect": "db2-zos", "claim": "not-observed"},
                "target_semantics": {"dialect": target, "claim": "not-qualified"},
                "classification": classification,
                "rationale": rationale,
                "evidence_required": evidence,
                "decision": "unresolved" if classification == CompatibilityClass.POLICY_DECISION_REQUIRED.value else "excluded-from-claim-scope",
            })
    counts = Counter(item["classification"] for item in entries)
    return seal({
        "schema_version": SCHEMA_VERSION,
        "ledger_type": "lightyear-database-compatibility-ledger",
        "source_model_sha256": model["content_sha256"],
        "mapping_sha256s": sorted(str(item["content_sha256"]) for item in mappings),
        "classifications": list(COMPATIBILITY_CLASSES),
        "entries": entries,
        "statistics": {name: counts.get(name, 0) for name in COMPATIBILITY_CLASSES},
        "equivalence_blocked": any(item["classification"] in {CompatibilityClass.POLICY_DECISION_REQUIRED.value, CompatibilityClass.LOSSY.value} and item["decision"] == "unresolved" for item in entries),
        "claim_scope_excludes_unsupported": True,
        "production_ready": False,
    })


def validate_compatibility_ledger(
    ledger: Mapping[str, Any], model: Mapping[str, Any], mappings: Iterable[Mapping[str, Any]]
) -> list[str]:
    mappings = tuple(mappings)
    errors: list[str] = []
    if ledger.get("content_sha256") != content_hash(dict(ledger)):
        errors.append("compatibility-ledger-content-hash-invalid")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return errors + ["compatibility-ledger-entries-missing"]
    ids = [item.get("item_id") for item in entries if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        errors.append("compatibility-ledger-item-id-duplicate")
    for item in entries:
        if not isinstance(item, dict) or item.get("classification") not in COMPATIBILITY_CLASSES:
            errors.append("compatibility-ledger-classification-invalid")
            continue
        required = {"item_id", "scope", "source_semantics", "target_semantics", "classification", "rationale", "evidence_required", "decision"}
        if not required.issubset(item):
            errors.append("compatibility-ledger-entry-incomplete")
        if item["classification"] in {CompatibilityClass.POLICY_DECISION_REQUIRED.value, CompatibilityClass.LOSSY.value} and item.get("decision") == "accepted-by-core-policy":
            errors.append("compatibility-ledger-unsafe-auto-acceptance")
    expected_columns = {
        f"column:{mapping['target_dialect']}:{column['name']}"
        for mapping in mappings for column in model["columns"]
    }
    if not expected_columns.issubset(set(ids)):
        errors.append("compatibility-ledger-column-coverage-incomplete")
    return sorted(set(errors))


def normalize_row(row: Mapping[str, Any], model: Mapping[str, Any]) -> dict[str, Any]:
    columns = [column["name"] for column in model["columns"]]
    if set(row) != set(columns):
        raise ValueError("normalized-row-column-set-invalid")
    cells = []
    for column in model["columns"]:
        value = row[column["name"]]
        kind = canonical_type(column)["kind"]
        if value is None:
            normalized = None
        elif kind == "fixed-character":
            normalized = str(value).rstrip(" ")
        elif kind == "exact-decimal":
            try:
                normalized = format(Decimal(str(value)), f".{int(column.get('scale') or 0)}f")
            except InvalidOperation as error:
                raise ValueError(f"normalized-row-decimal-invalid:{column['name']}") from error
        elif kind == "signed-integer":
            normalized = str(int(value))
        else:
            normalized = str(value)
        cells.append({"name": column["name"], "canonical_type": kind, "is_null": value is None, "value": normalized})
    return seal({
        "schema_version": SCHEMA_VERSION,
        "row_type": "lightyear-normalized-row",
        "model_sha256": model["content_sha256"],
        "cells": cells,
    })


def compare_normalized_rows(expected: Iterable[Mapping[str, Any]], actual: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    expected_hashes = Counter(str(item.get("content_sha256")) for item in expected)
    actual_hashes = Counter(str(item.get("content_sha256")) for item in actual)
    return seal({
        "schema_version": SCHEMA_VERSION,
        "comparison_type": "lightyear-normalized-row-multiset-comparison",
        "status": "passed" if expected_hashes == actual_hashes else "failed",
        "expected_count": sum(expected_hashes.values()),
        "actual_count": sum(actual_hashes.values()),
        "missing": sorted((expected_hashes - actual_hashes).elements()),
        "unexpected": sorted((actual_hashes - expected_hashes).elements()),
        "production_ready": False,
    })


def compare_query_results(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> dict[str, Any]:
    required = {"statement_sha256", "parameters_sha256", "columns", "rows", "error_class"}
    if not required.issubset(expected) or not required.issubset(actual):
        raise ValueError("query-result-contract-incomplete")
    checks = {name: expected[name] == actual[name] for name in sorted(required)}
    return seal({"schema_version": SCHEMA_VERSION, "comparison_type": "lightyear-query-result-comparison", "checks": checks, "status": "passed" if all(checks.values()) else "failed", "production_ready": False})


def compare_transactions(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("initial_state_sha256", "operations_sha256", "commit_state_sha256", "rollback_state_sha256", "error_class", "isolation_observations")
    if any(name not in expected or name not in actual for name in fields):
        raise ValueError("transaction-comparison-contract-incomplete")
    checks = {name: expected[name] == actual[name] for name in fields}
    return seal({"schema_version": SCHEMA_VERSION, "comparison_type": "lightyear-transaction-comparison", "checks": checks, "status": "passed" if all(checks.values()) else "failed", "production_ready": False})


def validate_cdc_event(event: Mapping[str, Any]) -> list[str]:
    required = {"source_adapter", "stream_id", "partition", "position", "transaction_id", "operation", "table", "key", "before", "after", "occurred_at", "content_sha256"}
    errors = []
    if not required.issubset(event):
        errors.append("cdc-event-fields-incomplete")
    if event.get("operation") not in {"insert", "update", "delete"}:
        errors.append("cdc-event-operation-invalid")
    if event.get("content_sha256") != content_hash(dict(event)):
        errors.append("cdc-event-content-hash-invalid")
    operation = event.get("operation")
    if operation == "insert" and (event.get("before") is not None or not isinstance(event.get("after"), dict)):
        errors.append("cdc-insert-image-invalid")
    if operation == "delete" and (not isinstance(event.get("before"), dict) or event.get("after") is not None):
        errors.append("cdc-delete-image-invalid")
    if operation == "update" and (not isinstance(event.get("before"), dict) or not isinstance(event.get("after"), dict)):
        errors.append("cdc-update-image-invalid")
    return sorted(set(errors))


def validate_cutover_and_rollback(cutover: Mapping[str, Any], rollback: Mapping[str, Any]) -> list[str]:
    errors = []
    gates = {"initial-load-reconciled", "cdc-caught-up", "write-freeze-observed", "final-delta-reconciled", "human-approval-valid", "rollback-checkpoint-valid"}
    if set(cutover.get("gates", {})) != gates or any(value is not True for value in cutover.get("gates", {}).values()):
        errors.append("cutover-gates-incomplete")
    if cutover.get("automatic_approval") is not False:
        errors.append("cutover-automatic-approval-invalid")
    evidence = {"pre-cutover-checkpoint", "reverse-or-replay-plan", "identity-after-restore", "divergence-report"}
    if set(rollback.get("evidence", {})) != evidence or any(not value for value in rollback.get("evidence", {}).values()):
        errors.append("rollback-evidence-incomplete")
    if rollback.get("production_ready") is not False:
        errors.append("rollback-overclaims-production-readiness")
    return sorted(errors)


def adapter_conformance_receipt(
    adapters: Iterable[TargetAdapter], model: Mapping[str, Any], ledger: Mapping[str, Any], fixtures: Mapping[str, Any]
) -> dict[str, Any]:
    adapters = tuple(adapters)
    results = []
    ledger_errors = validate_compatibility_ledger(ledger, model, [adapter.mapping(dict(model)) for adapter in adapters])
    for adapter in adapters:
        mapping_one = adapter.mapping(dict(model))
        mapping_two = adapter.mapping(dict(model))
        normalized = [normalize_row(row, model) for row in fixtures.get("rows", [])]
        checks = {
            "interface": all(callable(getattr(adapter, name, None)) for name in ("mapping", "schema_sql", "fixture_sql", "catalog_expectation")),
            "determinism": mapping_one == mapping_two and adapter.schema_sql(dict(model)) == adapter.schema_sql(dict(model)),
            "column_coverage": [item["source"] for item in mapping_one.get("columns", [])] == [item["name"] for item in model["columns"]],
            "canonical_type_coverage": all(canonical_type(item)["kind"] in CANONICAL_TYPES for item in model["columns"]),
            "compatibility_ledger_coverage": not ledger_errors,
            "unsafe_classification_gates": ledger.get("equivalence_blocked") is True,
            "normalized_row_round_trip": bool(normalized) and compare_normalized_rows(normalized, normalized)["status"] == "passed",
        }
        results.append({"adapter": {"id": adapter.adapter_id, "version": adapter.adapter_version, "dialect": adapter.dialect}, "checks": checks, "status": "passed" if all(checks.values()) else "failed"})
    return seal({
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "lightyear-adapter-conformance",
        "semantic_core_version": SEMANTIC_CORE_VERSION,
        "model_sha256": model["content_sha256"],
        "ledger_sha256": ledger["content_sha256"],
        "adapters": results,
        "status": "passed" if results and all(item["status"] == "passed" for item in results) else "failed",
        "production_qualification_implied": False,
        "production_ready": False,
    })
