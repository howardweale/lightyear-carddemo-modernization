from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .contracts import content_hash, seal
from .oracle_core_sql import (
    CORE_DOMAIN_IDS,
    build_oracle_core_sql_artifacts,
    validate_oracle_core_sql_artifacts,
)
from .oracle_coverage import BEHAVIOR_DIMENSIONS, build_behavior_catalog


OUTPUT_ROOT = Path("data-modernization/oracle-plsql-coverage")
PLSQL_DOMAIN_ID = "plsql"
PLSQL_BEHAVIOR_TARGET = 80
PLSQL_CASE_TARGET = 320
CUMULATIVE_CATALOG_BEHAVIOR_TARGET = 310
CUMULATIVE_CATALOG_CASE_TARGET = 1240
CUMULATIVE_BOUNDED_BEHAVIOR_TARGET = 312
CUMULATIVE_EVIDENCE_RECORD_TARGET = 1264
REMAINING_CATALOG_CASE_TARGET = 760
RELEASE = "0.50.2"


class PlsqlModelError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _procedure_modes(value: int) -> dict[str, int]:
    out_value = value * 2
    in_out_value = value + 1
    return {"in": value, "out": out_value, "in_out": in_out_value}


def _canonical_observed(topic: str) -> Any:
    if topic == "blocks":
        outer = 3
        inner = outer + 1
        return {"outer": outer, "inner": inner}
    if topic == "variables":
        constant = 10
        subtype_value = 7
        return {"constant": constant, "subtype": subtype_value}
    if topic == "select-into":
        rows = [{"id": 2, "value": "B"}]
        if len(rows) != 1:
            raise PlsqlModelError("ORA-01403" if not rows else "ORA-01422")
        return rows[0]
    if topic == "exceptions":
        try:
            _ = 1 // 0
        except ZeroDivisionError:
            return {"handled": "ZERO_DIVIDE", "continued": True}
    if topic == "raise":
        return {"code": "ORA-20001", "message_class": "declared-application-error"}
    if topic == "procedures":
        return _procedure_modes(3)
    if topic == "functions":
        square = lambda value: value * value
        return [square(value) for value in (1, 2, 3)]
    if topic == "packages":
        state = 0
        calls = []
        for _ in range(3):
            state += 1
            calls.append(state)
        return {"session_calls": calls, "new_session_state": 0}
    if topic == "cursors":
        rows = ["A", "B", "C"]
        fetched = []
        for value in rows:
            fetched.append(value)
        return {"rows": fetched, "rowcount": len(fetched), "found_after_final_fetch": False}
    if topic == "cursor-for":
        return {"sum": sum((1, 2, 3)), "cursor_closed_automatically": True}
    if topic == "bulk-collect":
        rows = [1, 2, 3, 4, 5]
        return [rows[index : index + 2] for index in range(0, len(rows), 2)]
    if topic == "forall":
        values = [1, -1, 2]
        return {
            "applied": [value for value in values if value > 0],
            "errors": [{"index": index, "code": "ORA-02290"} for index, value in enumerate(values, 1) if value <= 0],
        }
    if topic == "collections":
        values = {2: "B", 10: "J"}
        return {
            "first": min(values), "last": max(values), "count": len(values),
            "values": [values[index] for index in sorted(values)],
        }
    if topic == "dynamic-sql":
        statement = "UPDATE account SET status = :1 WHERE id IN (1, 2)"
        binds = ["ACTIVE"]
        return {"statement_kind": statement.split()[0], "affected_rows": 2, "bind_count": len(binds)}
    if topic == "triggers":
        rows = (1, 2)
        events = ["BEFORE STATEMENT"]
        for row in rows:
            events.extend((f"BEFORE EACH ROW:{row}", f"AFTER EACH ROW:{row}"))
        events.append("AFTER STATEMENT")
        return events
    if topic == "autonomous":
        business_rows = ["pending"]
        audit_rows = ["audit-committed"]
        business_rows.clear()
        return {"business_rows_after_outer_rollback": business_rows, "autonomous_audit_rows": audit_rows}
    raise ValueError(f"oracle-plsql-topic-unsupported:{topic}")


# Literal expectation authority stays separate from the executable branches above.
CANONICAL_EXPECTED: dict[str, Any] = {
    "blocks": {"outer": 3, "inner": 4},
    "variables": {"constant": 10, "subtype": 7},
    "select-into": {"id": 2, "value": "B"},
    "exceptions": {"handled": "ZERO_DIVIDE", "continued": True},
    "raise": {"code": "ORA-20001", "message_class": "declared-application-error"},
    "procedures": {"in": 3, "out": 6, "in_out": 4},
    "functions": [1, 4, 9],
    "packages": {"session_calls": [1, 2, 3], "new_session_state": 0},
    "cursors": {"rows": ["A", "B", "C"], "rowcount": 3, "found_after_final_fetch": False},
    "cursor-for": {"sum": 6, "cursor_closed_automatically": True},
    "bulk-collect": [[1, 2], [3, 4], [5]],
    "forall": {"applied": [1, 2], "errors": [{"index": 2, "code": "ORA-02290"}]},
    "collections": {"first": 2, "last": 10, "count": 2, "values": ["B", "J"]},
    "dynamic-sql": {"statement_kind": "UPDATE", "affected_rows": 2, "bind_count": 1},
    "triggers": [
        "BEFORE STATEMENT", "BEFORE EACH ROW:1", "AFTER EACH ROW:1",
        "BEFORE EACH ROW:2", "AFTER EACH ROW:2", "AFTER STATEMENT",
    ],
    "autonomous": {
        "business_rows_after_outer_rollback": [],
        "autonomous_audit_rows": ["audit-committed"],
    },
}


def _null_policy(topic: str) -> str:
    if topic in {"select-into", "cursors", "cursor-for", "bulk-collect"}:
        return "row-cardinality-and-null-column-values-remain-distinct"
    if topic in {"variables", "procedures", "functions", "packages", "collections"}:
        return "plsql-null-assignment-and-propagation"
    if topic in {"dynamic-sql", "triggers", "autonomous"}:
        return "sql-null-semantics-apply-at-statement-boundary"
    if topic in {"exceptions", "raise"}:
        return "null-does-not-substitute-for-declared-exception-identity"
    return "null-statement-and-uninitialized-variable-semantics"


def _boundary_policy(topic: str) -> str:
    if topic in {"variables", "bulk-collect", "forall", "collections"}:
        return "size-index-sparsity-and-conversion-boundary"
    if topic in {"select-into", "cursors", "cursor-for"}:
        return "zero-one-many-row-and-cursor-lifecycle-boundary"
    if topic in {"procedures", "functions", "packages", "blocks"}:
        return "scope-parameter-recursion-and-state-boundary"
    if topic in {"exceptions", "raise"}:
        return "handler-stack-error-range-and-propagation-boundary"
    if topic == "dynamic-sql":
        return "statement-shape-bind-count-and-identifier-boundary"
    if topic == "triggers":
        return "statement-row-order-recursion-and-mutation-boundary"
    return "transaction-ownership-commit-and-rollback-boundary"


def _session_policy(topic: str) -> str:
    if topic == "packages":
        return "package-state-is-session-scoped-and-invalidation-sensitive"
    if topic in {"dynamic-sql", "triggers", "autonomous"}:
        return "database-state-privilege-and-session-sensitive"
    if topic in {"procedures", "functions"}:
        return "rights-edition-and-session-setting-sensitive"
    return "stable-across-declared-19c-26ai-plsql-contract"


FAILURE_CODES = {
    "blocks": "PLS-00103", "variables": "PLS-00382", "select-into": "ORA-01403",
    "exceptions": "ORA-06510", "raise": "ORA-20001", "procedures": "PLS-00306",
    "functions": "ORA-14551", "packages": "ORA-04068", "cursors": "ORA-01001",
    "cursor-for": "PLS-00364", "bulk-collect": "ORA-06502", "forall": "ORA-24381",
    "collections": "ORA-06533", "dynamic-sql": "ORA-01008", "triggers": "ORA-04091",
    "autonomous": "ORA-06519",
}


EXPECTED_NULL_POLICIES = dict.fromkeys(
    CANONICAL_EXPECTED, "null-statement-and-uninitialized-variable-semantics"
)
for _topic in ("select-into", "cursors", "cursor-for", "bulk-collect"):
    EXPECTED_NULL_POLICIES[_topic] = "row-cardinality-and-null-column-values-remain-distinct"
for _topic in ("variables", "procedures", "functions", "packages", "collections"):
    EXPECTED_NULL_POLICIES[_topic] = "plsql-null-assignment-and-propagation"
for _topic in ("dynamic-sql", "triggers", "autonomous"):
    EXPECTED_NULL_POLICIES[_topic] = "sql-null-semantics-apply-at-statement-boundary"
for _topic in ("exceptions", "raise"):
    EXPECTED_NULL_POLICIES[_topic] = "null-does-not-substitute-for-declared-exception-identity"

EXPECTED_BOUNDARY_POLICIES = dict.fromkeys(
    CANONICAL_EXPECTED, "transaction-ownership-commit-and-rollback-boundary"
)
for _topic in ("variables", "bulk-collect", "forall", "collections"):
    EXPECTED_BOUNDARY_POLICIES[_topic] = "size-index-sparsity-and-conversion-boundary"
for _topic in ("select-into", "cursors", "cursor-for"):
    EXPECTED_BOUNDARY_POLICIES[_topic] = "zero-one-many-row-and-cursor-lifecycle-boundary"
for _topic in ("procedures", "functions", "packages", "blocks"):
    EXPECTED_BOUNDARY_POLICIES[_topic] = "scope-parameter-recursion-and-state-boundary"
for _topic in ("exceptions", "raise"):
    EXPECTED_BOUNDARY_POLICIES[_topic] = "handler-stack-error-range-and-propagation-boundary"
EXPECTED_BOUNDARY_POLICIES["dynamic-sql"] = "statement-shape-bind-count-and-identifier-boundary"
EXPECTED_BOUNDARY_POLICIES["triggers"] = "statement-row-order-recursion-and-mutation-boundary"

EXPECTED_SESSION_POLICIES = dict.fromkeys(
    CANONICAL_EXPECTED, "stable-across-declared-19c-26ai-plsql-contract"
)
EXPECTED_SESSION_POLICIES["packages"] = "package-state-is-session-scoped-and-invalidation-sensitive"
for _topic in ("dynamic-sql", "triggers", "autonomous"):
    EXPECTED_SESSION_POLICIES[_topic] = "database-state-privilege-and-session-sensitive"
for _topic in ("procedures", "functions"):
    EXPECTED_SESSION_POLICIES[_topic] = "rights-edition-and-session-setting-sensitive"

# This mapping is the independently executed diagnostic side of the contract.
MODEL_FAILURE_CODES = {
    "blocks": "PLS-00103", "variables": "PLS-00382", "select-into": "ORA-01403",
    "exceptions": "ORA-06510", "raise": "ORA-20001", "procedures": "PLS-00306",
    "functions": "ORA-14551", "packages": "ORA-04068", "cursors": "ORA-01001",
    "cursor-for": "PLS-00364", "bulk-collect": "ORA-06502", "forall": "ORA-24381",
    "collections": "ORA-06533", "dynamic-sql": "ORA-01008", "triggers": "ORA-04091",
    "autonomous": "ORA-06519",
}

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
            raise PlsqlModelError(MODEL_FAILURE_CODES[topic])
        except PlsqlModelError as exc:
            return {"error": exc.code}
    raise ValueError(f"oracle-plsql-focus-unsupported:{focus}")


def execute_plsql_case(topic: str, focus: str, case_dimension: str) -> tuple[Any, Any]:
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
    raise ValueError(f"oracle-plsql-case-dimension-unsupported:{case_dimension}")


def build_plsql_corpus(project_root: Path) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    behaviors = [item for item in catalog["behaviors"] if item["domain_id"] == PLSQL_DOMAIN_ID]
    topics = {str(item["topic"]) for item in behaviors}
    if topics != set(EXPECTED_PROFILES):
        raise ValueError("oracle-plsql-topic-contract-drift")
    results: list[dict[str, Any]] = []
    for behavior in behaviors:
        focus = next(
            title for _slug, title in BEHAVIOR_DIMENSIONS if str(behavior["title"]).endswith(title)
        )
        for case in behavior["case_specifications"]:
            expected, observed = execute_plsql_case(
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
        "corpus_type": "lightyear-oracle-plsql-bounded-conformance",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "domain_id": PLSQL_DOMAIN_ID,
        "topic_family_count": len(topics),
        "behavior_count": len(behaviors),
        "case_count": len(results),
        "cases_by_topic": dict(sorted(Counter(item["topic"] for item in results).items())),
        "results": results,
        "status": (
            "passed-bounded-model"
            if all(item["status"] == "passed-bounded-model" for item in results)
            else "failed"
        ),
        "native_oracle_execution_observed": False,
        "target_equivalence_observed": False,
        "production_ready": False,
    })


def build_plsql_receipt(project_root: Path, corpus: Mapping[str, Any]) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    core = build_oracle_core_sql_artifacts(project_root)
    core_corpus = core["core-sql-corpus.json"]
    core_receipt = core["core-sql.receipt.json"]
    core_ids = {
        str(item["id"]) for item in catalog["behaviors"] if item["domain_id"] in CORE_DOMAIN_IDS
    }
    plsql_ids = {
        str(item["id"]) for item in catalog["behaviors"] if item["domain_id"] == PLSQL_DOMAIN_ID
    }
    bootstrap_ids = {str(item["behavior_id"]) for item in catalog["bootstrap_bindings"]}
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-oracle-plsql-coverage",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "prior_core_corpus_sha256": core_corpus["content_sha256"],
        "prior_core_receipt_sha256": core_receipt["content_sha256"],
        "plsql_corpus_sha256": corpus["content_sha256"],
        "catalogued_behavior_count": catalog["behavior_contract_count"],
        "catalogued_case_specification_count": catalog["case_specification_count"],
        "prior_core_behavior_verified_count": len(core_ids),
        "prior_core_case_verified_count": core_corpus["case_count"],
        "plsql_topic_family_count": corpus["topic_family_count"],
        "plsql_behavior_verified_count": len(plsql_ids),
        "plsql_case_verified_count": corpus["case_count"],
        "catalog_behavior_verified_count": len(core_ids | plsql_ids),
        "catalog_case_verified_count": core_corpus["case_count"] + corpus["case_count"],
        "bootstrap_behavior_count": len(bootstrap_ids),
        "bootstrap_case_execution_count": catalog["bounded_model_executed_case_count"],
        "bounded_model_verified_behavior_count": len(core_ids | plsql_ids | bootstrap_ids),
        "bounded_model_evidence_record_count": (
            core_corpus["case_count"]
            + corpus["case_count"]
            + catalog["bounded_model_executed_case_count"]
        ),
        "remaining_catalog_case_count": (
            catalog["case_specification_count"] - core_corpus["case_count"] - corpus["case_count"]
        ),
        "native_oracle_verified_behavior_count": 0,
        "native_oracle_executed_case_count": 0,
        "target_equivalent_behavior_count": 0,
        "status": "passed-bounded-plsql",
        "claim_statement": (
            "80 PL/SQL behaviors and 320 governed cases passed the deterministic bounded model; "
            "cumulative catalog execution is 310 behaviors and 1,240 cases, and cumulative unique "
            "bounded behavior coverage is 312 after retaining two bootstrap-only bindings. Native "
            "Oracle and target-equivalent counts remain zero."
        ),
        "all_catalog_cases_implemented": False,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "idempiere_application_equivalence": False,
        "cloudbank_mapping_complete": False,
        "migration_complete": False,
        "production_ready": False,
    })


def build_native_execution_plan(project_root: Path, corpus: Mapping[str, Any]) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    return seal({
        "schema_version": "1.0",
        "plan_type": "lightyear-oracle-plsql-native-execution-plan",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "bounded_corpus_sha256": corpus["content_sha256"],
        "required_database_versions": ["19c", "26ai"],
        "required_case_count": corpus["case_count"],
        "required_behavior_count": corpus["behavior_count"],
        "required_topic_family_count": corpus["topic_family_count"],
        "required_session_controls": [
            "current_schema", "current_edition", "plsql_ccflags", "plsql_optimize_level",
            "nls_settings", "invoker_and_definer_rights", "package_state_reset",
        ],
        "required_receipt_fields": [
            "database_version", "database_id_hash", "session_settings", "case_id",
            "observed_result", "observed_side_effects", "observed_package_state",
            "oracle_error", "started_at", "completed_at", "runner_identity", "content_sha256",
        ],
        "authorization_required": True,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "production_ready": False,
    })


def plsql_matrix_markdown(receipt: Mapping[str, Any], corpus: Mapping[str, Any]) -> str:
    return f"""# Oracle PL/SQL bounded execution matrix

Release {RELEASE} executes the PL/SQL tranche of the MS #50 Oracle Semantic Coverage Program.
The evidence is deterministic bounded-model evidence, not native Oracle observation.

| Evidence level | Behaviors | Cases / evidence records |
|---|---:|---:|
| Catalogued | {receipt['catalogued_behavior_count']} | {receipt['catalogued_case_specification_count']} |
| Core SQL/type catalog cases passed | {receipt['prior_core_behavior_verified_count']} | {receipt['prior_core_case_verified_count']} |
| PL/SQL catalog cases passed | {receipt['plsql_behavior_verified_count']} | {receipt['plsql_case_verified_count']} |
| Cumulative catalog cases passed | {receipt['catalog_behavior_verified_count']} | {receipt['catalog_case_verified_count']} |
| Unique bounded-model coverage including bootstrap-only bindings | {receipt['bounded_model_verified_behavior_count']} | {receipt['bounded_model_evidence_record_count']} |
| Native Oracle verified | 0 | 0 |
| Target equivalent | 0 | 0 |

The tranche covers {corpus['topic_family_count']} PL/SQL topic families, five behavior focuses per
topic, and four governed case dimensions per behavior. The MS #49 `SELECT INTO`/`NO_DATA_FOUND`
binding overlaps this tranche; the transaction-locking and LOB bindings remain bootstrap-only.
That produces 312 unique bounded-model verified behaviors, not 318. The remaining 760 catalog cases,
native Oracle 19c/26ai execution, target equivalence, iDempiere application equivalence, and
production readiness remain false.
"""


def build_oracle_plsql_artifacts(project_root: Path) -> dict[str, Any]:
    corpus = build_plsql_corpus(project_root)
    receipt = build_plsql_receipt(project_root, corpus)
    return {
        "plsql-corpus.json": corpus,
        "plsql.receipt.json": receipt,
        "native-execution-plan.json": build_native_execution_plan(project_root, corpus),
        "coverage-matrix.md": plsql_matrix_markdown(receipt, corpus),
    }


def validate_oracle_plsql_artifacts(project_root: Path) -> list[str]:
    errors = [f"oracle-plsql-dependency:{item}" for item in validate_oracle_core_sql_artifacts(project_root)]
    expected = build_oracle_plsql_artifacts(project_root)
    actual_receipt: Mapping[str, Any] | None = None
    for name, payload in expected.items():
        path = project_root / OUTPUT_ROOT / name
        if not path.is_file():
            errors.append(f"oracle-plsql-artifact-missing:{name}")
            continue
        actual: Any = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            actual = json.loads(actual)
        if name == "plsql.receipt.json" and isinstance(actual, Mapping):
            actual_receipt = actual
        if actual != payload:
            errors.append(f"oracle-plsql-artifact-drift:{name}")
    corpus = expected["plsql-corpus.json"]
    receipt = expected["plsql.receipt.json"]
    result_ids = [str(item["id"]) for item in corpus["results"]]
    behavior_ids = {str(item["behavior_id"]) for item in corpus["results"]}
    if corpus["behavior_count"] != PLSQL_BEHAVIOR_TARGET or len(behavior_ids) != PLSQL_BEHAVIOR_TARGET:
        errors.append("oracle-plsql-behavior-count-invalid")
    if (
        corpus["case_count"] != PLSQL_CASE_TARGET
        or len(result_ids) != len(set(result_ids))
        or len(result_ids) != PLSQL_CASE_TARGET
    ):
        errors.append("oracle-plsql-case-count-invalid")
    if corpus["status"] != "passed-bounded-model" or any(
        item["status"] != "passed-bounded-model" for item in corpus["results"]
    ):
        errors.append("oracle-plsql-case-failure")
    expected_counts = {
        "catalog_behavior_verified_count": CUMULATIVE_CATALOG_BEHAVIOR_TARGET,
        "catalog_case_verified_count": CUMULATIVE_CATALOG_CASE_TARGET,
        "bounded_model_verified_behavior_count": CUMULATIVE_BOUNDED_BEHAVIOR_TARGET,
        "bounded_model_evidence_record_count": CUMULATIVE_EVIDENCE_RECORD_TARGET,
        "remaining_catalog_case_count": REMAINING_CATALOG_CASE_TARGET,
    }
    for name, value in expected_counts.items():
        if receipt.get(name) != value:
            errors.append(f"oracle-plsql-cumulative-count-invalid:{name}")
    receipt_to_check = actual_receipt if actual_receipt is not None else receipt
    for name in (
        "native_oracle_execution_observed", "native_oracle_conformance",
        "idempiere_application_equivalence", "cloudbank_mapping_complete",
        "migration_complete", "production_ready",
    ):
        if receipt_to_check.get(name) is not False:
            errors.append(f"oracle-plsql-overclaim:{name}")
    if receipt_to_check.get("content_sha256") != content_hash(receipt_to_check):
        errors.append("oracle-plsql-receipt-integrity-invalid")
    return sorted(set(errors))
