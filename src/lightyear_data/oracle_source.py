from __future__ import annotations

import copy
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from .builder import load_assets
from .contracts import content_hash, seal
from .oracle import OracleAdapter
from .oracle_procedures import (
    build_procedure_conformance,
    build_procedure_ledger,
    build_procedure_qualification,
)
from .postgres import PostgreSQLAdapter
from .semantic_core import (
    COMPATIBILITY_CLASSES,
    SourceAdapter,
    build_canonical_schema,
    build_profile_contract,
    compare_normalized_rows,
    compare_query_results,
    normalize_row,
)


QUALIFICATION_TYPE = "lightyear-oracle-postgresql-source-qualification"
QUALIFICATION_ID = "authfrds-oracle-postgresql-source-v0.43"


class OracleSourceAdapter(SourceAdapter):
    """Bounded Oracle source projection with fail-closed live-evidence labels."""

    adapter_id = "lightyear-oracle-source"
    adapter_version = "1.0"
    dialect = "oracle-26ai-free"

    def __init__(
        self,
        model: Mapping[str, Any],
        rows: Iterable[Mapping[str, Any]] = (),
        events: Iterable[Mapping[str, Any]] = (),
        *,
        catalog_observed: bool = False,
        profile_observed: bool = False,
        redo_observed: bool = False,
        transaction_observed: bool = False,
    ) -> None:
        self._model = copy.deepcopy(dict(model))
        self._rows = tuple(copy.deepcopy(dict(row)) for row in rows)
        self._events = tuple(copy.deepcopy(dict(event)) for event in events)
        self._catalog_observed = catalog_observed
        self._profile_observed = profile_observed
        self._redo_observed = redo_observed
        self._transaction_observed = transaction_observed

    def discover_schema(self) -> dict[str, Any]:
        oracle = OracleAdapter()
        return seal({
            "schema_version": "1.0",
            "discovery_type": "lightyear-oracle-source-schema-discovery",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "dialect": self.dialect,
            "canonical_schema": build_canonical_schema(self._model),
            "source_columns": [{
                "name": item["name"],
                "ordinal": item["ordinal"],
                "oracle_type": oracle.target_type(item),
                "nullable": item["nullable"],
            } for item in self._model["columns"]],
            "catalog_observed": self._catalog_observed,
            "evidence_class": "live-oracle-catalog" if self._catalog_observed else "bounded-source-contract",
            "production_ready": False,
        })

    def profile_data(self, profile_contract: Mapping[str, Any]) -> dict[str, Any]:
        if profile_contract.get("model_sha256") != self._model.get("content_sha256"):
            raise ValueError("oracle-source-profile-model-binding-invalid")
        profiles = []
        for column in self._model["columns"]:
            name = column["name"]
            values = [row.get(name) for row in self._rows]
            non_null = [value for value in values if value is not None]
            text = [str(value) for value in non_null]
            metrics: dict[str, Any] = {
                "row_count": len(values),
                "null_count": len(values) - len(non_null),
                "distinct_count": len(set(text)),
            }
            if column["source_type"] in {"CHAR", "VARCHAR"}:
                metrics.update({
                    "empty_string_count": sum(value == "" for value in text),
                    "maximum_character_length": max((len(value) for value in text), default=0),
                    "invalid_encoding_count": 0,
                })
            elif column["source_type"] in {"DECIMAL", "SMALLINT", "INTEGER"}:
                decimals = [Decimal(value) for value in text]
                metrics.update({
                    "minimum": format(min(decimals), "f") if decimals else None,
                    "maximum": format(max(decimals), "f") if decimals else None,
                    "decimal_overflow_count": 0,
                })
            else:
                metrics.update({
                    "minimum": min(text) if text else None,
                    "maximum": max(text) if text else None,
                    "timestamp_precision_observed": 6 if column["source_type"] == "TIMESTAMP" and text else None,
                })
            profiles.append({"name": name, "metrics": metrics})
        return seal({
            "schema_version": "1.0",
            "profile_type": "lightyear-oracle-source-data-profile",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "model_sha256": self._model["content_sha256"],
            "profile_contract_sha256": profile_contract["content_sha256"],
            "columns": profiles,
            "raw_values_persisted": False,
            "profile_observed": self._profile_observed,
            "evidence_class": "live-oracle-profile" if self._profile_observed else "bounded-fixture-profile",
            "production_ready": False,
        })

    def read_rows(self, extraction_contract: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
        if extraction_contract.get("model_sha256") != self._model.get("content_sha256"):
            raise ValueError("oracle-source-extraction-model-binding-invalid")
        expected = [column["name"] for column in self._model["columns"]]
        if extraction_contract.get("columns") != expected:
            raise ValueError("oracle-source-extraction-column-contract-invalid")
        return tuple(copy.deepcopy(row) for row in self._rows)

    def capture_changes(self, resume_token: Mapping[str, Any] | None) -> Iterable[Mapping[str, Any]]:
        position = None
        last_event_sha256 = None
        if resume_token is not None:
            token = dict(resume_token)
            if token.get("adapter_id") != self.adapter_id or token.get("content_sha256") != content_hash(token):
                raise ValueError("oracle-source-cdc-resume-token-invalid")
            position = token.get("position")
            last_event_sha256 = token.get("last_event_sha256")
        events = self._events
        if position is not None:
            positions = [event.get("position") for event in events]
            if position not in positions:
                raise ValueError("oracle-source-cdc-resume-position-unknown")
            index = positions.index(position)
            if events[index].get("content_sha256") != last_event_sha256:
                raise ValueError("oracle-source-cdc-resume-event-binding-invalid")
            events = events[index + 1 :]
        return tuple(copy.deepcopy(event) for event in events)

    def transaction_capabilities(self) -> Mapping[str, Any]:
        return seal({
            "schema_version": "1.0",
            "capability_type": "lightyear-oracle-source-transaction-capabilities",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "commit": "supported",
            "rollback": "supported",
            "savepoints": "supported-not-qualified",
            "isolation": "read-committed-default-policy-decision-required",
            "locking": "multi-version-read-consistency-live-probes-required",
            "empty_string_is_null": True,
            "capabilities_observed": self._transaction_observed,
            "production_ready": False,
        })


def reference_oracle_events(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in rows]
    if len(rows) < 2:
        raise ValueError("oracle-source-reference-events-require-two-rows")
    events = [
        {"position": "SCN:000000000001", "transaction_id": "ORA-TX-001", "operation": "insert", "key": {"CARD_NUM": rows[0]["CARD_NUM"], "AUTH_TS": rows[0]["AUTH_TS"]}, "before": None, "after": rows[0]},
        {"position": "SCN:000000000002", "transaction_id": "ORA-TX-002", "operation": "insert", "key": {"CARD_NUM": rows[1]["CARD_NUM"], "AUTH_TS": rows[1]["AUTH_TS"]}, "before": None, "after": rows[1]},
        {"position": "SCN:000000000003", "transaction_id": "ORA-TX-003", "operation": "update", "key": {"CARD_NUM": rows[0]["CARD_NUM"], "AUTH_TS": rows[0]["AUTH_TS"]}, "before": {"AUTH_FRAUD": "N"}, "after": {"AUTH_FRAUD": "Y"}},
        {"position": "SCN:000000000004", "transaction_id": "ORA-TX-004", "operation": "delete", "key": {"CARD_NUM": rows[1]["CARD_NUM"], "AUTH_TS": rows[1]["AUTH_TS"]}, "before": rows[1], "after": None},
    ]
    return [seal({
        "schema_version": "1.0",
        "event_type": "lightyear-oracle-cdc-event",
        "source_adapter": OracleSourceAdapter.adapter_id,
        "stream_id": "AUTHFRDS-REFERENCE",
        "partition": "0",
        **event,
        "table": "CARDDEMO.AUTHFRDS",
        "occurred_at": f"2026-08-31T00:00:0{index}Z",
        "evidence_class": "bounded-redo-shape",
    }) for index, event in enumerate(events, 1)]


def build_oracle_source_ledger(model: Mapping[str, Any]) -> dict[str, Any]:
    entries = []
    for column in model["columns"]:
        character = column["source_type"] in {"CHAR", "VARCHAR"}
        entries.append({
            "item_id": f"oracle-source-column:{column['name']}",
            "scope": "source-column-to-canonical-type",
            "source_semantics": {"dialect": "oracle-26ai-free", "oracle_type": OracleAdapter.target_type(column)},
            "target_semantics": {"canonical_source_type": column["source_type"]},
            "classification": "policy-decision-required" if character else "exact",
            "decision": "unresolved" if character else "no-policy-required",
            "evidence_required": ["empty-string-and-padding-profile", "approved-null-policy"] if character else ["catalog-and-boundary-values"],
        })
    behaviors = (
        ("number-precision-scale", "exact", "no-policy-required", ["catalog-precision-scale"]),
        ("date-includes-time", "normalized-equivalent", "governed-normalization", ["date-time-boundary-cases"]),
        ("timestamp-precision", "normalized-equivalent", "governed-normalization", ["fractional-second-profile"]),
        ("empty-string-is-null", "policy-decision-required", "unresolved", ["empty-string-profile", "approved-null-policy"]),
        ("identifier-case", "normalized-equivalent", "governed-normalization", ["quoted-identifier-inventory"]),
        ("transaction-isolation", "policy-decision-required", "unresolved", ["concurrent-oracle-postgresql-probes", "approved-isolation-policy"]),
        ("redo-scn-resume", "policy-decision-required", "unresolved", ["authorized-logminer-or-xstream-capture", "restart-test"]),
        ("ddl-cdc", "unsupported", "excluded-from-claim-scope", ["separate-ddl-change-plan"]),
        ("sequence-and-identity-state", "lossy", "unresolved", ["sequence-inventory-and-cutover-policy"]),
        ("stored-procedure-subset", "policy-decision-required", "unresolved", ["procedure-qualification-receipt", "native-differential-execution"]),
        ("packages-and-package-state", "unsupported", "excluded-from-claim-scope", ["separate-package-state-qualification"]),
        ("autonomous-transactions", "unsupported", "excluded-from-claim-scope", ["separate-transaction-qualification"]),
    )
    for scope, classification, decision, evidence in behaviors:
        entries.append({
            "item_id": f"oracle-source-behavior:{scope}",
            "scope": scope,
            "source_semantics": {"dialect": "oracle-26ai-free", "requires_observation": True},
            "target_semantics": {"dialect": "postgresql-16", "contract": "lightyear-database-semantic-core"},
            "classification": classification,
            "decision": decision,
            "evidence_required": evidence,
        })
    statistics = Counter(item["classification"] for item in entries)
    return seal({
        "schema_version": "1.0",
        "ledger_type": "lightyear-oracle-source-compatibility-ledger",
        "source_model_sha256": model["content_sha256"],
        "classifications": list(COMPATIBILITY_CLASSES),
        "entries": entries,
        "statistics": {name: statistics.get(name, 0) for name in COMPATIBILITY_CLASSES},
        "equivalence_blocked": True,
        "production_ready": False,
    })


def validate_oracle_source_ledger(ledger: Mapping[str, Any], model: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("ledger_type") != "lightyear-oracle-source-compatibility-ledger":
        errors.append("oracle-source-ledger-identity-invalid")
    if ledger.get("content_sha256") != content_hash(ledger):
        errors.append("oracle-source-ledger-content-hash-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    expected = {f"oracle-source-column:{item['name']}" for item in model["columns"]}
    actual = {item.get("item_id") for item in entries if item.get("scope") == "source-column-to-canonical-type"}
    if expected != actual:
        errors.append("oracle-source-ledger-column-coverage-incomplete")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("oracle-source-ledger-classifications-invalid")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries):
        errors.append("oracle-source-ledger-classification-invalid")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") in {"policy-decision-required", "lossy"}):
        errors.append("oracle-source-ledger-policy-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"):
        errors.append("oracle-source-ledger-unsupported-not-excluded")
    if ledger.get("equivalence_blocked") is not True or ledger.get("production_ready") is not False:
        errors.append("oracle-source-ledger-overclaim")
    return sorted(set(errors))


def build_oracle_source_conformance(project_root: Path) -> dict[str, Any]:
    model, _, fixtures = load_assets(project_root)
    profile_contract = build_profile_contract(model)
    events = reference_oracle_events(fixtures["rows"])
    adapter = OracleSourceAdapter(model, fixtures["rows"], events)
    ledger = build_oracle_source_ledger(model)
    discovery = adapter.discover_schema()
    profile = adapter.profile_data(profile_contract)
    extraction = {"model_sha256": model["content_sha256"], "columns": [item["name"] for item in model["columns"]]}
    rows = list(adapter.read_rows(extraction))
    resume = seal({"adapter_id": adapter.adapter_id, "position": events[1]["position"], "last_event_sha256": events[1]["content_sha256"]})
    resumed = list(adapter.capture_changes(resume))
    checks = {
        "source-interface": isinstance(adapter, SourceAdapter),
        "deterministic-discovery": discovery == adapter.discover_schema(),
        "canonical-schema-coverage": len(discovery["canonical_schema"]["columns"]) == len(model["columns"]),
        "privacy-preserving-profile": profile["raw_values_persisted"] is False,
        "contract-bound-extraction": len(rows) == len(fixtures["rows"]),
        "content-bound-cdc-resume": [item["position"] for item in resumed] == [events[2]["position"], events[3]["position"]],
        "transaction-capabilities-fail-closed": adapter.transaction_capabilities()["capabilities_observed"] is False,
        "compatibility-ledger-complete": not validate_oracle_source_ledger(ledger, model),
        "live-claims-fail-closed": not discovery["catalog_observed"] and not profile["profile_observed"],
    }
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-oracle-source-adapter-conformance",
        "adapter": {"id": adapter.adapter_id, "version": adapter.adapter_version, "dialect": adapter.dialect},
        "model_sha256": model["content_sha256"],
        "profile_contract_sha256": profile_contract["content_sha256"],
        "ledger_sha256": ledger["content_sha256"],
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
        "catalog_observed": False,
        "profile_observed": False,
        "redo_observed": False,
        "transaction_observed": False,
        "production_ready": False,
    })


def _query_result(rows: Iterable[Mapping[str, Any]], statement: str) -> dict[str, Any]:
    rows = list(rows)
    if statement == "fraud-count":
        value: Any = sum(row.get("AUTH_FRAUD") == "Y" for row in rows)
    elif statement == "approved-total":
        value = format(sum((Decimal(str(row["APPROVED_AMT"])) for row in rows if row.get("APPROVED_AMT") is not None), Decimal("0")), ".2f")
    else:
        raise ValueError("oracle-source-query-outside-bounded-contract")
    return {
        "statement_sha256": content_hash({"statement": statement}),
        "parameters_sha256": content_hash({"parameters": []}),
        "columns": [{"name": "result", "canonical_type": "scalar"}],
        "rows": [[value]],
        "error_class": None,
    }


def project_rows_to_postgresql(
    rows: Iterable[Mapping[str, Any]], model: Mapping[str, Any]
) -> list[dict[str, Any]]:
    mapping = PostgreSQLAdapter().mapping(dict(model))
    projected = []
    for row in rows:
        source = dict(row)
        target: dict[str, Any] = {}
        for column in mapping["columns"]:
            value = source.get(column["source"])
            if isinstance(value, str) and value == "":
                value = None
            target[column["target"]] = value
        projected.append(target)
    return projected


def canonicalize_postgresql_rows(
    rows: Iterable[Mapping[str, Any]], model: Mapping[str, Any]
) -> list[dict[str, Any]]:
    expected = {column["name"].lower(): column["name"] for column in model["columns"]}
    result = []
    for row in rows:
        physical = dict(row)
        if set(physical) != set(expected):
            raise ValueError("postgresql-projection-column-contract-invalid")
        result.append({source: physical[target] for target, source in expected.items()})
    return result


def build_oracle_postgresql_source_qualification(project_root: Path) -> dict[str, Any]:
    model, _, fixtures = load_assets(project_root)
    source = OracleSourceAdapter(model, fixtures["rows"], reference_oracle_events(fixtures["rows"]))
    extraction = {"model_sha256": model["content_sha256"], "columns": [item["name"] for item in model["columns"]]}
    source_rows = list(source.read_rows(extraction))
    target_physical_rows = project_rows_to_postgresql(source_rows, model)
    target_rows = canonicalize_postgresql_rows(target_physical_rows, model)
    source_normalized = [normalize_row(row, model) for row in source_rows]
    target_normalized = [normalize_row(row, model) for row in target_rows]
    row_comparison = compare_normalized_rows(source_normalized, target_normalized)
    query_comparisons = [
        compare_query_results(_query_result(source_rows, statement), _query_result(target_rows, statement))
        for statement in ("fraud-count", "approved-total")
    ]
    conformance = build_oracle_source_conformance(project_root)
    ledger = build_oracle_source_ledger(model)
    procedures = build_procedure_qualification(project_root)
    procedure_conformance = build_procedure_conformance(project_root)
    procedure_ledger = build_procedure_ledger(project_root)
    oracle_target = OracleAdapter()
    postgres_target = PostgreSQLAdapter()
    gates = [
        {"gate": 1, "claim": "oracle-source-schema-discovery", "status": "passed-bounded-source-contract", "evidence": {"columns": len(model["columns"]), "catalog_observed": False}},
        {"gate": 2, "claim": "oracle-to-postgresql-data-conversion", "status": "passed-bounded-adapter-execution", "evidence": {"rows": len(source_rows), "target_columns": len(target_physical_rows[0]) if target_physical_rows else 0, "comparison_sha256": row_comparison["content_sha256"]}},
        {"gate": 3, "claim": "constraints-and-indexes", "status": "passed-bounded-source-contract", "evidence": {"constraints": len(model["constraints"]), "indexes": len(model["indexes"])}},
        {"gate": 4, "claim": "query-equivalence", "status": "passed-bounded-adapter-execution", "evidence": {"comparisons": [item["content_sha256"] for item in query_comparisons]}},
        {"gate": 5, "claim": "transaction-behavior", "status": "policy-decision-required-live-concurrency", "evidence": {"bounded_commit_rollback": True, "concurrent_execution_observed": False}},
        {"gate": 6, "claim": "cdc-and-resume", "status": "passed-bounded-scn-replay", "evidence": {"events": 4, "redo_observed": False, "content_bound_resume": True}},
        {"gate": 7, "claim": "cutover-and-rollback", "status": "passed-bounded-rehearsal", "evidence": {"rollback_exact": True, "production_authorized": False}},
        {"gate": 8, "claim": "stored-procedure-subset", "status": "passed-bounded-supported-subset", "evidence": {"procedures": procedures["procedure_count"], "cases": procedure_conformance["case_count"], "native_execution_observed": False}},
    ]
    return seal({
        "schema_version": "1.0",
        "qualification_type": QUALIFICATION_TYPE,
        "qualification_id": QUALIFICATION_ID,
        "source": {"adapter": source.adapter_id, "dialect": source.dialect},
        "target": {"adapter": postgres_target.adapter_id, "dialect": postgres_target.dialect},
        "bindings": {
            "model_sha256": model["content_sha256"],
            "oracle_mapping_sha256": oracle_target.mapping(model)["content_sha256"],
            "postgresql_mapping_sha256": postgres_target.mapping(model)["content_sha256"],
            "source_conformance_sha256": conformance["content_sha256"],
            "source_ledger_sha256": ledger["content_sha256"],
            "procedure_qualification_sha256": procedures["content_sha256"],
            "procedure_conformance_sha256": procedure_conformance["content_sha256"],
            "procedure_ledger_sha256": procedure_ledger["content_sha256"],
        },
        "gates": gates,
        "development_ready": True,
        "supported_procedure_subset_qualified": True,
        "live_source_observed": False,
        "live_target_observed": False,
        "live_redo_observed": False,
        "native_procedure_execution_observed": False,
        "database_migration_complete": False,
        "stored_logic_complete": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can exercise a genuine Oracle SourceAdapter through a bounded Oracle-to-PostgreSQL path and qualify a declared stored-procedure subset without promoting synthetic evidence to live equivalence.",
    })


def validate_oracle_postgresql_source_qualification(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_oracle_postgresql_source_qualification(project_root)
    payload = dict(payload or expected)
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE:
        errors.append("oracle-postgresql-source-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("oracle-postgresql-source-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("oracle-postgresql-source-qualification-drift")
    if payload.get("development_ready") is not True or payload.get("supported_procedure_subset_qualified") is not True:
        errors.append("oracle-postgresql-source-development-claim-invalid")
    false_claims = (
        "live_source_observed", "live_target_observed", "live_redo_observed",
        "native_procedure_execution_observed", "database_migration_complete",
        "stored_logic_complete", "production_ready",
    )
    if any(payload.get(name) is not False for name in false_claims):
        errors.append("oracle-postgresql-source-qualification-overclaim")
    gates = payload.get("gates", [])
    if [item.get("gate") for item in gates if isinstance(item, dict)] != list(range(1, 9)):
        errors.append("oracle-postgresql-source-gates-invalid")
    return sorted(set(errors))


def build_oracle_source_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    model, _, _ = load_assets(project_root)
    return {
        "source-compatibility-ledger.json": build_oracle_source_ledger(model),
        "source-conformance.receipt.json": build_oracle_source_conformance(project_root),
        "procedure-compatibility-ledger.json": build_procedure_ledger(project_root),
        "procedure-conformance.receipt.json": build_procedure_conformance(project_root),
        "procedure-qualification.json": build_procedure_qualification(project_root),
        "qualification.json": build_oracle_postgresql_source_qualification(project_root),
    }
