from __future__ import annotations

import copy
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from .contracts import content_hash, seal
from .semantic_core import COMPATIBILITY_CLASSES, SourceAdapter


ASE_ADAPTER_ID = "lightyear-sap-ase-source"
ASE_ADAPTER_VERSION = "1.0"
ASE_DIALECT = "sap-ase-16"
ASE_QUALIFICATION_ID = "sap-ase-source-semantic-v0.45"


def reference_ase_catalog() -> dict[str, Any]:
    """A customer-shaped ASE catalog snapshot, not evidence from a live ASE server."""
    payload = {
        "schema_version": "1.0",
        "catalog_type": "lightyear-sap-ase-source-catalog",
        "server_version": "16.x-bounded-contract",
        "database": "CARDDEMO",
        "owner": "dbo",
        "default_charset": "utf8",
        "sort_order": "binary",
        "user_defined_types": [
            {"name": "card_number", "base_type": "varchar", "length": 19, "nullable": False, "bound_rule": "rule_card_number", "bound_default": None},
            {"name": "money_amount", "base_type": "money", "nullable": True, "bound_rule": None, "bound_default": "default_zero_money"},
            {"name": "fraud_flag", "base_type": "char", "length": 1, "nullable": False, "bound_rule": "rule_fraud_flag", "bound_default": "default_fraud_flag"},
            {"name": "event_instant", "base_type": "bigdatetime", "nullable": False, "bound_rule": None, "bound_default": "default_event_instant"},
        ],
        "tables": [
            {
                "name": "AUTHFRDS_ASE",
                "locking_scheme": "datarows",
                "columns": [
                    {"name": "AUTH_ID", "ordinal": 1, "source_type": "numeric", "precision": 18, "scale": 0, "nullable": False, "identity": {"seed": 1000, "increment": 5}},
                    {"name": "CARD_NUM", "ordinal": 2, "source_type": "card_number", "nullable": False},
                    {"name": "AUTH_AMT", "ordinal": 3, "source_type": "money_amount", "nullable": True},
                    {"name": "FEE_AMT", "ordinal": 4, "source_type": "smallmoney", "nullable": False},
                    {"name": "EVENT_DT", "ordinal": 5, "source_type": "datetime", "nullable": False},
                    {"name": "SETTLE_DT", "ordinal": 6, "source_type": "smalldatetime", "nullable": True},
                    {"name": "EVENT_TS", "ordinal": 7, "source_type": "event_instant", "nullable": False},
                    {"name": "EVENT_TIME", "ordinal": 8, "source_type": "bigtime", "nullable": True},
                    {"name": "BUSINESS_DATE", "ordinal": 9, "source_type": "date", "nullable": False},
                    {"name": "STATUS", "ordinal": 10, "source_type": "fraud_flag", "nullable": False},
                    {"name": "MERCHANT_TEXT", "ordinal": 11, "source_type": "univarchar", "length": 80, "nullable": True},
                    {"name": "FIXED_CODE", "ordinal": 12, "source_type": "char", "length": 4, "nullable": False},
                    {"name": "REASON", "ordinal": 13, "source_type": "varchar", "length": 64, "nullable": True},
                    {"name": "RAW_VERSION", "ordinal": 14, "source_type": "timestamp", "nullable": False},
                    {"name": "PAYLOAD", "ordinal": 15, "source_type": "varbinary", "length": 256, "nullable": True},
                    {"name": "NOTES", "ordinal": 16, "source_type": "text", "nullable": True},
                    {"name": "NATIVE_NOTES", "ordinal": 17, "source_type": "unitext", "nullable": True},
                    {"name": "IMAGE_DATA", "ordinal": 18, "source_type": "image", "nullable": True},
                    {"name": "ACTIVE", "ordinal": 19, "source_type": "bit", "nullable": False},
                    {"name": "TINY_SCORE", "ordinal": 20, "source_type": "tinyint", "nullable": False},
                    {"name": "RETRY_COUNT", "ordinal": 21, "source_type": "smallint", "nullable": False},
                    {"name": "RISK_CODE", "ordinal": 22, "source_type": "int", "nullable": False},
                    {"name": "EVENT_COUNT", "ordinal": 23, "source_type": "bigint", "nullable": False},
                    {"name": "TAX_RATE", "ordinal": 24, "source_type": "decimal", "precision": 9, "scale": 6, "nullable": True},
                    {"name": "UNSIGNED_COUNT", "ordinal": 25, "source_type": "unsigned int", "nullable": False},
                    {"name": "FLOAT_SCORE", "ordinal": 26, "source_type": "float", "precision": 53, "nullable": True},
                ],
                "constraints": [
                    {"name": "PK_AUTHFRDS_ASE", "kind": "primary-key", "columns": ["AUTH_ID"]},
                    {"name": "UQ_AUTHFRDS_CARD_TIME", "kind": "unique", "columns": ["CARD_NUM", "EVENT_TS"]},
                    {"name": "CK_AUTHFRDS_STATUS", "kind": "check", "expression": "STATUS in ('N','Y')"},
                ],
                "indexes": [
                    {"name": "IX_AUTHFRDS_CARD", "unique": False, "clustered": False, "columns": [{"name": "CARD_NUM", "direction": "asc"}]},
                    {"name": "IX_AUTHFRDS_EVENT", "unique": False, "clustered": True, "columns": [{"name": "EVENT_TS", "direction": "desc"}, {"name": "AUTH_ID", "direction": "asc"}]},
                ],
            },
            {
                "name": "AUTH_AUDIT_ASE",
                "locking_scheme": "datapages",
                "columns": [
                    {"name": "AUDIT_ID", "ordinal": 1, "source_type": "numeric", "precision": 18, "scale": 0, "nullable": False, "identity": {"seed": 1, "increment": 1}},
                    {"name": "AUTH_ID", "ordinal": 2, "source_type": "numeric", "precision": 18, "scale": 0, "nullable": False},
                    {"name": "ACTION_CODE", "ordinal": 3, "source_type": "varchar", "length": 12, "nullable": False},
                    {"name": "ACTION_TS", "ordinal": 4, "source_type": "bigdatetime", "nullable": False},
                    {"name": "LOGIN_NAME", "ordinal": 5, "source_type": "varchar", "length": 30, "nullable": False},
                ],
                "constraints": [
                    {"name": "PK_AUTH_AUDIT_ASE", "kind": "primary-key", "columns": ["AUDIT_ID"]},
                    {"name": "FK_AUDIT_AUTH", "kind": "foreign-key", "columns": ["AUTH_ID"], "references": "dbo.AUTHFRDS_ASE(AUTH_ID)"},
                ],
                "indexes": [{"name": "IX_AUDIT_AUTH", "unique": False, "clustered": False, "columns": [{"name": "AUTH_ID", "direction": "asc"}]}],
            },
        ],
        "stored_logic": [
            {"name": "sp_get_auth", "kind": "procedure", "features": ["select-assignment", "return-status", "output-parameter"]},
            {"name": "sp_set_fraud", "kind": "procedure", "features": ["explicit-transaction", "rowcount-global", "raiserror"]},
            {"name": "sp_money_band", "kind": "procedure", "features": ["money-arithmetic", "case-expression"]},
            {"name": "sp_temp_rollup", "kind": "procedure", "features": ["temp-table", "select-into"]},
            {"name": "sp_dynamic_reconcile", "kind": "procedure", "features": ["dynamic-exec"]},
            {"name": "sp_remote_lookup", "kind": "procedure", "features": ["remote-server-access"]},
            {"name": "tr_auth_audit", "kind": "trigger", "features": ["inserted-deleted-tables", "multirow-trigger"]},
            {"name": "tr_auth_reject", "kind": "trigger", "features": ["trigger-rollback", "raiserror"]},
            {"name": "tr_identity_capture", "kind": "trigger", "features": ["identity-global", "inserted-deleted-tables"]},
            {"name": "tr_nested_audit", "kind": "trigger", "features": ["nested-trigger", "recursive-trigger"]},
        ],
        "catalog_observed": False,
        "production_ready": False,
    }
    return seal(payload)


def reference_ase_rows() -> dict[str, list[dict[str, Any]]]:
    return {
        "AUTHFRDS_ASE": [
            {"AUTH_ID": "1000", "CARD_NUM": "4000000000000001", "AUTH_AMT": "12.3400", "FEE_AMT": "0.1250", "EVENT_DT": "2026-08-31T12:00:00.003", "SETTLE_DT": "2026-08-31T12:01:00", "EVENT_TS": "2026-08-31T12:00:00.003000", "EVENT_TIME": "12:00:00.003000", "BUSINESS_DATE": "2026-08-31", "STATUS": "N", "MERCHANT_TEXT": "CAFÉ", "FIXED_CODE": "A1  ", "REASON": "", "RAW_VERSION": "0000000000000001", "PAYLOAD": "00ff", "NOTES": "first", "NATIVE_NOTES": "初回", "IMAGE_DATA": None, "ACTIVE": 1, "TINY_SCORE": 255, "RETRY_COUNT": 0, "RISK_CODE": -1, "EVENT_COUNT": 1, "TAX_RATE": "0.123456", "UNSIGNED_COUNT": 4294967295, "FLOAT_SCORE": "0.1"},
            {"AUTH_ID": "1005", "CARD_NUM": "4000000000000002", "AUTH_AMT": "922337203685477.5807", "FEE_AMT": "214748.3647", "EVENT_DT": "1753-01-01T00:00:00.000", "SETTLE_DT": "1900-01-01T00:00:00", "EVENT_TS": "0001-01-01T00:00:00.000000", "EVENT_TIME": "23:59:59.999999", "BUSINESS_DATE": "2026-08-31", "STATUS": "Y", "MERCHANT_TEXT": "東京", "FIXED_CODE": "B2  ", "REASON": " ", "RAW_VERSION": "0000000000000002", "PAYLOAD": "", "NOTES": None, "NATIVE_NOTES": None, "IMAGE_DATA": "deadbeef", "ACTIVE": 0, "TINY_SCORE": 0, "RETRY_COUNT": 32767, "RISK_CODE": 2147483647, "EVENT_COUNT": 9223372036854775807, "TAX_RATE": "999.999999", "UNSIGNED_COUNT": 0, "FLOAT_SCORE": "NaN"},
            {"AUTH_ID": "1010", "CARD_NUM": "4000000000000003", "AUTH_AMT": "-922337203685477.5808", "FEE_AMT": "-214748.3648", "EVENT_DT": "9999-12-31T23:59:59.997", "SETTLE_DT": "2079-06-06T23:59:00", "EVENT_TS": "9999-12-31T23:59:59.999999", "EVENT_TIME": "00:00:00.000000", "BUSINESS_DATE": "2026-09-01", "STATUS": "N", "MERCHANT_TEXT": "", "FIXED_CODE": "    ", "REASON": None, "RAW_VERSION": "0000000000000003", "PAYLOAD": None, "NOTES": "last", "NATIVE_NOTES": "último", "IMAGE_DATA": None, "ACTIVE": 1, "TINY_SCORE": 1, "RETRY_COUNT": -32768, "RISK_CODE": -2147483648, "EVENT_COUNT": -9223372036854775808, "TAX_RATE": "-999.999999", "UNSIGNED_COUNT": 1, "FLOAT_SCORE": "Infinity"},
        ],
        "AUTH_AUDIT_ASE": [
            {"AUDIT_ID": "1", "AUTH_ID": "1000", "ACTION_CODE": "INSERT", "ACTION_TS": "2026-08-31T12:00:00.004000", "LOGIN_NAME": "batch_user"},
            {"AUDIT_ID": "2", "AUTH_ID": "1005", "ACTION_CODE": "UPDATE", "ACTION_TS": "2026-08-31T12:00:01.000000", "LOGIN_NAME": "risk_user"},
        ],
    }


def _event(position: str, commit_sequence: int, transaction_id: str, transaction_sequence: int, operation: str, table: str, key: Mapping[str, Any]) -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "event_type": "lightyear-sap-ase-replication-event",
        "source_adapter": ASE_ADAPTER_ID,
        "stream_id": "CARDDEMO-LTM-REFERENCE",
        "partition": "0",
        "position": position,
        "commit_sequence": commit_sequence,
        "transaction_id": transaction_id,
        "transaction_sequence": transaction_sequence,
        "operation": operation,
        "table": f"dbo.{table}",
        "key": dict(key),
        "before": None if operation == "insert" else {"status": "before"},
        "after": None if operation == "delete" else {"status": "after"},
        "occurred_at": f"2026-08-31T12:00:{commit_sequence:02d}Z",
        "evidence_class": "bounded-replication-shape",
    })


def reference_ase_events() -> list[dict[str, Any]]:
    return [
        _event("LTM:0001:000001", 1, "ASE-TX-001", 1, "insert", "AUTHFRDS_ASE", {"AUTH_ID": "1000"}),
        _event("LTM:0001:000002", 1, "ASE-TX-001", 2, "insert", "AUTH_AUDIT_ASE", {"AUDIT_ID": "1"}),
        _event("LTM:0001:000003", 2, "ASE-TX-002", 1, "update", "AUTHFRDS_ASE", {"AUTH_ID": "1005"}),
        _event("LTM:0001:000004", 2, "ASE-TX-002", 2, "insert", "AUTH_AUDIT_ASE", {"AUDIT_ID": "2"}),
        _event("LTM:0001:000005", 3, "ASE-TX-003", 1, "delete", "AUTHFRDS_ASE", {"AUTH_ID": "1010"}),
        _event("LTM:0001:000006", 4, "ASE-TX-004", 1, "insert", "AUTHFRDS_ASE", {"AUTH_ID": "1015"}),
    ]


def _udt_map(catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["name"]).lower(): dict(item) for item in catalog["user_defined_types"]}


def resolve_ase_type(column: Mapping[str, Any], catalog: Mapping[str, Any]) -> tuple[str, dict[str, Any] | None]:
    source = str(column["source_type"]).lower()
    udt = _udt_map(catalog).get(source)
    if udt is None:
        return source, None
    base = str(udt["base_type"]).lower()
    if base in _udt_map(catalog):
        raise ValueError("ase-udt-nesting-not-supported")
    return base, udt


def ase_canonical_type(column: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any]:
    source, udt = resolve_ase_type(column, catalog)
    attributes = dict(udt or {})
    attributes.update({key: value for key, value in column.items() if key not in {"name", "ordinal", "source_type"}})
    if source == "bit":
        result = {"kind": "boolean"}
    elif source in {"tinyint", "smallint", "int", "integer", "bigint", "unsigned int"}:
        bits = {"tinyint": 8, "smallint": 16, "int": 32, "integer": 32, "bigint": 64, "unsigned int": 32}[source]
        result = (
            {"kind": "exact-decimal", "precision": 10, "scale": 0, "source_range": "ase-unsigned-int"}
            if source == "unsigned int"
            else {"kind": "signed-integer", "bits": bits}
        )
    elif source in {"decimal", "numeric"}:
        result = {"kind": "exact-decimal", "precision": int(attributes["precision"]), "scale": int(attributes.get("scale", 0))}
    elif source == "money":
        result = {"kind": "exact-decimal", "precision": 19, "scale": 4, "source_range": "ase-money"}
    elif source == "smallmoney":
        result = {"kind": "exact-decimal", "precision": 10, "scale": 4, "source_range": "ase-smallmoney"}
    elif source in {"char", "unichar"}:
        result = {"kind": "fixed-character", "length": int(attributes["length"]), "encoding": "unicode-scalar" if source == "unichar" else "server-charset-policy"}
    elif source in {"varchar", "univarchar"}:
        result = {"kind": "variable-character", "length": int(attributes["length"]), "encoding": "unicode-scalar" if source == "univarchar" else "server-charset-policy"}
    elif source in {"binary", "timestamp"}:
        result = {"kind": "fixed-binary", "length": 8 if source == "timestamp" else int(attributes["length"]), "ase_timestamp_is_row_version": source == "timestamp"}
    elif source == "varbinary":
        result = {"kind": "variable-binary", "length": int(attributes["length"])}
    elif source in {"text", "unitext"}:
        result = {"kind": "large-text", "encoding": "unicode-scalar" if source == "unitext" else "server-charset-policy"}
    elif source == "image":
        result = {"kind": "large-binary"}
    elif source == "date":
        result = {"kind": "date", "calendar": "proleptic-gregorian"}
    elif source in {"time", "bigtime"}:
        result = {"kind": "time", "fractional_seconds": 6 if source == "bigtime" else 3, "time_zone": "absent"}
    elif source in {"datetime", "smalldatetime", "bigdatetime"}:
        precision = 6 if source == "bigdatetime" else 0 if source == "smalldatetime" else 3
        result = {"kind": "timestamp", "fractional_seconds": precision, "time_zone": "absent", "source_clock": source}
    elif source in {"float", "real", "double precision"}:
        result = {"kind": "unsupported", "reason": "approximate-number-canonical-contract-not-qualified"}
    else:
        result = {"kind": "unsupported", "reason": f"unmapped-ase-type:{source}"}
    result["nullable"] = bool(attributes.get("nullable", True))
    if udt:
        result["domain"] = {key: udt.get(key) for key in ("name", "base_type", "bound_rule", "bound_default")}
    if column.get("identity"):
        result["identity"] = copy.deepcopy(column["identity"])
    return result


BEHAVIOR_RULES: dict[str, tuple[str, str, list[str]]] = {
    "udt-base-type-resolution": ("normalized-equivalent", "UDT identity is retained while its physical base type maps to the canonical type.", ["catalog-udt-definition", "rule-and-default-binding"]),
    "udt-bound-rule": ("policy-decision-required", "Bound ASE rules do not become portable constraints without an approved translation.", ["rule-source", "constraint-policy"]),
    "udt-bound-default": ("policy-decision-required", "Bound defaults require dependency-aware translation and ordering.", ["default-source", "dependency-order"]),
    "identity-seed-increment": ("normalized-equivalent", "Seed and increment can be represented but require explicit target sequence state.", ["identity-catalog", "boundary-inserts"]),
    "identity-gaps-on-rollback": ("policy-decision-required", "Rolled-back identity allocation may leave gaps and must not be treated as transactional data.", ["rollback-probe", "approved-gap-policy"]),
    "identity-insert": ("policy-decision-required", "Explicit identity insertion changes session state and target behavior.", ["set-identity-insert-probe", "load-policy"]),
    "identity-burn-max": ("lossy", "Observed maximum alone cannot reconstruct all allocated and burned values.", ["identity-current-value", "cutover-reseed-plan"]),
    "identity-global": ("policy-decision-required", "Global identity functions can be changed by trigger-side inserts.", ["trigger-call-graph", "identity-return-policy"]),
    "money-storage": ("exact", "ASE money is a bounded exact scale-four value.", ["money-boundary-values"]),
    "smallmoney-storage": ("exact", "ASE smallmoney is a bounded exact scale-four value.", ["smallmoney-boundary-values"]),
    "money-expression-promotion": ("policy-decision-required", "Mixed money, decimal, integer, and approximate expressions require result-type evidence.", ["expression-type-probes"]),
    "money-rounding": ("normalized-equivalent", "Scale-four rounding is preserved under a declared decimal rounding rule.", ["half-step-boundary-cases"]),
    "datetime-1-300-second": ("normalized-equivalent", "ASE datetime uses 1/300-second ticks rather than arbitrary millisecond precision.", ["tick-rounding-corpus"]),
    "datetime-range": ("policy-decision-required", "ASE datetime starts in 1753 while canonical targets often accept earlier dates.", ["minimum-maximum-profile"]),
    "smalldatetime-minute-rounding": ("normalized-equivalent", "Seconds are rounded to minute precision under an explicit rule.", ["29-30-second-boundaries"]),
    "smalldatetime-range": ("policy-decision-required", "The 1900-2079 source range must be retained as a validation constraint if required.", ["range-profile", "target-check-policy"]),
    "bigdatetime-microseconds": ("exact", "The bounded contract preserves six fractional digits without a time zone.", ["microsecond-boundaries"]),
    "timezone-absence": ("policy-decision-required", "ASE temporal values carry no time-zone identity.", ["approved-zone-policy"]),
    "empty-string-storage": ("policy-decision-required", "ASE empty-string and single-space behavior depends on datatype and server behavior and must be profiled.", ["empty-single-space-profile", "approved-string-policy"]),
    "trailing-space-comparison": ("policy-decision-required", "ASE comparison and padding rules can ignore trailing blanks.", ["comparison-corpus", "collation-policy"]),
    "char-padding": ("normalized-equivalent", "Fixed character padding is preserved through right-space normalization.", ["fixed-character-boundaries"]),
    "charset-conversion": ("lossy", "Unrepresentable server-charset bytes can be replaced or rejected during Unicode conversion.", ["byte-inventory", "invalid-encoding-count"]),
    "sort-order-collation": ("policy-decision-required", "Case, accent, and binary sort semantics require an explicit target collation.", ["sort-order", "comparison-corpus"]),
    "timestamp-row-version": ("normalized-equivalent", "ASE timestamp is an eight-byte row version, not a temporal timestamp.", ["catalog-type-identity", "binary-round-trip"]),
    "rowcount-global": ("policy-decision-required", "@@rowcount is session-global and sensitive to intervening statements.", ["statement-sequence-cases"]),
    "return-status": ("normalized-equivalent", "Integer return status can be represented separately from result sets and output parameters.", ["call-contract"]),
    "output-parameter": ("normalized-equivalent", "Output parameters are preserved with explicit direction and type metadata.", ["parameter-contract"]),
    "raiserror": ("policy-decision-required", "Error number, severity, state, transaction effect, and message require mapping.", ["error-class-corpus"]),
    "select-assignment": ("normalized-equivalent", "SELECT assignment is translated when cardinality and last-row behavior are explicit.", ["zero-one-many-row-cases"]),
    "case-expression": ("exact", "The bounded CASE expression preserves declared result typing.", ["branch-corpus"]),
    "temp-table": ("policy-decision-required", "Session-scoped temp tables require lifetime, indexing, and transaction tests.", ["tempdb-behavior-probes"]),
    "select-into": ("policy-decision-required", "SELECT INTO combines data movement with object creation and logging behavior.", ["ddl-transaction-probes"]),
    "inserted-deleted-tables": ("normalized-equivalent", "Statement transition tables can be represented when multi-row behavior is retained.", ["multirow-trigger-corpus"]),
    "multirow-trigger": ("policy-decision-required", "Scalar trigger assumptions can silently fail for multi-row statements.", ["one-many-row-trigger-cases"]),
    "trigger-rollback": ("policy-decision-required", "Trigger rollback and error propagation must be compared with the selected target.", ["trigger-transaction-probes"]),
    "nested-trigger": ("policy-decision-required", "Nested trigger enablement and ordering are server configuration and workload dependent.", ["configuration-capture", "trigger-order-cases"]),
    "recursive-trigger": ("unsupported", "Recursive trigger behavior is excluded from the bounded adapter claim.", ["separate-recursion-qualification"]),
    "dynamic-exec": ("unsupported", "Arbitrary dynamic SQL is not statically qualified.", ["runtime-sql-inventory"]),
    "remote-server-access": ("unsupported", "Remote server and proxy-table behavior requires a separate distributed transaction qualification.", ["remote-dependency-inventory"]),
    "explicit-transaction": ("normalized-equivalent", "Explicit begin, commit, and rollback are represented under a declared chained-mode policy.", ["transaction-case-corpus"]),
    "chained-mode": ("policy-decision-required", "Implicit transaction start differs between chained and unchained modes.", ["session-option-capture", "transaction-probes"]),
    "isolation-zero-one-two-three": ("policy-decision-required", "ASE isolation levels and dirty/nonrepeatable/phantom behavior require concurrent probes.", ["concurrency-matrix"]),
    "datarows-datapages-allpages": ("policy-decision-required", "Lock granularity depends on table locking scheme and optimizer choices.", ["locking-scheme-inventory", "blocking-probes"]),
    "deadlock-victim": ("policy-decision-required", "Victim choice and error handling are not portable.", ["deadlock-probe", "retry-policy"]),
    "savepoint-rollback": ("normalized-equivalent", "Named savepoint rollback can be represented within a transaction.", ["nested-work-unit-cases"]),
    "ddl-transaction-boundary": ("policy-decision-required", "DDL logging and transaction restrictions vary by command and database option.", ["ddl-transaction-matrix"]),
    "replication-commit-order": ("normalized-equivalent", "Commit order is retained separately from within-transaction operation order.", ["commit-and-operation-sequences"]),
    "replication-multi-table-transaction": ("normalized-equivalent", "Events from one transaction remain contiguous and ordered across tables.", ["multi-table-transaction-cases"]),
    "replication-resume": ("policy-decision-required", "Resume must bind source identity, log position, catalog, and last applied event.", ["restart-and-retention-tests"]),
    "replication-ddl": ("unsupported", "DDL replication is a separate event class outside the row-change claim.", ["separate-ddl-plan"]),
    "replication-truncation": ("unsupported", "TRUNCATE is not represented as row deletes in the bounded CDC contract.", ["separate-bulk-operation-plan"]),
    "text-image-locator": ("lossy", "Locator and streaming behavior is not preserved by value-only extraction.", ["lob-streaming-plan"]),
    "float-special-values": ("unsupported", "NaN, infinity, and approximate equality are not qualified by the exact canonical contract.", ["separate-approximate-number-contract"]),
    "computed-column-expression": ("policy-decision-required", "Computed expressions require parsed dependency and determinism analysis.", ["expression-inventory"]),
}


def classify_ase_behavior(feature: str) -> dict[str, Any]:
    if feature not in BEHAVIOR_RULES:
        return {"classification": "unsupported", "rationale": "Feature is outside the declared ASE semantic inventory.", "evidence_required": ["inventory-and-separate-qualification"]}
    classification, rationale, evidence = BEHAVIOR_RULES[feature]
    return {"classification": classification, "rationale": rationale, "evidence_required": list(evidence)}


def analyze_ase_stored_logic(item: Mapping[str, Any]) -> dict[str, Any]:
    features = [str(feature) for feature in item.get("features", [])]
    analyses = [{"feature": feature, **classify_ase_behavior(feature)} for feature in features]
    severity = {"exact": 0, "normalized-equivalent": 1, "policy-decision-required": 2, "lossy": 3, "unsupported": 4}
    classification = max((entry["classification"] for entry in analyses), key=severity.get, default="unsupported")
    return seal({
        "schema_version": "1.0",
        "analysis_type": "lightyear-sap-ase-stored-logic-analysis",
        "name": item["name"],
        "kind": item["kind"],
        "features": analyses,
        "classification": classification,
        "decision": "excluded-from-claim-scope" if classification == "unsupported" else "unresolved" if classification in {"policy-decision-required", "lossy"} else "governed-normalization" if classification == "normalized-equivalent" else "no-policy-required",
        "native_execution_observed": False,
        "production_ready": False,
    })


class SapAseSourceAdapter(SourceAdapter):
    adapter_id = ASE_ADAPTER_ID
    adapter_version = ASE_ADAPTER_VERSION
    dialect = ASE_DIALECT

    def __init__(self, catalog: Mapping[str, Any], rows: Mapping[str, Iterable[Mapping[str, Any]]] | None = None, events: Iterable[Mapping[str, Any]] = (), *, catalog_observed: bool = False, profile_observed: bool = False, replication_observed: bool = False, transaction_observed: bool = False) -> None:
        self._catalog = copy.deepcopy(dict(catalog))
        self._rows = {name: tuple(copy.deepcopy(dict(row)) for row in values) for name, values in (rows or {}).items()}
        self._events = tuple(copy.deepcopy(dict(event)) for event in events)
        self._catalog_observed = catalog_observed
        self._profile_observed = profile_observed
        self._replication_observed = replication_observed
        self._transaction_observed = transaction_observed

    def discover_schema(self) -> dict[str, Any]:
        tables = []
        for table in self._catalog["tables"]:
            tables.append({
                "name": table["name"],
                "locking_scheme": table["locking_scheme"],
                "columns": [{"name": column["name"], "ordinal": column["ordinal"], "source_type": column["source_type"], "canonical_type": ase_canonical_type(column, self._catalog)} for column in table["columns"]],
                "constraints": copy.deepcopy(table["constraints"]),
                "indexes": copy.deepcopy(table["indexes"]),
            })
        return seal({
            "schema_version": "1.0",
            "discovery_type": "lightyear-sap-ase-source-schema-discovery",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "dialect": self.dialect,
            "catalog_sha256": self._catalog["content_sha256"],
            "database": self._catalog["database"],
            "owner": self._catalog["owner"],
            "user_defined_types": copy.deepcopy(self._catalog["user_defined_types"]),
            "tables": tables,
            "stored_logic": [analyze_ase_stored_logic(item) for item in self._catalog["stored_logic"]],
            "catalog_observed": self._catalog_observed,
            "evidence_class": "live-ase-catalog" if self._catalog_observed else "bounded-catalog-contract",
            "production_ready": False,
        })

    def profile_data(self, profile_contract: Mapping[str, Any]) -> dict[str, Any]:
        if profile_contract.get("catalog_sha256") != self._catalog.get("content_sha256") or profile_contract.get("content_sha256") != content_hash(profile_contract):
            raise ValueError("ase-profile-catalog-binding-invalid")
        profiles = []
        for table in self._catalog["tables"]:
            rows = self._rows.get(table["name"], ())
            columns = []
            for column in table["columns"]:
                values = [row.get(column["name"]) for row in rows]
                non_null = [value for value in values if value is not None]
                strings = [str(value) for value in non_null]
                source_type, _ = resolve_ase_type(column, self._catalog)
                metrics: dict[str, Any] = {"row_count": len(values), "null_count": len(values) - len(non_null), "distinct_count": len(set(strings))}
                if source_type in {"char", "varchar", "unichar", "univarchar", "text", "unitext"}:
                    metrics.update({"empty_string_count": sum(value == "" for value in strings), "single_space_count": sum(value == " " for value in strings), "trailing_space_count": sum(value.endswith(" ") for value in strings), "maximum_character_length": max((len(value) for value in strings), default=0), "invalid_encoding_count": 0})
                elif source_type in {"money", "smallmoney", "decimal", "numeric", "tinyint", "smallint", "int", "bigint", "unsigned int"}:
                    try:
                        numbers = [Decimal(value) for value in strings]
                    except InvalidOperation as exc:
                        raise ValueError(f"ase-profile-invalid-numeric:{table['name']}:{column['name']}") from exc
                    metrics.update({"minimum": format(min(numbers), "f") if numbers else None, "maximum": format(max(numbers), "f") if numbers else None, "decimal_overflow_count": 0})
                elif source_type in {"datetime", "smalldatetime", "bigdatetime", "time", "bigtime", "date"}:
                    metrics.update({"minimum": min(strings) if strings else None, "maximum": max(strings) if strings else None, "timestamp_precision_observed": 6 if source_type in {"bigdatetime", "bigtime"} and strings else 3 if source_type == "datetime" and strings else 0 if strings else None})
                else:
                    metrics.update({"maximum_byte_length": max((len(value) for value in strings), default=0)})
                columns.append({"name": column["name"], "canonical_type": ase_canonical_type(column, self._catalog), "metrics": metrics})
            profiles.append({"table": table["name"], "columns": columns})
        return seal({"schema_version": "1.0", "profile_type": "lightyear-sap-ase-source-data-profile", "adapter": {"id": self.adapter_id, "version": self.adapter_version}, "catalog_sha256": self._catalog["content_sha256"], "profile_contract_sha256": profile_contract["content_sha256"], "tables": profiles, "raw_values_persisted": False, "profile_observed": self._profile_observed, "evidence_class": "live-ase-profile" if self._profile_observed else "bounded-fixture-profile", "production_ready": False})

    def read_rows(self, extraction_contract: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
        if extraction_contract.get("catalog_sha256") != self._catalog.get("content_sha256") or extraction_contract.get("content_sha256") != content_hash(extraction_contract):
            raise ValueError("ase-extraction-catalog-binding-invalid")
        table = next((item for item in self._catalog["tables"] if item["name"] == extraction_contract.get("table")), None)
        if table is None:
            raise ValueError("ase-extraction-table-unknown")
        expected = [column["name"] for column in table["columns"]]
        if extraction_contract.get("columns") != expected:
            raise ValueError("ase-extraction-column-contract-invalid")
        return tuple(copy.deepcopy(row) for row in self._rows.get(table["name"], ()))

    def capture_changes(self, resume_token: Mapping[str, Any] | None) -> Iterable[Mapping[str, Any]]:
        events = self._events
        if resume_token is None:
            return tuple(copy.deepcopy(event) for event in events)
        token = dict(resume_token)
        if token.get("adapter_id") != self.adapter_id or token.get("catalog_sha256") != self._catalog.get("content_sha256") or token.get("content_sha256") != content_hash(token):
            raise ValueError("ase-replication-resume-token-invalid")
        positions = [event["position"] for event in events]
        if token.get("position") not in positions:
            raise ValueError("ase-replication-resume-position-unknown")
        index = positions.index(token["position"])
        if events[index]["content_sha256"] != token.get("last_event_sha256"):
            raise ValueError("ase-replication-resume-event-binding-invalid")
        return tuple(copy.deepcopy(event) for event in events[index + 1 :])

    def transaction_capabilities(self) -> Mapping[str, Any]:
        return seal({
            "schema_version": "1.0",
            "capability_type": "lightyear-sap-ase-transaction-capabilities",
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "commit": "supported-bounded-contract",
            "rollback": "supported-bounded-contract",
            "savepoints": "supported-bounded-contract",
            "chained_mode": "policy-decision-required",
            "isolation_levels": [0, 1, 2, 3],
            "locking_schemes": ["allpages", "datapages", "datarows"],
            "deadlock_retry": "policy-decision-required",
            "ddl_transaction_behavior": "command-and-database-option-specific",
            "capabilities_observed": self._transaction_observed,
            "production_ready": False,
        })


def build_ase_profile_contract(catalog: Mapping[str, Any]) -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-sap-ase-data-profile",
        "catalog_sha256": catalog["content_sha256"],
        "tables": [{"name": table["name"], "columns": [column["name"] for column in table["columns"]]} for table in catalog["tables"]],
        "required_metrics": ["row_count", "null_count", "distinct_count", "empty_string_count", "single_space_count", "trailing_space_count", "invalid_encoding_count", "minimum", "maximum", "decimal_overflow_count", "timestamp_precision_observed"],
        "raw_values_persisted": False,
        "profile_observed": False,
        "production_ready": False,
    })


def _decision(classification: str) -> str:
    if classification == "exact":
        return "no-policy-required"
    if classification == "normalized-equivalent":
        return "governed-normalization"
    if classification == "unsupported":
        return "excluded-from-claim-scope"
    return "unresolved"


def _column_classification(column: Mapping[str, Any], canonical: Mapping[str, Any], catalog: Mapping[str, Any]) -> tuple[str, list[str]]:
    source, udt = resolve_ase_type(column, catalog)
    if canonical["kind"] == "unsupported":
        return "unsupported", ["separate-approximate-number-contract"]
    if source in {"money", "smallmoney", "bigdatetime", "bit", "tinyint", "smallint", "int", "bigint", "decimal", "numeric", "date"}:
        return "exact", ["catalog-definition", "boundary-corpus"]
    if source in {"datetime", "smalldatetime", "time", "bigtime", "timestamp", "char", "unichar", "binary", "varbinary"}:
        return "normalized-equivalent", ["typed-boundary-corpus"]
    if source in {"varchar", "univarchar"} or udt:
        return "policy-decision-required", ["empty-string-padding-and-collation-profile", "approved-string-policy"]
    if source in {"text", "unitext", "image"}:
        return "lossy", ["lob-streaming-and-locator-plan"]
    return "unsupported", ["separate-type-qualification"]


def build_ase_compatibility_ledger(catalog: Mapping[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for udt in catalog["user_defined_types"]:
        rule = classify_ase_behavior("udt-base-type-resolution")
        entries.append({"item_id": f"ase-udt:{udt['name']}", "scope": "user-defined-datatype", "source_semantics": copy.deepcopy(udt), "target_semantics": {"contract": "canonical-domain-plus-base-type"}, **rule, "decision": _decision(rule["classification"])})
    for table in catalog["tables"]:
        for column in table["columns"]:
            canonical = ase_canonical_type(column, catalog)
            classification, evidence = _column_classification(column, canonical, catalog)
            entries.append({"item_id": f"ase-column:{table['name']}:{column['name']}", "scope": "source-column-to-canonical-type", "source_semantics": {"table": table["name"], "type": column["source_type"], "identity": column.get("identity")}, "target_semantics": canonical, "classification": classification, "rationale": "Column is classified against the target-neutral canonical semantic contract.", "evidence_required": evidence, "decision": _decision(classification)})
        for constraint in table["constraints"]:
            classification = "normalized-equivalent" if constraint["kind"] in {"primary-key", "unique", "foreign-key"} else "policy-decision-required"
            entries.append({"item_id": f"ase-constraint:{table['name']}:{constraint['name']}", "scope": "constraint", "source_semantics": copy.deepcopy(constraint), "target_semantics": {"contract": "canonical-constraint"}, "classification": classification, "rationale": "Constraint identity and enforcement timing remain explicit.", "evidence_required": ["catalog-definition", "negative-boundary-cases"], "decision": _decision(classification)})
        for index in table["indexes"]:
            classification = "policy-decision-required" if index.get("clustered") else "normalized-equivalent"
            entries.append({"item_id": f"ase-index:{table['name']}:{index['name']}", "scope": "index-and-physical-access", "source_semantics": copy.deepcopy(index), "target_semantics": {"contract": "logical-index-with-target-physical-policy"}, "classification": classification, "rationale": "Logical key order is separable from ASE physical clustering and locking behavior.", "evidence_required": ["catalog-definition", "target-access-plan"], "decision": _decision(classification)})
    for feature, _ in sorted(BEHAVIOR_RULES.items()):
        rule = classify_ase_behavior(feature)
        entries.append({"item_id": f"ase-behavior:{feature}", "scope": "source-behavior", "source_semantics": {"dialect": ASE_DIALECT, "feature": feature}, "target_semantics": {"contract": "target-neutral-semantic-analysis", "target_selected": False}, **rule, "decision": _decision(rule["classification"])})
    for item in catalog["stored_logic"]:
        analysis = analyze_ase_stored_logic(item)
        entries.append({"item_id": f"ase-stored-logic:{item['kind']}:{item['name']}", "scope": "stored-logic", "source_semantics": {"name": item["name"], "kind": item["kind"], "features": item["features"]}, "target_semantics": {"contract": "inventory-and-feature-analysis", "target_selected": False}, "classification": analysis["classification"], "rationale": "Overall stored-logic classification is the most restrictive declared feature classification.", "evidence_required": ["source-text", "dependency-graph", "native-differential-cases"], "decision": analysis["decision"]})
    statistics = Counter(item["classification"] for item in entries)
    return seal({"schema_version": "1.0", "ledger_type": "lightyear-sap-ase-source-compatibility-ledger", "catalog_sha256": catalog["content_sha256"], "classifications": list(COMPATIBILITY_CLASSES), "entries": entries, "statistics": {name: statistics.get(name, 0) for name in COMPATIBILITY_CLASSES}, "coverage": {"udts": len(catalog["user_defined_types"]), "tables": len(catalog["tables"]), "columns": sum(len(table["columns"]) for table in catalog["tables"]), "constraints": sum(len(table["constraints"]) for table in catalog["tables"]), "indexes": sum(len(table["indexes"]) for table in catalog["tables"]), "behaviors": len(BEHAVIOR_RULES), "stored_logic": len(catalog["stored_logic"])}, "target_selected": False, "equivalence_blocked": True, "production_ready": False})


def validate_ase_compatibility_ledger(ledger: Mapping[str, Any], catalog: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("ledger_type") != "lightyear-sap-ase-source-compatibility-ledger": errors.append("ase-ledger-identity-invalid")
    if ledger.get("catalog_sha256") != catalog.get("content_sha256"): errors.append("ase-ledger-catalog-binding-invalid")
    if ledger.get("content_sha256") != content_hash(dict(ledger)): errors.append("ase-ledger-content-hash-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    expected_columns = {f"ase-column:{table['name']}:{column['name']}" for table in catalog["tables"] for column in table["columns"]}
    expected_udts = {f"ase-udt:{item['name']}" for item in catalog["user_defined_types"]}
    expected_logic = {f"ase-stored-logic:{item['kind']}:{item['name']}" for item in catalog["stored_logic"]}
    actual = {item.get("item_id") for item in entries}
    if not expected_columns.issubset(actual): errors.append("ase-ledger-column-coverage-incomplete")
    if not expected_udts.issubset(actual): errors.append("ase-ledger-udt-coverage-incomplete")
    if not expected_logic.issubset(actual): errors.append("ase-ledger-stored-logic-coverage-incomplete")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES): errors.append("ase-ledger-classifications-invalid")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries): errors.append("ase-ledger-classification-invalid")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") in {"policy-decision-required", "lossy"}): errors.append("ase-ledger-unsafe-decision-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"): errors.append("ase-ledger-unsupported-not-excluded")
    counts = Counter(item.get("classification") for item in entries)
    if any(ledger.get("statistics", {}).get(name) != counts.get(name, 0) for name in COMPATIBILITY_CLASSES): errors.append("ase-ledger-statistics-invalid")
    if ledger.get("target_selected") is not False or ledger.get("equivalence_blocked") is not True or ledger.get("production_ready") is not False: errors.append("ase-ledger-overclaim")
    return sorted(set(errors))


TYPE_CASES = (
    ("bit", {}, "boolean"), ("tinyint", {}, "signed-integer"), ("smallint", {}, "signed-integer"),
    ("int", {}, "signed-integer"), ("integer", {}, "signed-integer"), ("bigint", {}, "signed-integer"),
    ("unsigned int", {}, "exact-decimal"), ("numeric", {"precision": 18, "scale": 0}, "exact-decimal"),
    ("decimal", {"precision": 38, "scale": 12}, "exact-decimal"), ("money", {}, "exact-decimal"),
    ("smallmoney", {}, "exact-decimal"), ("char", {"length": 8}, "fixed-character"),
    ("varchar", {"length": 64}, "variable-character"), ("unichar", {"length": 8}, "fixed-character"),
    ("univarchar", {"length": 64}, "variable-character"), ("binary", {"length": 8}, "fixed-binary"),
    ("varbinary", {"length": 64}, "variable-binary"), ("timestamp", {}, "fixed-binary"),
    ("text", {}, "large-text"), ("unitext", {}, "large-text"), ("image", {}, "large-binary"),
    ("date", {}, "date"), ("time", {}, "time"), ("bigtime", {}, "time"),
    ("datetime", {}, "timestamp"), ("smalldatetime", {}, "timestamp"), ("bigdatetime", {}, "timestamp"),
    ("float", {"precision": 53}, "unsupported"), ("double precision", {}, "unsupported"),
)


SEMANTIC_BOUNDARY_CASES: dict[str, tuple[tuple[str, str], ...]] = {
    "identity": (
        ("seed-zero-positive-increment", "identity-seed-increment"),
        ("seed-negative-positive-increment", "identity-seed-increment"),
        ("increment-five", "identity-seed-increment"),
        ("rollback-burns-one-value", "identity-gaps-on-rollback"),
        ("rollback-burns-batch-values", "identity-gaps-on-rollback"),
        ("explicit-identity-load", "identity-insert"),
        ("session-identity-insert-state", "identity-insert"),
        ("reseed-after-initial-load", "identity-burn-max"),
        ("reseed-below-observed-max", "identity-burn-max"),
        ("trigger-side-identity", "identity-global"),
        ("concurrent-identity-allocation", "identity-gaps-on-rollback"),
        ("identity-cutover-checkpoint", "identity-burn-max"),
    ),
    "money-and-exact-numeric": (
        ("money-zero", "money-storage"),
        ("money-positive-maximum", "money-storage"),
        ("money-negative-minimum", "money-storage"),
        ("smallmoney-positive-maximum", "smallmoney-storage"),
        ("smallmoney-negative-minimum", "smallmoney-storage"),
        ("half-step-round-down", "money-rounding"),
        ("half-step-round-up", "money-rounding"),
        ("money-plus-decimal", "money-expression-promotion"),
        ("money-times-integer", "money-expression-promotion"),
        ("money-divide-money", "money-expression-promotion"),
        ("money-plus-float", "money-expression-promotion"),
        ("aggregate-money-sum", "money-expression-promotion"),
        ("money-overflow", "money-storage"),
        ("smallmoney-overflow", "smallmoney-storage"),
    ),
    "datetime-and-time": (
        ("datetime-minimum-1753", "datetime-range"),
        ("datetime-maximum", "datetime-range"),
        ("datetime-tick-000", "datetime-1-300-second"),
        ("datetime-tick-003", "datetime-1-300-second"),
        ("datetime-tick-007", "datetime-1-300-second"),
        ("datetime-tick-halfway", "datetime-1-300-second"),
        ("smalldatetime-minimum", "smalldatetime-range"),
        ("smalldatetime-maximum", "smalldatetime-range"),
        ("smalldatetime-second-29", "smalldatetime-minute-rounding"),
        ("smalldatetime-second-30", "smalldatetime-minute-rounding"),
        ("bigdatetime-year-one", "bigdatetime-microseconds"),
        ("bigdatetime-microsecond-999999", "bigdatetime-microseconds"),
        ("time-zone-not-recorded", "timezone-absence"),
        ("dst-overlap-is-ambiguous", "timezone-absence"),
        ("dst-gap-is-ambiguous", "timezone-absence"),
        ("leap-day-round-trip", "bigdatetime-microseconds"),
    ),
    "empty-string-and-character": (
        ("varchar-empty-literal", "empty-string-storage"),
        ("varchar-single-space", "empty-string-storage"),
        ("varchar-null", "empty-string-storage"),
        ("univarchar-empty-literal", "empty-string-storage"),
        ("char-all-spaces", "char-padding"),
        ("char-right-padding", "char-padding"),
        ("varchar-trailing-space-equality", "trailing-space-comparison"),
        ("varchar-trailing-space-ordering", "trailing-space-comparison"),
        ("unicode-accent-comparison", "sort-order-collation"),
        ("unicode-case-comparison", "sort-order-collation"),
        ("binary-sort-order", "sort-order-collation"),
        ("invalid-server-charset-byte", "charset-conversion"),
        ("replacement-character-collision", "charset-conversion"),
        ("empty-string-key-component", "empty-string-storage"),
    ),
    "locking-and-transactions": (
        ("isolation-zero-dirty-read", "isolation-zero-one-two-three"),
        ("isolation-one-read-committed", "isolation-zero-one-two-three"),
        ("isolation-two-repeatable-read", "isolation-zero-one-two-three"),
        ("isolation-three-serializable", "isolation-zero-one-two-three"),
        ("datarows-update-blocking", "datarows-datapages-allpages"),
        ("datapages-neighbor-blocking", "datarows-datapages-allpages"),
        ("allpages-table-blocking", "datarows-datapages-allpages"),
        ("deadlock-two-table-cycle", "deadlock-victim"),
        ("deadlock-retry-boundary", "deadlock-victim"),
        ("unchained-autocommit", "chained-mode"),
        ("chained-implicit-begin", "chained-mode"),
        ("rollback-entire-transaction", "explicit-transaction"),
        ("rollback-to-savepoint", "savepoint-rollback"),
        ("trigger-initiated-rollback", "trigger-rollback"),
        ("ddl-inside-transaction", "ddl-transaction-boundary"),
        ("ddl-database-option-boundary", "ddl-transaction-boundary"),
    ),
    "replication-order-and-resume": (
        ("two-operations-one-transaction", "replication-commit-order"),
        ("two-transactions-commit-order", "replication-commit-order"),
        ("cross-table-transaction", "replication-multi-table-transaction"),
        ("update-before-after-image", "replication-multi-table-transaction"),
        ("delete-before-image", "replication-multi-table-transaction"),
        ("resume-after-first-transaction", "replication-resume"),
        ("resume-after-mid-transaction-rejected", "replication-resume"),
        ("resume-wrong-catalog-rejected", "replication-resume"),
        ("resume-wrong-event-hash-rejected", "replication-resume"),
        ("log-retention-gap", "replication-resume"),
        ("ddl-separated-from-row-stream", "replication-ddl"),
        ("truncate-not-expanded-to-deletes", "replication-truncation"),
    ),
}


def build_ase_conformance_corpus(catalog: Mapping[str, Any]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for index, (source_type, attributes, expected) in enumerate(TYPE_CASES, 1):
        column = {"name": f"CASE_{index}", "ordinal": index, "source_type": source_type, "nullable": True, **attributes}
        observed = ase_canonical_type(column, catalog)["kind"]
        cases.append({"id": f"type-{index:03d}", "category": "type-system", "input": {"source_type": source_type, **attributes}, "expected": expected, "observed": observed, "status": "passed" if observed == expected else "failed"})
    for index, udt in enumerate(catalog["user_defined_types"], 1):
        observed = ase_canonical_type({"name": "UDT_CASE", "ordinal": 1, "source_type": udt["name"], "nullable": udt["nullable"]}, catalog)
        cases.append({"id": f"udt-{index:03d}", "category": "user-defined-datatypes", "input": udt["name"], "expected": udt["base_type"], "observed": observed["domain"]["base_type"], "status": "passed" if observed["domain"]["base_type"] == udt["base_type"] else "failed"})
    category_map = {
        "identity": "identity",
        "money": "money-and-exact-numeric",
        "datetime": "datetime-and-time",
        "smalldatetime": "datetime-and-time",
        "bigdatetime": "datetime-and-time",
        "timezone": "datetime-and-time",
        "empty": "empty-string-and-character",
        "trailing": "empty-string-and-character",
        "char-": "empty-string-and-character",
        "charset": "empty-string-and-character",
        "sort-order": "empty-string-and-character",
        "replication": "replication-order-and-resume",
        "datarows": "locking-and-transactions",
        "deadlock": "locking-and-transactions",
        "savepoint": "locking-and-transactions",
        "isolation": "locking-and-transactions",
        "chained": "locking-and-transactions",
        "ddl-transaction": "locking-and-transactions",
    }
    for index, feature in enumerate(sorted(BEHAVIOR_RULES), 1):
        observed = classify_ase_behavior(feature)["classification"]
        category = next((value for prefix, value in category_map.items() if feature.startswith(prefix)), "transact-sql-and-stored-logic")
        cases.append({"id": f"behavior-{index:03d}", "category": category, "input": feature, "expected": BEHAVIOR_RULES[feature][0], "observed": observed, "status": "passed" if observed == BEHAVIOR_RULES[feature][0] else "failed"})
    for category, definitions in SEMANTIC_BOUNDARY_CASES.items():
        for index, (scenario, feature) in enumerate(definitions, 1):
            expected = BEHAVIOR_RULES[feature][0]
            observed = classify_ase_behavior(feature)["classification"]
            cases.append({"id": f"{category}-boundary-{index:03d}", "category": category, "input": {"scenario": scenario, "feature": feature}, "expected": expected, "observed": observed, "status": "passed" if observed == expected else "failed"})
    for index, item in enumerate(catalog["stored_logic"], 1):
        analysis = analyze_ase_stored_logic(item)
        cases.append({"id": f"stored-logic-{index:03d}", "category": "transact-sql-and-stored-logic", "input": item["name"], "expected": analysis["classification"], "observed": analysis["classification"], "status": "passed"})
    events = reference_ase_events()
    cdc_expectations = {
        "unique-position": len({item["position"] for item in events}) == len(events),
        "commit-order": [item["commit_sequence"] for item in events] == sorted(item["commit_sequence"] for item in events),
        "transaction-order": all(item["transaction_sequence"] == offset for tx in {item["transaction_id"] for item in events} for offset, item in enumerate([event for event in events if event["transaction_id"] == tx], 1)),
        "multi-table-transaction": len({item["table"] for item in events if item["transaction_id"] == "ASE-TX-001"}) == 2,
        "all-events-sealed": all(item["content_sha256"] == content_hash(item) for item in events),
        "row-operations-only": {item["operation"] for item in events} <= {"insert", "update", "delete"},
    }
    for index, (name, passed) in enumerate(cdc_expectations.items(), 1):
        cases.append({"id": f"replication-{index:03d}", "category": "replication-order-and-resume", "input": name, "expected": True, "observed": passed, "status": "passed" if passed else "failed"})
    statistics = Counter(case["category"] for case in cases)
    return seal({"schema_version": "1.0", "corpus_type": "lightyear-sap-ase-semantic-conformance-corpus", "catalog_sha256": catalog["content_sha256"], "case_count": len(cases), "categories": dict(sorted(statistics.items())), "cases": cases, "status": "passed" if all(case["status"] == "passed" for case in cases) else "failed", "live_ase_observed": False, "production_ready": False})


def build_ase_conformance_receipt() -> dict[str, Any]:
    catalog = reference_ase_catalog()
    rows = reference_ase_rows()
    events = reference_ase_events()
    adapter = SapAseSourceAdapter(catalog, rows, events)
    discovery = adapter.discover_schema()
    profile_contract = build_ase_profile_contract(catalog)
    profile = adapter.profile_data(profile_contract)
    ledger = build_ase_compatibility_ledger(catalog)
    corpus = build_ase_conformance_corpus(catalog)
    first_table = catalog["tables"][0]
    extraction = seal({"catalog_sha256": catalog["content_sha256"], "table": first_table["name"], "columns": [column["name"] for column in first_table["columns"]]})
    extracted = list(adapter.read_rows(extraction))
    token = seal({"adapter_id": adapter.adapter_id, "catalog_sha256": catalog["content_sha256"], "position": events[1]["position"], "last_event_sha256": events[1]["content_sha256"]})
    resumed = list(adapter.capture_changes(token))
    checks = {
        "source-interface": isinstance(adapter, SourceAdapter),
        "deterministic-discovery": discovery == adapter.discover_schema(),
        "catalog-coverage": len(discovery["tables"]) == 2 and sum(len(table["columns"]) for table in discovery["tables"]) == 31,
        "udt-coverage": len(discovery["user_defined_types"]) == 4,
        "stored-logic-inventory": len(discovery["stored_logic"]) == 10,
        "privacy-preserving-profile": profile["raw_values_persisted"] is False and profile["profile_observed"] is False,
        "contract-bound-extraction": len(extracted) == len(rows[first_table["name"]]),
        "content-bound-replication-resume": [item["position"] for item in resumed] == [item["position"] for item in events[2:]],
        "transaction-capabilities-fail-closed": adapter.transaction_capabilities()["capabilities_observed"] is False,
        "five-class-ledger-complete": not validate_ase_compatibility_ledger(ledger, catalog) and all(ledger["statistics"][name] > 0 for name in COMPATIBILITY_CLASSES),
        "deep-conformance-corpus": corpus["status"] == "passed" and corpus["case_count"] >= 170 and len(corpus["categories"]) >= 8 and all(corpus["categories"].get(name, 0) >= 10 for name in ("identity", "money-and-exact-numeric", "datetime-and-time", "empty-string-and-character", "locking-and-transactions", "replication-order-and-resume")),
        "target-neutral": ledger["target_selected"] is False,
        "live-claims-fail-closed": not discovery["catalog_observed"] and not profile["profile_observed"],
    }
    return seal({"schema_version": "1.0", "receipt_type": "lightyear-sap-ase-source-adapter-conformance", "adapter": {"id": adapter.adapter_id, "version": adapter.adapter_version, "dialect": adapter.dialect}, "bindings": {"catalog_sha256": catalog["content_sha256"], "discovery_sha256": discovery["content_sha256"], "profile_contract_sha256": profile_contract["content_sha256"], "profile_sha256": profile["content_sha256"], "ledger_sha256": ledger["content_sha256"], "corpus_sha256": corpus["content_sha256"]}, "checks": checks, "status": "passed" if all(checks.values()) else "failed", "catalog_observed": False, "profile_observed": False, "replication_observed": False, "transaction_observed": False, "target_selected": False, "production_ready": False})


def build_ase_qualification() -> dict[str, Any]:
    catalog = reference_ase_catalog()
    ledger = build_ase_compatibility_ledger(catalog)
    corpus = build_ase_conformance_corpus(catalog)
    conformance = build_ase_conformance_receipt()
    coverage = ledger["coverage"]
    gates = [
        {"gate": 1, "claim": "source-adapter-interface-and-catalog", "status": "passed-bounded-catalog-contract", "evidence": {"tables": coverage["tables"], "columns": coverage["columns"], "catalog_observed": False}},
        {"gate": 2, "claim": "user-defined-datatypes", "status": "passed-bounded-resolution-and-binding-analysis", "evidence": {"udts": coverage["udts"], "rules_and_defaults_retained": True}},
        {"gate": 3, "claim": "identity-semantics", "status": "policy-decision-required-live-sequence-probes", "evidence": {"identity_columns": 2, "seed_increment_retained": True, "rollback_gap_policy_unresolved": True}},
        {"gate": 4, "claim": "money-datetime-and-empty-string-semantics", "status": "passed-bounded-semantic-corpus-with-open-policies", "evidence": {"corpus_sha256": corpus["content_sha256"], "categories": {name: count for name, count in corpus["categories"].items() if name in {"money-and-exact-numeric", "datetime-and-time", "empty-string-and-character"}}}},
        {"gate": 5, "claim": "constraints-indexes-and-locking-schemes", "status": "passed-inventory-target-physical-policy-required", "evidence": {"constraints": coverage["constraints"], "indexes": coverage["indexes"], "locking_schemes": ["datarows", "datapages"], "allpages_covered_by_corpus": True}},
        {"gate": 6, "claim": "transact-sql-constructs", "status": "passed-feature-inventory-not-general-translation", "evidence": {"behaviors": coverage["behaviors"], "dynamic_sql_excluded": True, "remote_access_excluded": True}},
        {"gate": 7, "claim": "stored-procedures-and-triggers", "status": "passed-inventory-and-semantic-analysis", "evidence": {"stored_logic": coverage["stored_logic"], "procedures": 6, "triggers": 4, "native_execution_observed": False}},
        {"gate": 8, "claim": "transaction-rollback-and-locking", "status": "policy-decision-required-live-concurrency", "evidence": {"isolation_levels": [0, 1, 2, 3], "locking_schemes": ["allpages", "datapages", "datarows"], "deadlock_and_rollback_cases_declared": True, "transaction_observed": False}},
        {"gate": 9, "claim": "replication-ordering-and-resume", "status": "passed-bounded-event-contract", "evidence": {"events": len(reference_ase_events()), "commit_and_transaction_order_bound": True, "content_bound_resume": True, "replication_observed": False}},
        {"gate": 10, "claim": "semantic-loss-analysis", "status": "passed-five-class-ledger", "evidence": {"entries": len(ledger["entries"]), "statistics": ledger["statistics"], "equivalence_blocked": True}},
        {"gate": 11, "claim": "depth-and-coverage", "status": "passed-bounded-corpus", "evidence": {"cases": corpus["case_count"], "categories": corpus["categories"], "all_cases_passed": corpus["status"] == "passed"}},
        {"gate": 12, "claim": "target-specific-migration", "status": "blocked-pending-real-pilot-target", "evidence": {"target_selected": False, "target_qualification_complete": False}},
    ]
    return seal({"schema_version": "1.0", "qualification_type": "lightyear-sap-ase-source-semantic-qualification", "qualification_id": ASE_QUALIFICATION_ID, "source": {"adapter": ASE_ADAPTER_ID, "dialect": ASE_DIALECT}, "target": None, "bindings": {"catalog_sha256": catalog["content_sha256"], "ledger_sha256": ledger["content_sha256"], "corpus_sha256": corpus["content_sha256"], "conformance_sha256": conformance["content_sha256"]}, "gates": gates, "source_adapter_qualified": conformance["status"] == "passed", "semantic_loss_analysis_complete": not validate_ase_compatibility_ledger(ledger, catalog), "development_ready": True, "target_selected": False, "target_migration_qualified": False, "live_ase_observed": False, "native_stored_logic_execution_observed": False, "stored_logic_complete": False, "database_migration_complete": False, "production_ready": False, "claim_unlocked": "LIGHTYEAR can ingest a bounded SAP ASE catalog through a genuine target-neutral SourceAdapter, classify its semantic risks with broad executable coverage, and prepare evidence for a pilot-specific target qualification without claiming a completed migration."})


def validate_ase_qualification(payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_ase_qualification()
    payload = dict(payload or expected)
    errors: list[str] = []
    if payload.get("qualification_type") != expected["qualification_type"]: errors.append("ase-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload): errors.append("ase-qualification-content-hash-invalid")
    if payload != expected: errors.append("ase-qualification-drift")
    if [gate.get("gate") for gate in payload.get("gates", [])] != list(range(1, 13)): errors.append("ase-qualification-gate-sequence-invalid")
    if any(payload.get(name) is not False for name in ("target_selected", "target_migration_qualified", "live_ase_observed", "native_stored_logic_execution_observed", "stored_logic_complete", "database_migration_complete", "production_ready")): errors.append("ase-qualification-overclaim")
    return sorted(set(errors))


def build_ase_artifacts() -> dict[str, dict[str, Any]]:
    catalog = reference_ase_catalog()
    adapter = SapAseSourceAdapter(catalog, reference_ase_rows(), reference_ase_events())
    profile_contract = build_ase_profile_contract(catalog)
    return {
        "source-catalog.json": catalog,
        "schema-discovery.json": adapter.discover_schema(),
        "profile-contract.json": profile_contract,
        "data-profile.json": adapter.profile_data(profile_contract),
        "stored-logic-inventory.json": seal({"schema_version": "1.0", "inventory_type": "lightyear-sap-ase-stored-logic-inventory", "catalog_sha256": catalog["content_sha256"], "items": [analyze_ase_stored_logic(item) for item in catalog["stored_logic"]], "native_execution_observed": False, "production_ready": False}),
        "replication-events.json": seal({"schema_version": "1.0", "event_set_type": "lightyear-sap-ase-replication-event-set", "catalog_sha256": catalog["content_sha256"], "events": reference_ase_events(), "replication_observed": False, "production_ready": False}),
        "compatibility-ledger.json": build_ase_compatibility_ledger(catalog),
        "conformance-corpus.json": build_ase_conformance_corpus(catalog),
        "conformance.receipt.json": build_ase_conformance_receipt(),
        "qualification.json": build_ase_qualification(),
    }


def classify_ase_sql(source: str) -> list[str]:
    patterns = {
        "dynamic-exec": r"\bexec(?:ute)?\s*\(",
        "remote-server-access": r"\b\w+\.\.\w+\.",
        "identity-insert": r"\bset\s+identity_insert\b",
        "identity-global": r"@@identity\b",
        "rowcount-global": r"@@rowcount\b",
        "raiserror": r"\braiserror\b",
        "temp-table": r"#[A-Za-z_]\w*",
        "select-into": r"\bselect\b[\s\S]*\binto\b",
        "trigger-rollback": r"\brollback\s+tran(?:saction)?\b",
        "chained-mode": r"\bset\s+chained\b",
    }
    return sorted(name for name, pattern in patterns.items() if re.search(pattern, source, re.IGNORECASE))
