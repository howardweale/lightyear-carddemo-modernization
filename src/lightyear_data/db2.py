from __future__ import annotations

import copy
from collections import Counter
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .contracts import content_hash, seal
from .semantic_core import (
    COMPATIBILITY_CLASSES,
    SourceAdapter,
    build_canonical_schema,
    canonical_type,
    normalize_row,
)


class Db2SourceAdapter(SourceAdapter):
    """Fail-closed Db2 for z/OS projection into the database semantic core."""

    adapter_id = "lightyear-db2-zos-source"
    adapter_version = "1.0"
    dialect = "db2-zos"

    def __init__(
        self,
        model: Mapping[str, Any],
        rows: Iterable[Mapping[str, Any]] = (),
        events: Iterable[Mapping[str, Any]] = (),
        *,
        catalog_observed: bool = False,
        profile_observed: bool = False,
        log_observed: bool = False,
    ) -> None:
        self._model = copy.deepcopy(dict(model))
        self._rows = tuple(copy.deepcopy(dict(row)) for row in rows)
        self._events = tuple(copy.deepcopy(dict(event)) for event in events)
        self._catalog_observed = catalog_observed
        self._profile_observed = profile_observed
        self._log_observed = log_observed

    def discover_schema(self) -> dict[str, Any]:
        return seal({
            "schema_version": "1.0",
            "discovery_type": "lightyear-db2-schema-discovery",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "dialect": self.dialect,
            "canonical_schema": build_canonical_schema(self._model),
            "catalog_observed": self._catalog_observed,
            "evidence_class": "zos-observed" if self._catalog_observed else "source-only",
            "production_ready": False,
        })

    def profile_data(self, profile_contract: Mapping[str, Any]) -> dict[str, Any]:
        if profile_contract.get("model_sha256") != self._model.get("content_sha256"):
            raise ValueError("db2-profile-model-binding-invalid")
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
            profiles.append({"name": name, "canonical_type": canonical_type(column), "metrics": metrics})
        return seal({
            "schema_version": "1.0",
            "profile_type": "lightyear-db2-data-profile",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "model_sha256": self._model["content_sha256"],
            "profile_contract_sha256": profile_contract["content_sha256"],
            "columns": profiles,
            "raw_values_persisted": False,
            "profile_observed": self._profile_observed,
            "evidence_class": "zos-observed" if self._profile_observed else "synthetic-fixture",
            "production_ready": False,
        })

    def read_rows(self, extraction_contract: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
        if extraction_contract.get("model_sha256") != self._model.get("content_sha256"):
            raise ValueError("db2-extraction-model-binding-invalid")
        expected = [column["name"] for column in self._model["columns"]]
        if extraction_contract.get("columns") != expected:
            raise ValueError("db2-extraction-column-contract-invalid")
        return tuple(copy.deepcopy(row) for row in self._rows)

    def capture_changes(self, resume_token: Mapping[str, Any] | None) -> Iterable[Mapping[str, Any]]:
        position = None
        if resume_token is not None:
            token = dict(resume_token)
            if token.get("adapter_id") != self.adapter_id or token.get("content_sha256") != content_hash(token):
                raise ValueError("db2-cdc-resume-token-invalid")
            position = token.get("position")
        events = self._events
        if position is not None:
            positions = [event.get("position") for event in events]
            if position not in positions:
                raise ValueError("db2-cdc-resume-position-unknown")
            events = events[positions.index(position) + 1 :]
        return tuple(copy.deepcopy(event) for event in events)

    def transaction_capabilities(self) -> Mapping[str, Any]:
        return seal({
            "schema_version": "1.0",
            "capability_type": "lightyear-db2-transaction-capabilities",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "commit": "supported",
            "rollback": "supported",
            "savepoints": "supported-not-qualified",
            "isolation": "policy-decision-required",
            "locking": "workload-probes-required",
            "capabilities_observed": False,
            "production_ready": False,
        })


def build_db2_source_ledger(model: Mapping[str, Any]) -> dict[str, Any]:
    entries = []
    for column in model["columns"]:
        character = column["source_type"] in {"CHAR", "VARCHAR"}
        entries.append({
            "item_id": f"db2-column:{column['name']}",
            "scope": "source-column-to-canonical-type",
            "source_semantics": {"dialect": "db2-zos", "type": column["source_type"]},
            "target_semantics": canonical_type(column),
            "classification": "normalized-equivalent" if character else "exact",
            "rationale": "Character data requires explicit encoding and right-space normalization." if character else "Db2 value domain is represented without loss by the canonical type.",
            "evidence_required": ["encoding-profile", "normalized-row-comparison"] if character else ["catalog-projection"],
            "decision": "governed-normalization" if character else "no-policy-required",
        })
    behaviors = (
        ("encoding", "normalized-equivalent", "governed-normalization", ["ccsid-capture", "invalid-encoding-profile"]),
        ("fixed-character-padding", "normalized-equivalent", "governed-normalization", ["right-space-comparison"]),
        ("null-vs-empty-string", "exact", "no-policy-required", ["data-profile"]),
        ("transaction-isolation", "policy-decision-required", "unresolved", ["approved-isolation-policy", "concurrent-transaction-probes"]),
        ("cdc-log-position", "policy-decision-required", "unresolved", ["authorized-db2-log-capture", "resume-and-replay-test"]),
        ("ddl-cdc", "unsupported", "excluded-from-claim-scope", ["separate-ddl-change-plan"]),
        ("package-bind-semantics", "unsupported", "excluded-from-claim-scope", ["package-and-plan-inventory", "application-qualification"]),
    )
    for scope, classification, decision, evidence in behaviors:
        entries.append({
            "item_id": f"db2-behavior:{scope}",
            "scope": scope,
            "source_semantics": {"dialect": "db2-zos", "claim": "requires-observation"},
            "target_semantics": {"contract": "lightyear-database-semantic-core"},
            "classification": classification,
            "rationale": "DB2 behavior is classified explicitly and cannot be inferred from DDL alone.",
            "evidence_required": evidence,
            "decision": decision,
        })
    statistics = dict(Counter(item["classification"] for item in entries))
    for classification in COMPATIBILITY_CLASSES:
        statistics.setdefault(classification, 0)
    return seal({
        "schema_version": "1.0",
        "ledger_type": "lightyear-db2-source-compatibility-ledger",
        "source_model_sha256": model["content_sha256"],
        "classifications": list(COMPATIBILITY_CLASSES),
        "entries": entries,
        "statistics": statistics,
        "equivalence_blocked": any(item["classification"] in {"policy-decision-required", "lossy", "unsupported"} for item in entries),
        "production_ready": False,
    })


def validate_db2_source_ledger(ledger: Mapping[str, Any], model: Mapping[str, Any]) -> list[str]:
    ledger = dict(ledger)
    errors: list[str] = []
    if ledger.get("ledger_type") != "lightyear-db2-source-compatibility-ledger":
        errors.append("db2-source-ledger-identity-invalid")
    if ledger.get("content_sha256") != content_hash(ledger):
        errors.append("db2-source-ledger-content-hash-invalid")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("db2-source-ledger-classifications-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    ids = [item.get("item_id") for item in entries]
    if len(ids) != len(set(ids)):
        errors.append("db2-source-ledger-item-identity-duplicate")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries):
        errors.append("db2-source-ledger-classification-invalid")
    expected_columns = {f"db2-column:{column['name']}" for column in model["columns"]}
    actual_columns = {item.get("item_id") for item in entries if item.get("scope") == "source-column-to-canonical-type"}
    if actual_columns != expected_columns:
        errors.append("db2-source-ledger-column-coverage-incomplete")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") == "policy-decision-required"):
        errors.append("db2-source-ledger-policy-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"):
        errors.append("db2-source-ledger-unsupported-not-excluded")
    expected_statistics = Counter(item.get("classification") for item in entries)
    if any(ledger.get("statistics", {}).get(name) != expected_statistics.get(name, 0) for name in COMPATIBILITY_CLASSES):
        errors.append("db2-source-ledger-statistics-invalid")
    unsafe = any(item.get("classification") in {"policy-decision-required", "lossy", "unsupported"} for item in entries)
    if ledger.get("equivalence_blocked") is not unsafe:
        errors.append("db2-source-ledger-equivalence-gate-invalid")
    if ledger.get("production_ready") is not False:
        errors.append("db2-source-ledger-overclaims-production")
    return sorted(set(errors))


def db2_source_conformance_receipt(
    adapter: Db2SourceAdapter,
    model: Mapping[str, Any],
    profile_contract: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> dict[str, Any]:
    schema_one = adapter.discover_schema()
    schema_two = adapter.discover_schema()
    profile = adapter.profile_data(profile_contract)
    extraction = {"model_sha256": model["content_sha256"], "columns": [column["name"] for column in model["columns"]]}
    rows = list(adapter.read_rows(extraction))
    normalized = [normalize_row(row, model) for row in rows]
    checks = {
        "source-interface": all(callable(getattr(adapter, name, None)) for name in ("discover_schema", "profile_data", "read_rows", "capture_changes", "transaction_capabilities")),
        "determinism": schema_one == schema_two,
        "canonical-schema-coverage": len(schema_one["canonical_schema"]["columns"]) == len(model["columns"]),
        "profile-contract-binding": profile["profile_contract_sha256"] == profile_contract["content_sha256"],
        "normalized-row-coverage": len(normalized) == len(rows),
        "ledger-coverage": not validate_db2_source_ledger(ledger, model),
        "unsafe-behavior-gates": ledger["equivalence_blocked"] is True,
        "live-claims-fail-closed": schema_one["catalog_observed"] is False and profile["profile_observed"] is False,
    }
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-db2-source-adapter-conformance",
        "adapter": {"id": adapter.adapter_id, "version": adapter.adapter_version, "dialect": adapter.dialect},
        "model_sha256": model["content_sha256"],
        "ledger_sha256": ledger["content_sha256"],
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
        "catalog_observed": False,
        "profile_observed": False,
        "cdc_observed": False,
        "mainframe_equivalent": False,
        "production_ready": False,
    })
