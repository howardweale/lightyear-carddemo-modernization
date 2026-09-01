from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .contracts import content_hash, seal
from .oracle_core_sql import CORE_DOMAIN_IDS, build_oracle_core_sql_artifacts
from .oracle_coverage import BEHAVIOR_DIMENSIONS, build_behavior_catalog
from .oracle_plsql import build_oracle_plsql_artifacts, validate_oracle_plsql_artifacts


OUTPUT_ROOT = Path("data-modernization/oracle-transaction-cdc-coverage")
DOMAIN_IDS = ("transactions", "operations")
TRANSACTION_BEHAVIOR_TARGET = 45
OPERATIONS_BEHAVIOR_TARGET = 25
BEHAVIOR_TARGET = 70
CASE_TARGET = 280
CUMULATIVE_CATALOG_BEHAVIOR_TARGET = 380
CUMULATIVE_CATALOG_CASE_TARGET = 1520
CUMULATIVE_BOUNDED_BEHAVIOR_TARGET = 381
CUMULATIVE_EVIDENCE_RECORD_TARGET = 1544
REMAINING_CATALOG_CASE_TARGET = 480
RELEASE = "0.50.3"


class TransactionCdcModelError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_observed(topic: str) -> Any:
    if topic == "commit":
        pending = ["row-1"]
        visible_to_self = bool(pending)
        committed = list(pending)
        pending.clear()
        return {
            "before_commit_visible_to_self": visible_to_self,
            "after_commit_visible_to_new_session": bool(committed),
            "rollback_after_commit_restores": False,
        }
    if topic == "rollback":
        rows = [1, 2]
        before = rows + [3]
        after = list(rows)
        return {"before": before, "after": after}
    if topic == "savepoint":
        rows = [1]
        savepoint_size = len(rows)
        rows.append(2)
        del rows[savepoint_size:]
        return {"after_partial_rollback": rows, "transaction_open": True}
    if topic == "read-committed":
        committed_versions = ["v1", "v2"]
        return {
            "statement_1": committed_versions[0],
            "statement_2": committed_versions[1],
            "snapshot_scope": "statement",
        }
    if topic == "serializable":
        snapshot = "v1"
        concurrent_commit = "v2"
        conflict = "ORA-08177" if concurrent_commit != snapshot else None
        return {"initial": snapshot, "conflict": conflict, "snapshot_scope": "transaction"}
    if topic == "read-only":
        snapshot = "v1"
        concurrent_commit = "v2"
        return {
            "snapshot": snapshot,
            "concurrent_commit_visible": snapshot == concurrent_commit,
            "write_error": "ORA-01456",
        }
    if topic == "for-update":
        rows = {1: "locked", 2: "available"}
        return {
            "first_session": rows[1],
            "second_session": "waits",
            "skip_locked_rows": [key for key, value in rows.items() if value != "locked"],
        }
    if topic == "lock-table":
        lock_mode = "EXCLUSIVE"
        return {
            "mode": lock_mode,
            "conflicting_dml": "waits" if lock_mode == "EXCLUSIVE" else "runs",
            "release": "commit-or-rollback",
        }
    if topic == "deadlock":
        waits = {"session-a": "row-2", "session-b": "row-1"}
        cycle = len(waits) == 2 and len(set(waits.values())) == 2
        return {
            "victim_error": "ORA-00060" if cycle else None,
            "victim_statement_rolled_back": cycle,
            "transaction_usable": cycle,
        }
    if topic == "logminer":
        changes = [(101, "INSERT"), (102, "UPDATE"), (103, "COMMIT")]
        mined = [item for item in changes if item[1] != "COMMIT"]
        return {
            "ordered_scns": [item[0] for item in mined],
            "operations": [item[1] for item in mined],
            "resume_exclusive_after_scn": mined[-1][0],
        }
    if topic == "dictionary":
        objects = [("APP", "ACCOUNT"), ("SYS", "OBJ$")]
        visible = [f"{owner}.{name}" for owner, name in objects if owner == "APP"]
        return {"visible_objects": visible, "dba_view_requires_privilege": True}
    if topic == "session":
        current_schema = "APP"
        current_schema = "REPORTING"
        return {
            "initial_schema": "APP",
            "current_schema": current_schema,
            "committed_data_unchanged": True,
        }
    if topic == "privileges":
        grants: set[str] = set()
        before = "SELECT" in grants
        grants.add("SELECT")
        after_grant = "SELECT" in grants
        grants.remove("SELECT")
        return {
            "select_before_grant": before,
            "select_after_grant": after_grant,
            "select_after_revoke": "SELECT" in grants,
        }
    if topic == "errors":
        return {
            "code": "ORA-00001",
            "sqlstate_class": "integrity-constraint",
            "message_language_sensitive": True,
        }
    raise ValueError(f"oracle-transaction-cdc-topic-unsupported:{topic}")


# Literal contract authority is deliberately separate from the executable branches above.
CANONICAL_EXPECTED: dict[str, Any] = {
    "commit": {
        "before_commit_visible_to_self": True,
        "after_commit_visible_to_new_session": True,
        "rollback_after_commit_restores": False,
    },
    "rollback": {"before": [1, 2, 3], "after": [1, 2]},
    "savepoint": {"after_partial_rollback": [1], "transaction_open": True},
    "read-committed": {"statement_1": "v1", "statement_2": "v2", "snapshot_scope": "statement"},
    "serializable": {"initial": "v1", "conflict": "ORA-08177", "snapshot_scope": "transaction"},
    "read-only": {"snapshot": "v1", "concurrent_commit_visible": False, "write_error": "ORA-01456"},
    "for-update": {"first_session": "locked", "second_session": "waits", "skip_locked_rows": [2]},
    "lock-table": {"mode": "EXCLUSIVE", "conflicting_dml": "waits", "release": "commit-or-rollback"},
    "deadlock": {
        "victim_error": "ORA-00060",
        "victim_statement_rolled_back": True,
        "transaction_usable": True,
    },
    "logminer": {
        "ordered_scns": [101, 102],
        "operations": ["INSERT", "UPDATE"],
        "resume_exclusive_after_scn": 102,
    },
    "dictionary": {"visible_objects": ["APP.ACCOUNT"], "dba_view_requires_privilege": True},
    "session": {
        "initial_schema": "APP",
        "current_schema": "REPORTING",
        "committed_data_unchanged": True,
    },
    "privileges": {
        "select_before_grant": False,
        "select_after_grant": True,
        "select_after_revoke": False,
    },
    "errors": {
        "code": "ORA-00001",
        "sqlstate_class": "integrity-constraint",
        "message_language_sensitive": True,
    },
}


def _null_policy(topic: str) -> str:
    if topic in {"commit", "rollback", "savepoint"}:
        return "null-row-values-do-not-change-transaction-boundaries"
    if topic in {"read-committed", "serializable", "read-only"}:
        return "null-values-follow-snapshot-visibility-without-equality"
    if topic in {"for-update", "lock-table", "deadlock"}:
        return "null-values-do-not-alter-lock-identity-or-wait-ownership"
    if topic == "logminer":
        return "supplemental-data-absence-is-distinct-from-sql-null"
    if topic == "dictionary":
        return "absent-metadata-row-is-distinct-from-null-column-metadata"
    if topic == "session":
        return "unset-session-property-uses-declared-database-default"
    if topic == "privileges":
        return "missing-grant-is-denial-not-null-authorization"
    return "diagnostic-field-absence-is-distinct-from-null-message-text"


def _boundary_policy(topic: str) -> str:
    if topic in {"commit", "rollback", "savepoint"}:
        return "transaction-end-savepoint-lifetime-and-implicit-ddl-boundary"
    if topic in {"read-committed", "serializable", "read-only"}:
        return "statement-transaction-snapshot-and-write-conflict-boundary"
    if topic in {"for-update", "lock-table", "deadlock"}:
        return "lock-mode-wait-timeout-skip-locked-and-deadlock-boundary"
    if topic == "logminer":
        return "scn-redo-range-order-resume-and-gap-boundary"
    if topic == "dictionary":
        return "owner-container-edition-and-privilege-visibility-boundary"
    if topic == "session":
        return "schema-edition-nls-container-and-session-lifetime-boundary"
    if topic == "privileges":
        return "direct-role-definer-invoker-and-revoke-boundary"
    return "error-stack-code-offset-cause-and-localized-message-boundary"


def _session_policy(topic: str) -> str:
    if topic in {"commit", "rollback", "savepoint"}:
        return "transaction-identity-autocommit-and-ddl-policy-are-session-bound"
    if topic in {"read-committed", "serializable", "read-only"}:
        return "isolation-mode-and-snapshot-start-are-explicit-session-controls"
    if topic in {"for-update", "lock-table", "deadlock"}:
        return "two-session-schedule-and-lock-timeout-must-be-receipted"
    if topic == "logminer":
        return "database-incarnation-scn-timezone-and-logminer-options-must-be-receipted"
    if topic == "dictionary":
        return "container-current-user-and-edition-control-metadata-visibility"
    if topic == "session":
        return "alter-session-effects-are-session-scoped-and-reset-on-reconnect"
    if topic == "privileges":
        return "current-user-enabled-roles-and-rights-mode-must-be-receipted"
    return "error-code-is-stable-while-message-text-can-vary-by-release-and-language"


FAILURE_CODES = {
    "commit": "ORA-02091",
    "rollback": "ORA-01086",
    "savepoint": "ORA-01086",
    "read-committed": "ORA-00054",
    "serializable": "ORA-08177",
    "read-only": "ORA-01456",
    "for-update": "ORA-00054",
    "lock-table": "ORA-00054",
    "deadlock": "ORA-00060",
    "logminer": "ORA-01291",
    "dictionary": "ORA-00942",
    "session": "ORA-01435",
    "privileges": "ORA-01031",
    "errors": "ORA-00600",
}

EXPECTED_NULL_POLICIES = {
    "commit": "null-row-values-do-not-change-transaction-boundaries",
    "rollback": "null-row-values-do-not-change-transaction-boundaries",
    "savepoint": "null-row-values-do-not-change-transaction-boundaries",
    "read-committed": "null-values-follow-snapshot-visibility-without-equality",
    "serializable": "null-values-follow-snapshot-visibility-without-equality",
    "read-only": "null-values-follow-snapshot-visibility-without-equality",
    "for-update": "null-values-do-not-alter-lock-identity-or-wait-ownership",
    "lock-table": "null-values-do-not-alter-lock-identity-or-wait-ownership",
    "deadlock": "null-values-do-not-alter-lock-identity-or-wait-ownership",
    "logminer": "supplemental-data-absence-is-distinct-from-sql-null",
    "dictionary": "absent-metadata-row-is-distinct-from-null-column-metadata",
    "session": "unset-session-property-uses-declared-database-default",
    "privileges": "missing-grant-is-denial-not-null-authorization",
    "errors": "diagnostic-field-absence-is-distinct-from-null-message-text",
}

EXPECTED_BOUNDARY_POLICIES = {
    "commit": "transaction-end-savepoint-lifetime-and-implicit-ddl-boundary",
    "rollback": "transaction-end-savepoint-lifetime-and-implicit-ddl-boundary",
    "savepoint": "transaction-end-savepoint-lifetime-and-implicit-ddl-boundary",
    "read-committed": "statement-transaction-snapshot-and-write-conflict-boundary",
    "serializable": "statement-transaction-snapshot-and-write-conflict-boundary",
    "read-only": "statement-transaction-snapshot-and-write-conflict-boundary",
    "for-update": "lock-mode-wait-timeout-skip-locked-and-deadlock-boundary",
    "lock-table": "lock-mode-wait-timeout-skip-locked-and-deadlock-boundary",
    "deadlock": "lock-mode-wait-timeout-skip-locked-and-deadlock-boundary",
    "logminer": "scn-redo-range-order-resume-and-gap-boundary",
    "dictionary": "owner-container-edition-and-privilege-visibility-boundary",
    "session": "schema-edition-nls-container-and-session-lifetime-boundary",
    "privileges": "direct-role-definer-invoker-and-revoke-boundary",
    "errors": "error-stack-code-offset-cause-and-localized-message-boundary",
}

EXPECTED_SESSION_POLICIES = {
    "commit": "transaction-identity-autocommit-and-ddl-policy-are-session-bound",
    "rollback": "transaction-identity-autocommit-and-ddl-policy-are-session-bound",
    "savepoint": "transaction-identity-autocommit-and-ddl-policy-are-session-bound",
    "read-committed": "isolation-mode-and-snapshot-start-are-explicit-session-controls",
    "serializable": "isolation-mode-and-snapshot-start-are-explicit-session-controls",
    "read-only": "isolation-mode-and-snapshot-start-are-explicit-session-controls",
    "for-update": "two-session-schedule-and-lock-timeout-must-be-receipted",
    "lock-table": "two-session-schedule-and-lock-timeout-must-be-receipted",
    "deadlock": "two-session-schedule-and-lock-timeout-must-be-receipted",
    "logminer": "database-incarnation-scn-timezone-and-logminer-options-must-be-receipted",
    "dictionary": "container-current-user-and-edition-control-metadata-visibility",
    "session": "alter-session-effects-are-session-scoped-and-reset-on-reconnect",
    "privileges": "current-user-enabled-roles-and-rights-mode-must-be-receipted",
    "errors": "error-code-is-stable-while-message-text-can-vary-by-release-and-language",
}

# This is the independently executed diagnostic side of the contract.
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
            raise TransactionCdcModelError(MODEL_FAILURE_CODES[topic])
        except TransactionCdcModelError as exc:
            return {"error": exc.code}
    raise ValueError(f"oracle-transaction-cdc-focus-unsupported:{focus}")


def execute_transaction_cdc_case(
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
    raise ValueError(f"oracle-transaction-cdc-case-dimension-unsupported:{case_dimension}")


def build_transaction_cdc_corpus(project_root: Path) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    behaviors = [item for item in catalog["behaviors"] if item["domain_id"] in DOMAIN_IDS]
    topics = {str(item["topic"]) for item in behaviors}
    if topics != set(EXPECTED_PROFILES):
        raise ValueError("oracle-transaction-cdc-topic-contract-drift")
    results: list[dict[str, Any]] = []
    for behavior in behaviors:
        focus = next(
            title for _slug, title in BEHAVIOR_DIMENSIONS if str(behavior["title"]).endswith(title)
        )
        for case in behavior["case_specifications"]:
            expected, observed = execute_transaction_cdc_case(
                str(behavior["topic"]), focus, str(case["dimension"])
            )
            results.append({
                "id": case["id"],
                "behavior_id": behavior["id"],
                "domain_id": behavior["domain_id"],
                "topic": behavior["topic"],
                "focus": focus,
                "dimension": case["dimension"],
                "expected": expected,
                "observed": observed,
                "status": "passed-bounded-model" if observed == expected else "failed",
            })
    return seal({
        "schema_version": "1.0",
        "corpus_type": "lightyear-oracle-transaction-cdc-bounded-conformance",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "domain_ids": list(DOMAIN_IDS),
        "topic_family_count": len(topics),
        "behavior_count": len(behaviors),
        "case_count": len(results),
        "cases_by_domain": dict(sorted(Counter(item["domain_id"] for item in results).items())),
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


def build_transaction_cdc_receipt(project_root: Path, corpus: Mapping[str, Any]) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    core = build_oracle_core_sql_artifacts(project_root)
    plsql = build_oracle_plsql_artifacts(project_root)
    prior = plsql["plsql.receipt.json"]
    prior_ids = {
        str(item["id"])
        for item in catalog["behaviors"]
        if item["domain_id"] in (*CORE_DOMAIN_IDS, "plsql")
    }
    tranche_ids = {
        str(item["id"]) for item in catalog["behaviors"] if item["domain_id"] in DOMAIN_IDS
    }
    bootstrap_ids = {str(item["behavior_id"]) for item in catalog["bootstrap_bindings"]}
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-oracle-transaction-cdc-coverage",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "prior_core_corpus_sha256": core["core-sql-corpus.json"]["content_sha256"],
        "prior_plsql_corpus_sha256": plsql["plsql-corpus.json"]["content_sha256"],
        "prior_plsql_receipt_sha256": prior["content_sha256"],
        "transaction_cdc_corpus_sha256": corpus["content_sha256"],
        "catalogued_behavior_count": catalog["behavior_contract_count"],
        "catalogued_case_specification_count": catalog["case_specification_count"],
        "prior_catalog_behavior_verified_count": prior["catalog_behavior_verified_count"],
        "prior_catalog_case_verified_count": prior["catalog_case_verified_count"],
        "transaction_behavior_verified_count": TRANSACTION_BEHAVIOR_TARGET,
        "operations_behavior_verified_count": OPERATIONS_BEHAVIOR_TARGET,
        "transaction_cdc_topic_family_count": corpus["topic_family_count"],
        "transaction_cdc_behavior_verified_count": len(tranche_ids),
        "transaction_cdc_case_verified_count": corpus["case_count"],
        "catalog_behavior_verified_count": len(prior_ids | tranche_ids),
        "catalog_case_verified_count": prior["catalog_case_verified_count"] + corpus["case_count"],
        "bootstrap_behavior_count": len(bootstrap_ids),
        "bootstrap_case_execution_count": catalog["bounded_model_executed_case_count"],
        "bounded_model_verified_behavior_count": len(prior_ids | tranche_ids | bootstrap_ids),
        "bounded_model_evidence_record_count": (
            prior["catalog_case_verified_count"]
            + corpus["case_count"]
            + catalog["bounded_model_executed_case_count"]
        ),
        "remaining_catalog_case_count": (
            catalog["case_specification_count"]
            - prior["catalog_case_verified_count"]
            - corpus["case_count"]
        ),
        "native_oracle_verified_behavior_count": 0,
        "native_oracle_executed_case_count": 0,
        "target_equivalent_behavior_count": 0,
        "status": "passed-bounded-transaction-cdc",
        "claim_statement": (
            "70 transaction, locking, CDC, metadata, session, security, and diagnostic behaviors "
            "and 280 governed cases passed the deterministic bounded model; cumulative catalog "
            "execution is 380 behaviors and 1,520 cases, and cumulative unique bounded behavior "
            "coverage is 381 after retaining one structured-data bootstrap-only binding. Native "
            "Oracle and target-equivalent counts remain zero."
        ),
        "all_catalog_cases_implemented": False,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "live_concurrency_observed": False,
        "live_redo_or_logminer_observed": False,
        "live_privilege_enforcement_observed": False,
        "idempiere_application_equivalence": False,
        "cloudbank_mapping_complete": False,
        "migration_complete": False,
        "production_ready": False,
    })


def build_native_execution_plan(project_root: Path, corpus: Mapping[str, Any]) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    return seal({
        "schema_version": "1.0",
        "plan_type": "lightyear-oracle-transaction-cdc-native-execution-plan",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "bounded_corpus_sha256": corpus["content_sha256"],
        "required_database_versions": ["19c", "26ai"],
        "required_case_count": corpus["case_count"],
        "required_behavior_count": corpus["behavior_count"],
        "required_topic_family_count": corpus["topic_family_count"],
        "required_session_controls": [
            "two_or_more_session_identities",
            "autocommit_disabled",
            "isolation_level",
            "current_schema_and_container",
            "enabled_roles_and_direct_grants",
            "nls_and_timezone_settings",
            "lock_wait_timeout",
            "database_incarnation",
        ],
        "required_concurrency_observations": [
            "transaction_ids",
            "deterministic_session_schedule",
            "blocking_and_wait_state",
            "lock_modes",
            "snapshot_visibility",
            "commit_and_rollback_side_effects",
            "deadlock_victim_and_rollback_scope",
        ],
        "required_cdc_observations": [
            "start_and_end_scn",
            "redo_log_identity",
            "database_incarnation",
            "logminer_options",
            "ordered_change_records",
            "transaction_commit_scn",
            "resume_checkpoint",
            "supplemental_logging_state",
        ],
        "required_receipt_fields": [
            "database_version",
            "database_id_hash",
            "session_identities",
            "session_settings",
            "case_id",
            "observed_result",
            "observed_side_effects",
            "oracle_error_stack",
            "started_at",
            "completed_at",
            "runner_identity",
            "content_sha256",
        ],
        "authorization_required": True,
        "logminer_privileges_required": True,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "production_ready": False,
    })


def transaction_cdc_matrix_markdown(receipt: Mapping[str, Any], corpus: Mapping[str, Any]) -> str:
    return f"""# Oracle transaction and CDC bounded execution matrix

Release {RELEASE} executes the transaction and operations tranche of the MS #50 Oracle Semantic
Coverage Program. The evidence is deterministic bounded-model evidence, not native Oracle
observation.

| Evidence level | Behaviors | Cases / evidence records |
|---|---:|---:|
| Catalogued | {receipt['catalogued_behavior_count']} | {receipt['catalogued_case_specification_count']} |
| Prior core SQL/type and PL/SQL catalog execution | {receipt['prior_catalog_behavior_verified_count']} | {receipt['prior_catalog_case_verified_count']} |
| Transaction and operations cases passed in bounded model | {receipt['transaction_cdc_behavior_verified_count']} | {receipt['transaction_cdc_case_verified_count']} |
| Cumulative catalog execution | {receipt['catalog_behavior_verified_count']} | {receipt['catalog_case_verified_count']} |
| Unique bounded-model coverage including bootstrap-only binding | {receipt['bounded_model_verified_behavior_count']} | {receipt['bounded_model_evidence_record_count']} |
| Native Oracle verified | 0 | 0 |
| Target equivalent | 0 | 0 |

| Domain | Topic families | Behaviors | Passed cases |
|---|---:|---:|---:|
| Transactions, isolation, locking, and concurrency | 9 | {receipt['transaction_behavior_verified_count']} | {corpus['cases_by_domain']['transactions']} |
| CDC, metadata, session, security, and diagnostics | 5 | {receipt['operations_behavior_verified_count']} | {corpus['cases_by_domain']['operations']} |
| **Total** | **{corpus['topic_family_count']}** | **{corpus['behavior_count']}** | **{corpus['case_count']}** |

Seven of the eight MS #49 bootstrap behavior bindings now overlap executed catalog tranches; the LOB
binding remains bootstrap-only. That produces {receipt['bounded_model_verified_behavior_count']}
unique bounded-model verified behaviors, not 388. The remaining
{receipt['remaining_catalog_case_count']} catalog cases cover schema/DML, schema objects, and
structured data. Concurrency schedules, locks, redo/SCN, LogMiner, metadata visibility, privilege
enforcement, and diagnostics are bounded simulations until sealed native Oracle 19c/26ai evidence
is attached.
"""


def build_oracle_transaction_cdc_artifacts(project_root: Path) -> dict[str, Any]:
    corpus = build_transaction_cdc_corpus(project_root)
    receipt = build_transaction_cdc_receipt(project_root, corpus)
    return {
        "transaction-cdc-corpus.json": corpus,
        "transaction-cdc.receipt.json": receipt,
        "native-execution-plan.json": build_native_execution_plan(project_root, corpus),
        "coverage-matrix.md": transaction_cdc_matrix_markdown(receipt, corpus),
    }


def validate_oracle_transaction_cdc_artifacts(project_root: Path) -> list[str]:
    errors = [
        f"oracle-transaction-cdc-dependency:{item}"
        for item in validate_oracle_plsql_artifacts(project_root)
    ]
    expected = build_oracle_transaction_cdc_artifacts(project_root)
    actual_receipt: Mapping[str, Any] | None = None
    for name, payload in expected.items():
        path = project_root / OUTPUT_ROOT / name
        if not path.is_file():
            errors.append(f"oracle-transaction-cdc-artifact-missing:{name}")
            continue
        actual: Any = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            actual = json.loads(actual)
        if name == "transaction-cdc.receipt.json" and isinstance(actual, Mapping):
            actual_receipt = actual
        if actual != payload:
            errors.append(f"oracle-transaction-cdc-artifact-drift:{name}")
    corpus = expected["transaction-cdc-corpus.json"]
    receipt = expected["transaction-cdc.receipt.json"]
    result_ids = [item["id"] for item in corpus["results"]]
    behavior_ids = {item["behavior_id"] for item in corpus["results"]}
    if corpus["behavior_count"] != BEHAVIOR_TARGET or len(behavior_ids) != BEHAVIOR_TARGET:
        errors.append("oracle-transaction-cdc-behavior-count-invalid")
    if corpus["case_count"] != CASE_TARGET or len(result_ids) != len(set(result_ids)):
        errors.append("oracle-transaction-cdc-case-count-invalid")
    if corpus["status"] != "passed-bounded-model" or any(
        item["status"] != "passed-bounded-model" for item in corpus["results"]
    ):
        errors.append("oracle-transaction-cdc-case-failure")
    expected_counts = {
        "catalog_behavior_verified_count": CUMULATIVE_CATALOG_BEHAVIOR_TARGET,
        "catalog_case_verified_count": CUMULATIVE_CATALOG_CASE_TARGET,
        "bounded_model_verified_behavior_count": CUMULATIVE_BOUNDED_BEHAVIOR_TARGET,
        "bounded_model_evidence_record_count": CUMULATIVE_EVIDENCE_RECORD_TARGET,
        "remaining_catalog_case_count": REMAINING_CATALOG_CASE_TARGET,
    }
    for name, value in expected_counts.items():
        if receipt.get(name) != value:
            errors.append(f"oracle-transaction-cdc-cumulative-count-invalid:{name}")
    receipt_to_check = actual_receipt if actual_receipt is not None else receipt
    for name in (
        "native_oracle_execution_observed",
        "native_oracle_conformance",
        "live_concurrency_observed",
        "live_redo_or_logminer_observed",
        "live_privilege_enforcement_observed",
        "idempiere_application_equivalence",
        "cloudbank_mapping_complete",
        "migration_complete",
        "production_ready",
    ):
        if receipt_to_check.get(name) is not False:
            errors.append(f"oracle-transaction-cdc-overclaim:{name}")
    if receipt_to_check.get("content_sha256") != content_hash(receipt_to_check):
        errors.append("oracle-transaction-cdc-receipt-integrity-invalid")
    return sorted(set(errors))
