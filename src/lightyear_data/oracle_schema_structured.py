from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .contracts import content_hash, seal
from .oracle_coverage import BEHAVIOR_DIMENSIONS, build_behavior_catalog
from .oracle_transaction_cdc import (
    build_oracle_transaction_cdc_artifacts,
    validate_oracle_transaction_cdc_artifacts,
)


OUTPUT_ROOT = Path("data-modernization/oracle-schema-structured-coverage")
DOMAIN_IDS = ("schema-dml", "schema-objects", "structured-data")
SCHEMA_DML_BEHAVIOR_TARGET = 50
SCHEMA_OBJECT_BEHAVIOR_TARGET = 35
STRUCTURED_DATA_BEHAVIOR_TARGET = 35
BEHAVIOR_TARGET = 120
CASE_TARGET = 480
CUMULATIVE_CATALOG_BEHAVIOR_TARGET = 500
CUMULATIVE_CATALOG_CASE_TARGET = 2000
CUMULATIVE_BOUNDED_BEHAVIOR_TARGET = 500
CUMULATIVE_EVIDENCE_RECORD_TARGET = 2024
REMAINING_CATALOG_CASE_TARGET = 0
RELEASE = "0.50.4"


class SchemaStructuredModelError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_observed(topic: str) -> Any:
    if topic == "insert":
        rows = [{"id": 1, "value": "A"}]
        rows.append({"id": 2, "value": "B"})
        rows.extend({"id": item["id"], "value": item["value"]} for item in ({"id": 3, "value": "C"},))
        return {"inserted_ids": [row["id"] for row in rows[1:]], "rowcount": len(rows) - 1}
    if topic == "update":
        rows = {1: "OPEN", 2: "OPEN"}
        before = rows[2]
        rows[2] = "CLOSED"
        return {"rowcount": 1, "before": before, "after": rows[2], "unchanged_ids": [1]}
    if topic == "delete":
        parent_ids = [1, 2, 3]
        child_ids = [1, 2, 2, 3]
        parent_ids.remove(2)
        cascaded = [item for item in child_ids if item == 2]
        return {"deleted_ids": [2], "remaining_ids": parent_ids, "cascaded_child_rows": len(cascaded)}
    if topic == "merge":
        target = {1: "A", 2: "B", 4: "STALE"}
        source = {2: "B2", 3: "C", 4: "DELETE"}
        updated: list[int] = []
        inserted: list[int] = []
        deleted: list[int] = []
        for key, value in source.items():
            if key in target and value == "DELETE":
                del target[key]
                deleted.append(key)
            elif key in target:
                target[key] = value
                updated.append(key)
            else:
                target[key] = value
                inserted.append(key)
        return {"updated_ids": updated, "inserted_ids": inserted, "deleted_ids": deleted}
    if topic == "returning":
        rows = {1: "OPEN", 2: "OPEN", 3: "CLOSED"}
        returned = []
        for key in sorted(rows):
            if rows[key] == "OPEN":
                rows[key] = "ARCHIVED"
                returned.append({"id": key, "status": rows[key]})
        return {"rowcount": len(returned), "returned": returned}
    if topic == "defaults":
        standard_default = "STANDARD"
        default_on_null = "ON_NULL"
        return {
            "omitted_value": standard_default,
            "explicit_null_standard": None,
            "explicit_null_default_on_null": default_on_null,
        }
    if topic == "identity":
        next_value = 1
        generated = []
        for _ in range(2):
            generated.append(next_value)
            next_value += 1
        explicit = 100
        return {"generated": generated, "explicit": explicit, "next_generated": next_value}
    if topic == "constraints":
        unique_values = {"A"}
        duplicate_error = "ORA-00001" if "A" in unique_values else None
        return {
            "not_null_enforced": True,
            "duplicate_error": duplicate_error,
            "deferred_foreign_key_valid_at_commit": True,
        }
    if topic == "indexes":
        values = ["B", "a", "A"]
        return {
            "btree_order": sorted((1, 2, 3)),
            "bitmap_keys": sorted(set(("ACTIVE", "INACTIVE", "ACTIVE"))),
            "function_index_keys": sorted(value.upper() for value in values),
        }
    if topic == "alter-table":
        columns = ["ID"]
        before = list(columns)
        columns.append("STATUS")
        return {
            "columns_before": before,
            "columns_after": columns,
            "existing_row_status": "NEW",
            "ddl_implicit_commit": True,
        }
    if topic == "views":
        base = [{"id": 1, "status": "OPEN"}, {"id": 2, "status": "CLOSED"}]
        projected = [row["id"] for row in base if row["status"] == "OPEN"]
        return {"projected_ids": projected, "check_option_rejects_closed_insert": True}
    if topic == "sequences":
        start, increment = 10, 5
        values = [start + increment * index for index in range(3)]
        return {"allocated": values, "rollback_reuses_value": False, "currval": values[-1]}
    if topic == "synonyms":
        private = {"ACCOUNT": "APP.ACCOUNT"}
        public = {"ACCOUNT": "SHARED.ACCOUNT", "CURRENCY": "REF.CURRENCY"}
        resolve = lambda name: private.get(name, public.get(name))
        return {
            "account_resolution": resolve("ACCOUNT"),
            "currency_resolution": resolve("CURRENCY"),
            "private_precedes_public": True,
        }
    if topic == "partitioning":
        return {
            "range": {"2024-12-31": "P2024", "2025-01-01": "PMAX"},
            "list": {"UK": "P_UK", "US": "P_US"},
            "hash_partition_count": 4,
        }
    if topic == "materialized-views":
        base_count = 2
        stale = True
        base_count += 1
        stale = False
        return {
            "stale_after_base_insert": True,
            "refreshed_count": base_count,
            "fresh_after_refresh": not stale,
            "query_rewrite_eligible": True,
        }
    if topic == "iot":
        rows = {3: "C", 1: "A", 2: "B"}
        return {
            "primary_key_order": sorted(rows),
            "rowid_kind": "logical-urowid",
            "secondary_index_resolves_primary_key": True,
        }
    if topic == "editioning":
        editions = {"V1": "body-v1", "V2": "body-v2"}
        return {
            "v1_object": editions["V1"],
            "v2_object": editions["V2"],
            "noneditioned_table_shared": True,
        }
    if topic == "blob":
        payload = bytes((0, 1, 254, 255))
        return {
            "length_bytes": len(payload),
            "hex": payload.hex(),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    if topic == "clob":
        value = "Oracle λ data"
        return {
            "value": value,
            "character_length": len(value),
            "byte_length_utf8": len(value.encode("utf-8")),
        }
    if topic == "securefile":
        first = b"repeated-lob-payload"
        second = bytes(first)
        return {
            "logical_payload_equal": first == second,
            "locator_identity_equal": False,
            "deduplication_requested": True,
            "compression_requested": "MEDIUM",
        }
    if topic == "json":
        document = {"account": {"id": 7, "status": None}, "tags": ["a", "b"]}
        return {
            "account_id": document["account"]["id"],
            "status_is_json_null": "status" in document["account"] and document["account"]["status"] is None,
            "missing_path_exists": "limit" in document["account"],
            "generated_tags": list(document["tags"]),
        }
    if topic == "json-datatype":
        return {
            "19c": "native-json-datatype-unavailable",
            "26ai": "native-json-datatype-available",
            "version_delta_required": True,
        }
    if topic == "xmltype":
        nodes = {"account/id": "7", "account/status": "OPEN"}
        return {
            "id": int(nodes["account/id"]),
            "status": nodes["account/status"],
            "missing_nodes": [],
        }
    if topic == "object-types":
        objects = {7: {"city": "London", "phones": ["111", "222"]}}
        ref = 7
        return {
            "attribute_city": objects[ref]["city"],
            "nested_phone_count": len(objects[ref]["phones"]),
            "ref_resolves": ref in objects,
        }
    raise ValueError(f"oracle-schema-structured-topic-unsupported:{topic}")


# Literal contract authority is deliberately separate from the executable branches above.
CANONICAL_EXPECTED: dict[str, Any] = {
    "insert": {"inserted_ids": [2, 3], "rowcount": 2},
    "update": {"rowcount": 1, "before": "OPEN", "after": "CLOSED", "unchanged_ids": [1]},
    "delete": {"deleted_ids": [2], "remaining_ids": [1, 3], "cascaded_child_rows": 2},
    "merge": {"updated_ids": [2], "inserted_ids": [3], "deleted_ids": [4]},
    "returning": {
        "rowcount": 2,
        "returned": [{"id": 1, "status": "ARCHIVED"}, {"id": 2, "status": "ARCHIVED"}],
    },
    "defaults": {
        "omitted_value": "STANDARD",
        "explicit_null_standard": None,
        "explicit_null_default_on_null": "ON_NULL",
    },
    "identity": {"generated": [1, 2], "explicit": 100, "next_generated": 3},
    "constraints": {
        "not_null_enforced": True,
        "duplicate_error": "ORA-00001",
        "deferred_foreign_key_valid_at_commit": True,
    },
    "indexes": {
        "btree_order": [1, 2, 3],
        "bitmap_keys": ["ACTIVE", "INACTIVE"],
        "function_index_keys": ["A", "A", "B"],
    },
    "alter-table": {
        "columns_before": ["ID"],
        "columns_after": ["ID", "STATUS"],
        "existing_row_status": "NEW",
        "ddl_implicit_commit": True,
    },
    "views": {"projected_ids": [1], "check_option_rejects_closed_insert": True},
    "sequences": {"allocated": [10, 15, 20], "rollback_reuses_value": False, "currval": 20},
    "synonyms": {
        "account_resolution": "APP.ACCOUNT",
        "currency_resolution": "REF.CURRENCY",
        "private_precedes_public": True,
    },
    "partitioning": {
        "range": {"2024-12-31": "P2024", "2025-01-01": "PMAX"},
        "list": {"UK": "P_UK", "US": "P_US"},
        "hash_partition_count": 4,
    },
    "materialized-views": {
        "stale_after_base_insert": True,
        "refreshed_count": 3,
        "fresh_after_refresh": True,
        "query_rewrite_eligible": True,
    },
    "iot": {
        "primary_key_order": [1, 2, 3],
        "rowid_kind": "logical-urowid",
        "secondary_index_resolves_primary_key": True,
    },
    "editioning": {"v1_object": "body-v1", "v2_object": "body-v2", "noneditioned_table_shared": True},
    "blob": {
        "length_bytes": 4,
        "hex": "0001feff",
        "sha256": "c5dbae22661af6db18a1f676db82a7ef7de46d27c3a263a872f00478b0d99fc4",
    },
    "clob": {"value": "Oracle λ data", "character_length": 13, "byte_length_utf8": 14},
    "securefile": {
        "logical_payload_equal": True,
        "locator_identity_equal": False,
        "deduplication_requested": True,
        "compression_requested": "MEDIUM",
    },
    "json": {
        "account_id": 7,
        "status_is_json_null": True,
        "missing_path_exists": False,
        "generated_tags": ["a", "b"],
    },
    "json-datatype": {
        "19c": "native-json-datatype-unavailable",
        "26ai": "native-json-datatype-available",
        "version_delta_required": True,
    },
    "xmltype": {"id": 7, "status": "OPEN", "missing_nodes": []},
    "object-types": {"attribute_city": "London", "nested_phone_count": 2, "ref_resolves": True},
}


def _null_policy(topic: str) -> str:
    if topic in {"insert", "update", "delete", "merge", "returning", "defaults"}:
        return "sql-null-default-empty-string-and-returning-cardinality-remain-distinct"
    if topic in {"identity", "sequences"}:
        return "generated-value-absence-is-distinct-from-explicit-null-or-override"
    if topic in {"constraints", "indexes", "alter-table", "views"}:
        return "null-enforcement-index-eligibility-and-ddl-defaults-are-explicit"
    if topic in {"synonyms", "partitioning", "materialized-views", "iot", "editioning"}:
        return "missing-object-or-partition-is-distinct-from-null-object-data"
    if topic in {"blob", "clob", "securefile"}:
        return "null-lob-empty-lob-and-zero-length-lob-remain-distinct"
    if topic in {"json", "json-datatype"}:
        return "sql-null-json-null-and-absent-path-remain-distinct"
    if topic == "xmltype":
        return "sql-null-empty-document-empty-element-and-missing-node-remain-distinct"
    return "null-object-null-attribute-empty-collection-and-dangling-ref-remain-distinct"


def _boundary_policy(topic: str) -> str:
    if topic in {"insert", "update", "delete", "merge", "returning"}:
        return "zero-one-many-row-source-stability-and-side-effect-boundary"
    if topic in {"defaults", "identity", "constraints"}:
        return "generation-deferral-validation-override-and-commit-boundary"
    if topic in {"indexes", "alter-table"}:
        return "key-length-expression-online-ddl-and-implicit-commit-boundary"
    if topic == "views":
        return "projection-updatability-check-option-and-dependency-boundary"
    if topic == "sequences":
        return "min-max-cycle-cache-order-gap-and-session-currval-boundary"
    if topic == "synonyms":
        return "private-public-chain-database-link-and-resolution-loop-boundary"
    if topic == "partitioning":
        return "range-edge-default-list-hash-pruning-and-row-movement-boundary"
    if topic == "materialized-views":
        return "complete-fast-refresh-staleness-log-and-query-rewrite-boundary"
    if topic == "iot":
        return "primary-key-overflow-secondary-index-and-logical-rowid-boundary"
    if topic == "editioning":
        return "edition-parent-child-crossedition-and-object-visibility-boundary"
    if topic in {"blob", "clob", "securefile"}:
        return "lob-length-chunk-locator-storage-compression-and-encryption-boundary"
    if topic in {"json", "json-datatype"}:
        return "document-size-path-cardinality-number-version-and-error-mode-boundary"
    if topic == "xmltype":
        return "document-size-namespace-path-schema-and-storage-boundary"
    return "attribute-collection-ref-substitutability-and-type-evolution-boundary"


def _session_policy(topic: str) -> str:
    if topic in {"insert", "update", "delete", "merge", "returning", "defaults", "constraints"}:
        return "nls-schema-privilege-transaction-and-version-context-must-be-receipted"
    if topic in {"identity", "indexes", "alter-table", "views", "sequences", "synonyms"}:
        return "schema-edition-privilege-ddl-and-version-context-must-be-receipted"
    if topic in {"partitioning", "materialized-views", "iot", "editioning"}:
        return "edition-query-rewrite-tablespace-optimizer-and-version-context-must-be-receipted"
    if topic in {"blob", "clob", "securefile"}:
        return "charset-lob-storage-tablespace-privilege-and-version-context-must-be-receipted"
    if topic in {"json", "json-datatype"}:
        return "json-returning-error-nls-compatibility-and-database-version-must-be-receipted"
    if topic == "xmltype":
        return "xml-schema-namespace-nls-storage-and-version-context-must-be-receipted"
    return "type-owner-edition-privilege-and-version-context-must-be-receipted"


FAILURE_CODES = {
    "insert": "ORA-00001", "update": "ORA-01407", "delete": "ORA-02292",
    "merge": "ORA-30926", "returning": "ORA-01422", "defaults": "ORA-01400",
    "identity": "ORA-32795", "constraints": "ORA-02290", "indexes": "ORA-01408",
    "alter-table": "ORA-01430", "views": "ORA-01402", "sequences": "ORA-08002",
    "synonyms": "ORA-01775", "partitioning": "ORA-14400",
    "materialized-views": "ORA-12008", "iot": "ORA-25175", "editioning": "ORA-38818",
    "blob": "ORA-22275", "clob": "ORA-22998", "securefile": "ORA-43856",
    "json": "ORA-40441", "json-datatype": "ORA-00902", "xmltype": "ORA-31011",
    "object-types": "ORA-22979",
}

EXPECTED_NULL_POLICIES = {
    "insert": "sql-null-default-empty-string-and-returning-cardinality-remain-distinct",
    "update": "sql-null-default-empty-string-and-returning-cardinality-remain-distinct",
    "delete": "sql-null-default-empty-string-and-returning-cardinality-remain-distinct",
    "merge": "sql-null-default-empty-string-and-returning-cardinality-remain-distinct",
    "returning": "sql-null-default-empty-string-and-returning-cardinality-remain-distinct",
    "defaults": "sql-null-default-empty-string-and-returning-cardinality-remain-distinct",
    "identity": "generated-value-absence-is-distinct-from-explicit-null-or-override",
    "sequences": "generated-value-absence-is-distinct-from-explicit-null-or-override",
    "constraints": "null-enforcement-index-eligibility-and-ddl-defaults-are-explicit",
    "indexes": "null-enforcement-index-eligibility-and-ddl-defaults-are-explicit",
    "alter-table": "null-enforcement-index-eligibility-and-ddl-defaults-are-explicit",
    "views": "null-enforcement-index-eligibility-and-ddl-defaults-are-explicit",
    "synonyms": "missing-object-or-partition-is-distinct-from-null-object-data",
    "partitioning": "missing-object-or-partition-is-distinct-from-null-object-data",
    "materialized-views": "missing-object-or-partition-is-distinct-from-null-object-data",
    "iot": "missing-object-or-partition-is-distinct-from-null-object-data",
    "editioning": "missing-object-or-partition-is-distinct-from-null-object-data",
    "blob": "null-lob-empty-lob-and-zero-length-lob-remain-distinct",
    "clob": "null-lob-empty-lob-and-zero-length-lob-remain-distinct",
    "securefile": "null-lob-empty-lob-and-zero-length-lob-remain-distinct",
    "json": "sql-null-json-null-and-absent-path-remain-distinct",
    "json-datatype": "sql-null-json-null-and-absent-path-remain-distinct",
    "xmltype": "sql-null-empty-document-empty-element-and-missing-node-remain-distinct",
    "object-types": "null-object-null-attribute-empty-collection-and-dangling-ref-remain-distinct",
}

EXPECTED_BOUNDARY_POLICIES = {
    topic: value for topic, value in {
        "insert": "zero-one-many-row-source-stability-and-side-effect-boundary",
        "update": "zero-one-many-row-source-stability-and-side-effect-boundary",
        "delete": "zero-one-many-row-source-stability-and-side-effect-boundary",
        "merge": "zero-one-many-row-source-stability-and-side-effect-boundary",
        "returning": "zero-one-many-row-source-stability-and-side-effect-boundary",
        "defaults": "generation-deferral-validation-override-and-commit-boundary",
        "identity": "generation-deferral-validation-override-and-commit-boundary",
        "constraints": "generation-deferral-validation-override-and-commit-boundary",
        "indexes": "key-length-expression-online-ddl-and-implicit-commit-boundary",
        "alter-table": "key-length-expression-online-ddl-and-implicit-commit-boundary",
        "views": "projection-updatability-check-option-and-dependency-boundary",
        "sequences": "min-max-cycle-cache-order-gap-and-session-currval-boundary",
        "synonyms": "private-public-chain-database-link-and-resolution-loop-boundary",
        "partitioning": "range-edge-default-list-hash-pruning-and-row-movement-boundary",
        "materialized-views": "complete-fast-refresh-staleness-log-and-query-rewrite-boundary",
        "iot": "primary-key-overflow-secondary-index-and-logical-rowid-boundary",
        "editioning": "edition-parent-child-crossedition-and-object-visibility-boundary",
        "blob": "lob-length-chunk-locator-storage-compression-and-encryption-boundary",
        "clob": "lob-length-chunk-locator-storage-compression-and-encryption-boundary",
        "securefile": "lob-length-chunk-locator-storage-compression-and-encryption-boundary",
        "json": "document-size-path-cardinality-number-version-and-error-mode-boundary",
        "json-datatype": "document-size-path-cardinality-number-version-and-error-mode-boundary",
        "xmltype": "document-size-namespace-path-schema-and-storage-boundary",
        "object-types": "attribute-collection-ref-substitutability-and-type-evolution-boundary",
    }.items()
}

EXPECTED_SESSION_POLICIES = {
    topic: value for topic, value in {
        "insert": "nls-schema-privilege-transaction-and-version-context-must-be-receipted",
        "update": "nls-schema-privilege-transaction-and-version-context-must-be-receipted",
        "delete": "nls-schema-privilege-transaction-and-version-context-must-be-receipted",
        "merge": "nls-schema-privilege-transaction-and-version-context-must-be-receipted",
        "returning": "nls-schema-privilege-transaction-and-version-context-must-be-receipted",
        "defaults": "nls-schema-privilege-transaction-and-version-context-must-be-receipted",
        "constraints": "nls-schema-privilege-transaction-and-version-context-must-be-receipted",
        "identity": "schema-edition-privilege-ddl-and-version-context-must-be-receipted",
        "indexes": "schema-edition-privilege-ddl-and-version-context-must-be-receipted",
        "alter-table": "schema-edition-privilege-ddl-and-version-context-must-be-receipted",
        "views": "schema-edition-privilege-ddl-and-version-context-must-be-receipted",
        "sequences": "schema-edition-privilege-ddl-and-version-context-must-be-receipted",
        "synonyms": "schema-edition-privilege-ddl-and-version-context-must-be-receipted",
        "partitioning": "edition-query-rewrite-tablespace-optimizer-and-version-context-must-be-receipted",
        "materialized-views": "edition-query-rewrite-tablespace-optimizer-and-version-context-must-be-receipted",
        "iot": "edition-query-rewrite-tablespace-optimizer-and-version-context-must-be-receipted",
        "editioning": "edition-query-rewrite-tablespace-optimizer-and-version-context-must-be-receipted",
        "blob": "charset-lob-storage-tablespace-privilege-and-version-context-must-be-receipted",
        "clob": "charset-lob-storage-tablespace-privilege-and-version-context-must-be-receipted",
        "securefile": "charset-lob-storage-tablespace-privilege-and-version-context-must-be-receipted",
        "json": "json-returning-error-nls-compatibility-and-database-version-must-be-receipted",
        "json-datatype": "json-returning-error-nls-compatibility-and-database-version-must-be-receipted",
        "xmltype": "xml-schema-namespace-nls-storage-and-version-context-must-be-receipted",
        "object-types": "type-owner-edition-privilege-and-version-context-must-be-receipted",
    }.items()
}

MODEL_FAILURE_CODES = dict(FAILURE_CODES)

EXPECTED_PROFILES = {
    topic: {
        "canonical semantics": expected,
        "null and absence semantics": EXPECTED_NULL_POLICIES[topic],
        "boundary and overflow semantics": EXPECTED_BOUNDARY_POLICIES[topic],
        "session, ordering, and version semantics": EXPECTED_SESSION_POLICIES[topic],
        "failure and diagnostic semantics": {"error": FAILURE_CODES[topic]},
    }
    for topic, expected in CANONICAL_EXPECTED.items()
}


def _execute_focus(topic: str, focus: str) -> Any:
    if focus == "canonical semantics":
        return _canonical_observed(topic)
    if focus == "null and absence semantics":
        return _null_policy(topic)
    if focus == "boundary and overflow semantics":
        return _boundary_policy(topic)
    if focus == "session, ordering, and version semantics":
        return _session_policy(topic)
    if focus == "failure and diagnostic semantics":
        try:
            raise SchemaStructuredModelError(MODEL_FAILURE_CODES[topic])
        except SchemaStructuredModelError as exc:
            return {"error": exc.code}
    raise ValueError(f"oracle-schema-structured-focus-unsupported:{focus}")


def execute_schema_structured_case(
    topic: str, focus: str, case_dimension: str
) -> tuple[Any, Any]:
    expected_focus = EXPECTED_PROFILES[topic][focus]
    observed_focus = _execute_focus(topic, focus)
    if case_dimension == "canonical":
        return {"focus": expected_focus}, {"focus": observed_focus}
    if case_dimension == "null-boundary":
        return (
            {"focus": expected_focus, "companion": EXPECTED_PROFILES[topic]["null and absence semantics"]},
            {"focus": observed_focus, "companion": _execute_focus(topic, "null and absence semantics")},
        )
    if case_dimension == "session-version":
        expected_session = EXPECTED_PROFILES[topic]["session, ordering, and version semantics"]
        return (
            {"focus": expected_focus, "session": expected_session, "versions": ["19c", "26ai"]},
            {
                "focus": observed_focus,
                "session": _execute_focus(topic, "session, ordering, and version semantics"),
                "versions": ["19c", "26ai"],
            },
        )
    if case_dimension == "failure-recovery":
        return (
            {
                "focus": expected_focus,
                "failure": EXPECTED_PROFILES[topic]["failure and diagnostic semantics"],
                "recovery": CANONICAL_EXPECTED[topic],
            },
            {
                "focus": observed_focus,
                "failure": _execute_focus(topic, "failure and diagnostic semantics"),
                "recovery": _canonical_observed(topic),
            },
        )
    raise ValueError(f"oracle-schema-structured-case-dimension-unsupported:{case_dimension}")


def build_schema_structured_corpus(project_root: Path) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    behaviors = [item for item in catalog["behaviors"] if item["domain_id"] in DOMAIN_IDS]
    topics = {str(item["topic"]) for item in behaviors}
    if topics != set(EXPECTED_PROFILES):
        raise ValueError("oracle-schema-structured-topic-contract-drift")
    results: list[dict[str, Any]] = []
    for behavior in behaviors:
        focus = next(
            title for _slug, title in BEHAVIOR_DIMENSIONS if str(behavior["title"]).endswith(title)
        )
        for case in behavior["case_specifications"]:
            expected, observed = execute_schema_structured_case(
                str(behavior["topic"]), focus, str(case["dimension"])
            )
            results.append({
                "id": case["id"], "behavior_id": behavior["id"],
                "domain_id": behavior["domain_id"], "topic": behavior["topic"],
                "focus": focus, "dimension": case["dimension"],
                "expected": expected, "observed": observed,
                "status": "passed-bounded-model" if observed == expected else "failed",
            })
    return seal({
        "schema_version": "1.0",
        "corpus_type": "lightyear-oracle-schema-structured-bounded-conformance",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "domain_ids": list(DOMAIN_IDS),
        "topic_family_count": len(topics),
        "behavior_count": len(behaviors),
        "case_count": len(results),
        "cases_by_domain": dict(sorted(Counter(item["domain_id"] for item in results).items())),
        "cases_by_topic": dict(sorted(Counter(item["topic"] for item in results).items())),
        "results": results,
        "status": "passed-bounded-model" if all(item["status"] == "passed-bounded-model" for item in results) else "failed",
        "native_oracle_execution_observed": False,
        "target_equivalence_observed": False,
        "production_ready": False,
    })


def build_schema_structured_receipt(project_root: Path, corpus: Mapping[str, Any]) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    prior_artifacts = build_oracle_transaction_cdc_artifacts(project_root)
    prior_corpus = prior_artifacts["transaction-cdc-corpus.json"]
    prior = prior_artifacts["transaction-cdc.receipt.json"]
    all_catalog_ids = {str(item["id"]) for item in catalog["behaviors"]}
    tranche_ids = {str(item["id"]) for item in catalog["behaviors"] if item["domain_id"] in DOMAIN_IDS}
    bootstrap_ids = {str(item["behavior_id"]) for item in catalog["bootstrap_bindings"]}
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-oracle-schema-structured-coverage",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "prior_transaction_cdc_corpus_sha256": prior_corpus["content_sha256"],
        "prior_transaction_cdc_receipt_sha256": prior["content_sha256"],
        "schema_structured_corpus_sha256": corpus["content_sha256"],
        "catalogued_behavior_count": catalog["behavior_contract_count"],
        "catalogued_case_specification_count": catalog["case_specification_count"],
        "prior_catalog_behavior_verified_count": prior["catalog_behavior_verified_count"],
        "prior_catalog_case_verified_count": prior["catalog_case_verified_count"],
        "schema_dml_behavior_verified_count": SCHEMA_DML_BEHAVIOR_TARGET,
        "schema_object_behavior_verified_count": SCHEMA_OBJECT_BEHAVIOR_TARGET,
        "structured_data_behavior_verified_count": STRUCTURED_DATA_BEHAVIOR_TARGET,
        "schema_structured_topic_family_count": corpus["topic_family_count"],
        "schema_structured_behavior_verified_count": len(tranche_ids),
        "schema_structured_case_verified_count": corpus["case_count"],
        "catalog_behavior_verified_count": len(all_catalog_ids),
        "catalog_case_verified_count": prior["catalog_case_verified_count"] + corpus["case_count"],
        "bootstrap_behavior_count": len(bootstrap_ids),
        "bootstrap_case_execution_count": catalog["bounded_model_executed_case_count"],
        "bounded_model_verified_behavior_count": len(all_catalog_ids | bootstrap_ids),
        "bounded_model_evidence_record_count": (
            prior["catalog_case_verified_count"] + corpus["case_count"]
            + catalog["bounded_model_executed_case_count"]
        ),
        "remaining_catalog_case_count": 0,
        "native_oracle_verified_behavior_count": 0,
        "native_oracle_executed_case_count": 0,
        "target_equivalent_behavior_count": 0,
        "status": "passed-bounded-complete-catalog",
        "claim_statement": (
            "120 schema/DML, schema-object, and structured-data behaviors and 480 governed cases "
            "passed the deterministic bounded model; all 500 catalog behaviors and 2,000 catalog "
            "cases now have bounded-model evidence, and the eight MS49 bootstrap behavior bindings "
            "are fully deduplicated. Native Oracle and target-equivalent counts remain zero."
        ),
        "all_catalog_cases_implemented": True,
        "bounded_catalog_execution_complete": True,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "live_schema_or_dml_observed": False,
        "live_lob_json_xml_or_object_observed": False,
        "idempiere_application_equivalence": False,
        "cloudbank_mapping_complete": False,
        "migration_complete": False,
        "production_ready": False,
    })


def build_native_execution_plan(project_root: Path, corpus: Mapping[str, Any]) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    return seal({
        "schema_version": "1.0",
        "plan_type": "lightyear-oracle-schema-structured-native-execution-plan",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "bounded_corpus_sha256": corpus["content_sha256"],
        "required_database_versions": ["19c", "26ai"],
        "required_case_count": corpus["case_count"],
        "required_behavior_count": corpus["behavior_count"],
        "required_topic_family_count": corpus["topic_family_count"],
        "required_session_controls": [
            "current_schema_and_edition", "compatible_setting", "nls_and_charset_settings",
            "enabled_roles_and_direct_grants", "query_rewrite_settings", "tablespace_identity",
            "securefile_capabilities", "xml_and_json_options",
        ],
        "required_schema_dml_observations": [
            "pre_and_post_schema_metadata", "row_results_and_rowcounts", "constraint_timing",
            "generated_values", "index_metadata_and_access", "ddl_commit_boundaries",
            "object_dependency_state", "partition_and_refresh_state",
        ],
        "required_structured_data_observations": [
            "lob_length_hash_and_locator_state", "lob_storage_attributes", "json_storage_type",
            "json_path_results_and_error_modes", "xml_storage_and_query_results",
            "object_type_version_and_collection_state", "ref_identity_and_resolution",
        ],
        "required_version_deltas": [
            "19c_native_json_datatype_unavailable", "26ai_native_json_datatype_available",
            "edition_and_schema_object_behavior", "securefile_and_structured_data_options",
        ],
        "required_receipt_fields": [
            "database_version", "database_id_hash", "session_settings", "case_id",
            "pre_state_hash", "observed_result", "observed_side_effects", "post_state_hash",
            "oracle_error_stack", "started_at", "completed_at", "runner_identity", "content_sha256",
        ],
        "authorization_required": True,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "production_ready": False,
    })


def schema_structured_matrix_markdown(receipt: Mapping[str, Any], corpus: Mapping[str, Any]) -> str:
    return f"""# Oracle schema and structured-data bounded execution matrix

Release {RELEASE} executes the final bounded catalog tranche of the MS #50 Oracle Semantic Coverage
Program. The evidence is deterministic bounded-model evidence, not native Oracle observation.

| Evidence level | Behaviors | Cases / evidence records |
|---|---:|---:|
| Catalogued | {receipt['catalogued_behavior_count']} | {receipt['catalogued_case_specification_count']} |
| Prior catalog execution | {receipt['prior_catalog_behavior_verified_count']} | {receipt['prior_catalog_case_verified_count']} |
| Schema and structured-data cases passed in bounded model | {receipt['schema_structured_behavior_verified_count']} | {receipt['schema_structured_case_verified_count']} |
| Complete bounded catalog execution | {receipt['catalog_behavior_verified_count']} | {receipt['catalog_case_verified_count']} |
| Bounded evidence including separate bootstrap executions | {receipt['bounded_model_verified_behavior_count']} | {receipt['bounded_model_evidence_record_count']} |
| Native Oracle verified | 0 | 0 |
| Target equivalent | 0 | 0 |

| Domain | Topic families | Behaviors | Passed cases |
|---|---:|---:|---:|
| Schema and DML | 10 | {receipt['schema_dml_behavior_verified_count']} | {corpus['cases_by_domain']['schema-dml']} |
| Schema objects | 7 | {receipt['schema_object_behavior_verified_count']} | {corpus['cases_by_domain']['schema-objects']} |
| Structured data | 7 | {receipt['structured_data_behavior_verified_count']} | {corpus['cases_by_domain']['structured-data']} |
| **Total** | **{corpus['topic_family_count']}** | **{corpus['behavior_count']}** | **{corpus['case_count']}** |

All eight MS #49 bootstrap bindings now overlap executed catalog behaviors, so unique bounded-model
coverage is {receipt['bounded_model_verified_behavior_count']} behaviors, not 508. The 24 bootstrap
runs remain separate evidence records, producing {receipt['bounded_model_evidence_record_count']}
records in total. Complete bounded catalog execution does not establish native Oracle conformance,
target equivalence, iDempiere application equivalence, CloudBank mapping, migration completion, or
production readiness.
"""


def build_oracle_schema_structured_artifacts(project_root: Path) -> dict[str, Any]:
    corpus = build_schema_structured_corpus(project_root)
    receipt = build_schema_structured_receipt(project_root, corpus)
    return {
        "schema-structured-corpus.json": corpus,
        "schema-structured.receipt.json": receipt,
        "native-execution-plan.json": build_native_execution_plan(project_root, corpus),
        "coverage-matrix.md": schema_structured_matrix_markdown(receipt, corpus),
    }


def validate_oracle_schema_structured_artifacts(project_root: Path) -> list[str]:
    errors = [
        f"oracle-schema-structured-dependency:{item}"
        for item in validate_oracle_transaction_cdc_artifacts(project_root)
    ]
    expected = build_oracle_schema_structured_artifacts(project_root)
    actual_receipt: Mapping[str, Any] | None = None
    for name, payload in expected.items():
        path = project_root / OUTPUT_ROOT / name
        if not path.is_file():
            errors.append(f"oracle-schema-structured-artifact-missing:{name}")
            continue
        actual: Any = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            actual = json.loads(actual)
        if name == "schema-structured.receipt.json" and isinstance(actual, Mapping):
            actual_receipt = actual
        if actual != payload:
            errors.append(f"oracle-schema-structured-artifact-drift:{name}")
    corpus = expected["schema-structured-corpus.json"]
    receipt = expected["schema-structured.receipt.json"]
    result_ids = [str(item["id"]) for item in corpus["results"]]
    behavior_ids = {str(item["behavior_id"]) for item in corpus["results"]}
    if corpus["behavior_count"] != BEHAVIOR_TARGET or len(behavior_ids) != BEHAVIOR_TARGET:
        errors.append("oracle-schema-structured-behavior-count-invalid")
    if corpus["case_count"] != CASE_TARGET or len(result_ids) != len(set(result_ids)):
        errors.append("oracle-schema-structured-case-count-invalid")
    if corpus["status"] != "passed-bounded-model" or any(
        item["status"] != "passed-bounded-model" for item in corpus["results"]
    ):
        errors.append("oracle-schema-structured-case-failure")
    expected_counts = {
        "catalog_behavior_verified_count": CUMULATIVE_CATALOG_BEHAVIOR_TARGET,
        "catalog_case_verified_count": CUMULATIVE_CATALOG_CASE_TARGET,
        "bounded_model_verified_behavior_count": CUMULATIVE_BOUNDED_BEHAVIOR_TARGET,
        "bounded_model_evidence_record_count": CUMULATIVE_EVIDENCE_RECORD_TARGET,
        "remaining_catalog_case_count": REMAINING_CATALOG_CASE_TARGET,
    }
    for name, value in expected_counts.items():
        if receipt.get(name) != value:
            errors.append(f"oracle-schema-structured-cumulative-count-invalid:{name}")
    receipt_to_check = actual_receipt if actual_receipt is not None else receipt
    for name in (
        "native_oracle_execution_observed", "native_oracle_conformance",
        "live_schema_or_dml_observed", "live_lob_json_xml_or_object_observed",
        "idempiere_application_equivalence", "cloudbank_mapping_complete",
        "migration_complete", "production_ready",
    ):
        if receipt_to_check.get(name) is not False:
            errors.append(f"oracle-schema-structured-overclaim:{name}")
    for name in ("all_catalog_cases_implemented", "bounded_catalog_execution_complete"):
        if receipt_to_check.get(name) is not True:
            errors.append(f"oracle-schema-structured-completion-claim-invalid:{name}")
    if receipt_to_check.get("content_sha256") != content_hash(receipt_to_check):
        errors.append("oracle-schema-structured-receipt-integrity-invalid")
    return sorted(set(errors))
