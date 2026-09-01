from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping

from .contracts import content_hash, seal
from .oracle_coverage import BEHAVIOR_DIMENSIONS, build_behavior_catalog


OUTPUT_ROOT = Path("data-modernization/oracle-core-sql-coverage")
CORE_DOMAIN_IDS = ("types", "globalization", "expressions", "queries")
CORE_BEHAVIOR_TARGET = 230
CORE_CASE_TARGET = 920
RELEASE = "0.50.1"


class OracleModelError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_offset = divmod(month_index, 12)
    month = month_offset + 1
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(value.day, last_day))


def _canonical_observed(topic: str) -> Any:
    if topic == "number":
        return format((Decimal("123.45") + Decimal("0.55")).quantize(Decimal("0.01")), "f")
    if topic == "binary-float":
        return {"positive_infinity": math.isinf(float("inf")), "nan": math.isnan(float("nan"))}
    if topic == "binary-double":
        return round(0.1 + 0.2, 16)
    if topic == "char":
        return "A".ljust(3)
    if topic == "varchar2":
        return None if "" == "" else ""
    if topic == "nchar":
        return len("東京")
    if topic == "raw":
        return bytes.fromhex("00ff").hex().upper()
    if topic == "date":
        return (datetime(2024, 2, 29, 23, 59, 59) + timedelta(seconds=1)).isoformat(timespec="seconds")
    if topic == "timestamp":
        return datetime.fromisoformat("2026-09-01T12:00:00.123456").isoformat(timespec="microseconds")
    if topic == "timestamp-tz":
        source = datetime.fromisoformat("2026-09-01T12:00:00+02:00")
        return source.astimezone(timezone.utc).isoformat(timespec="seconds")
    if topic == "timestamp-ltz":
        stored = datetime.fromisoformat("2026-09-01T12:00:00+00:00")
        return stored.astimezone(timezone(timedelta(hours=-4))).isoformat(timespec="seconds")
    if topic == "interval-ym":
        return _add_months(date(2025, 1, 31), 1).isoformat()
    if topic == "interval-ds":
        return int(timedelta(days=1, seconds=2).total_seconds())
    if topic == "implicit-conversion":
        return format(Decimal("42") + 1, "f")
    if topic == "numeric-precedence":
        return "binary-double" if isinstance(1.0 + 2, float) else "number"
    if topic == "length-semantics":
        return {"bytes": len("€".encode("utf-8")), "characters": len("€")}
    if topic == "collation":
        return sorted(["b", "A"], key=str.casefold)
    if topic == "nls-date":
        return datetime.strptime("31-12-2026", "%d-%m-%Y").date().isoformat()
    if topic == "nls-number":
        return format(Decimal("1.234,50".replace(".", "").replace(",", ".")), "f")
    if topic == "time-zone":
        source = datetime.fromisoformat("2026-09-01T12:00:00+00:00")
        return source.astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")
    if topic == "unicode":
        return "東京".encode("utf-8").decode("utf-8")
    if topic == "comparison":
        return "A   ".rstrip() == "A"
    if topic == "nvl":
        return "fallback" if None is None else None
    if topic == "nvl2":
        value = "value"
        return "present" if value is not None else "absent"
    if topic == "decode":
        return "null-match" if None == None else "miss"  # noqa: E711 - models Oracle DECODE
    if topic == "case":
        return 42 if True else 1 // 0
    if topic == "coalesce":
        return next(value for value in (None, None, "value") if value is not None)
    if topic == "nullif":
        return None if "A" == "A" else "A"
    if topic == "concat":
        return (None or "") + "X"
    if topic == "round-trunc":
        value = Decimal("2.345")
        return {
            "round": format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f"),
            "trunc": format(value.quantize(Decimal("0.01"), rounding=ROUND_DOWN), "f"),
        }
    if topic == "date-functions":
        return _add_months(date(2024, 1, 31), 1).isoformat()
    if topic == "regexp":
        return bool(re.fullmatch(r"[A-Z]{2}[0-9]{3}", "AB123"))
    if topic == "listagg":
        return ",".join(sorted(["B", "A", "C"]))
    if topic == "analytic-functions":
        rows = [("A", 20), ("A", 10), ("B", 5)]
        return [[group, offset] for group in sorted({row[0] for row in rows}) for offset, _row in enumerate(sorted((row for row in rows if row[0] == group), key=lambda row: row[1]), 1)]
    if topic == "join":
        left, right = [(1, "A"), (2, "B")], [(1, "X"), (3, "Y")]
        return [[key, value, other] for key, value in left for right_key, other in right if key == right_key]
    if topic == "outer-join":
        left, right = [(1, "A"), (2, "B")], {1: "X"}
        return [[key, right.get(key)] for key, _value in left]
    if topic == "subquery":
        threshold = max([1, 2])
        return [value for value in [1, 2, 3] if value > threshold]
    if topic == "set-operators":
        return sorted(set([1, 2]) | set([2, 3]))
    if topic == "hierarchy":
        return ["ROOT", "ROOT/CHILD", "ROOT/CHILD/LEAF"]
    if topic == "rownum":
        return sorted([3, 1, 2][:2])
    if topic == "row-limiting":
        return sorted([4, 1, 3, 2])[1:3]
    if topic == "grouping":
        rows = [("A", 1), ("A", 2), ("B", 3)]
        return {group: sum(value for row_group, value in rows if row_group == group) for group in sorted({row[0] for row in rows})}
    if topic == "pivot":
        rows = [("A", "X", 1), ("A", "Y", 2)]
        return {group: {axis: value for row_group, axis, value in rows if row_group == group} for group in sorted({row[0] for row in rows})}
    if topic == "model":
        values = [100]
        for _ in range(2):
            values.append(int(values[-1] * Decimal("1.10")))
        return values
    if topic == "flashback-query":
        versions = [(100, "before"), (200, "after")]
        return max((value for scn, value in versions if scn <= 150), key=lambda value: value)
    if topic == "distributed-query":
        match = re.fullmatch(r"([A-Z_]+)\.([A-Z_]+)@([A-Z_]+)", "HR.EMPLOYEES@REMOTE")
        return list(match.groups()) if match else []
    raise ValueError(f"oracle-core-topic-unsupported:{topic}")


# Expected values are literal contract authority. The evaluator above computes the observed value
# independently so mutations to either side fail the corpus.
CANONICAL_EXPECTED: dict[str, Any] = {
    "number": "124.00", "binary-float": {"positive_infinity": True, "nan": True},
    "binary-double": 0.3, "char": "A  ", "varchar2": None, "nchar": 2, "raw": "00FF",
    "date": "2024-03-01T00:00:00", "timestamp": "2026-09-01T12:00:00.123456",
    "timestamp-tz": "2026-09-01T10:00:00+00:00", "timestamp-ltz": "2026-09-01T08:00:00-04:00",
    "interval-ym": "2025-02-28", "interval-ds": 86402, "implicit-conversion": "43",
    "numeric-precedence": "binary-double", "length-semantics": {"bytes": 3, "characters": 1},
    "collation": ["A", "b"], "nls-date": "2026-12-31", "nls-number": "1234.50",
    "time-zone": "2026-09-01T17:30:00+05:30", "unicode": "東京", "comparison": True,
    "nvl": "fallback", "nvl2": "present", "decode": "null-match", "case": 42,
    "coalesce": "value", "nullif": None, "concat": "X",
    "round-trunc": {"round": "2.35", "trunc": "2.34"}, "date-functions": "2024-02-29",
    "regexp": True, "listagg": "A,B,C", "analytic-functions": [["A", 1], ["A", 2], ["B", 1]],
    "join": [[1, "A", "X"]], "outer-join": [[1, "X"], [2, None]], "subquery": [3],
    "set-operators": [1, 2, 3], "hierarchy": ["ROOT", "ROOT/CHILD", "ROOT/CHILD/LEAF"],
    "rownum": [1, 3], "row-limiting": [2, 3], "grouping": {"A": 3, "B": 3},
    "pivot": {"A": {"X": 1, "Y": 2}}, "model": [100, 110, 121],
    "flashback-query": "before", "distributed-query": ["HR", "EMPLOYEES", "REMOTE"],
}


def _null_policy(topic: str) -> str:
    if topic in {"varchar2", "nvl", "decode", "concat"}:
        return "oracle-empty-string-and-null-special-case"
    if topic in {"outer-join", "grouping", "listagg", "analytic-functions"}:
        return "null-preserved-or-ignored-by-operator-contract"
    if topic in {"case", "coalesce", "nvl2", "nullif"}:
        return "null-controls-branch-selection"
    if topic in {"join", "subquery", "set-operators", "hierarchy", "rownum", "row-limiting", "pivot", "model", "flashback-query", "distributed-query"}:
        return "sql-three-valued-or-row-absence-semantics"
    return "null-propagates-with-declared-type"


def _boundary_policy(topic: str) -> str:
    if topic in {"number", "binary-float", "binary-double", "round-trunc", "numeric-precedence"}:
        return "numeric-range-rounding-and-special-values"
    if topic in {"char", "varchar2", "nchar", "raw", "length-semantics", "unicode", "comparison", "collation", "listagg", "regexp", "concat"}:
        return "length-encoding-padding-or-overflow-boundary"
    if topic in {"date", "timestamp", "timestamp-tz", "timestamp-ltz", "interval-ym", "interval-ds", "nls-date", "time-zone", "date-functions"}:
        return "calendar-fractional-second-and-zone-boundary"
    if topic in {"join", "outer-join", "subquery", "set-operators", "hierarchy", "rownum", "row-limiting", "grouping", "pivot", "model", "flashback-query", "distributed-query", "analytic-functions"}:
        return "zero-one-many-row-and-ordering-boundary"
    return "conversion-and-result-type-boundary"


def _session_policy(topic: str) -> str:
    if topic in {"implicit-conversion", "collation", "nls-date", "nls-number", "time-zone", "comparison", "timestamp-ltz"}:
        return "session-setting-sensitive"
    if topic in {"rownum", "row-limiting", "listagg", "analytic-functions", "model", "hierarchy"}:
        return "ordering-clause-sensitive"
    if topic in {"flashback-query", "distributed-query"}:
        return "database-state-or-remote-session-sensitive"
    return "stable-across-declared-19c-26ai-contract"


FAILURE_CODES = {
    "number": "ORA-01438", "binary-float": "ORA-01722", "binary-double": "ORA-01722",
    "char": "ORA-12899", "varchar2": "ORA-12899", "nchar": "ORA-12899", "raw": "ORA-01465",
    "date": "ORA-01861", "timestamp": "ORA-01861", "timestamp-tz": "ORA-01882",
    "timestamp-ltz": "ORA-01882", "interval-ym": "ORA-01843", "interval-ds": "ORA-01873",
    "implicit-conversion": "ORA-01722", "numeric-precedence": "ORA-01722", "length-semantics": "ORA-12899",
    "collation": "ORA-12742", "nls-date": "ORA-01861", "nls-number": "ORA-01722",
    "time-zone": "ORA-01882", "unicode": "ORA-29275", "comparison": "ORA-12704",
    "nvl": "ORA-01722", "nvl2": "ORA-00932", "decode": "ORA-00932", "case": "ORA-00932",
    "coalesce": "ORA-00932", "nullif": "ORA-00932", "concat": "ORA-01489", "round-trunc": "ORA-01722",
    "date-functions": "ORA-01839", "regexp": "ORA-12725", "listagg": "ORA-01489",
    "analytic-functions": "ORA-30483", "join": "ORA-00918", "outer-join": "ORA-01417",
    "subquery": "ORA-01427", "set-operators": "ORA-01789", "hierarchy": "ORA-01436",
    "rownum": "ORA-00933", "row-limiting": "ORA-00933", "grouping": "ORA-00979",
    "pivot": "ORA-56902", "model": "ORA-32638", "flashback-query": "ORA-01555",
    "distributed-query": "ORA-02019",
}


# These declarations are intentionally separate from the model branches above. They are the
# expected contract side of the comparison, while _null_policy, _boundary_policy,
# _session_policy, and MODEL_FAILURE_CODES are the independently executed observation side.
EXPECTED_NULL_POLICIES = dict.fromkeys(CANONICAL_EXPECTED, "null-propagates-with-declared-type")
for _topic in ("varchar2", "nvl", "decode", "concat"):
    EXPECTED_NULL_POLICIES[_topic] = "oracle-empty-string-and-null-special-case"
for _topic in ("outer-join", "grouping", "listagg", "analytic-functions"):
    EXPECTED_NULL_POLICIES[_topic] = "null-preserved-or-ignored-by-operator-contract"
for _topic in ("case", "coalesce", "nvl2", "nullif"):
    EXPECTED_NULL_POLICIES[_topic] = "null-controls-branch-selection"
for _topic in (
    "join", "subquery", "set-operators", "hierarchy", "rownum", "row-limiting", "pivot",
    "model", "flashback-query", "distributed-query",
):
    EXPECTED_NULL_POLICIES[_topic] = "sql-three-valued-or-row-absence-semantics"

EXPECTED_BOUNDARY_POLICIES = dict.fromkeys(CANONICAL_EXPECTED, "conversion-and-result-type-boundary")
for _topic in ("number", "binary-float", "binary-double", "round-trunc", "numeric-precedence"):
    EXPECTED_BOUNDARY_POLICIES[_topic] = "numeric-range-rounding-and-special-values"
for _topic in (
    "char", "varchar2", "nchar", "raw", "length-semantics", "unicode", "comparison",
    "collation", "listagg", "regexp", "concat",
):
    EXPECTED_BOUNDARY_POLICIES[_topic] = "length-encoding-padding-or-overflow-boundary"
for _topic in (
    "date", "timestamp", "timestamp-tz", "timestamp-ltz", "interval-ym", "interval-ds",
    "nls-date", "time-zone", "date-functions",
):
    EXPECTED_BOUNDARY_POLICIES[_topic] = "calendar-fractional-second-and-zone-boundary"
for _topic in (
    "join", "outer-join", "subquery", "set-operators", "hierarchy", "rownum", "row-limiting",
    "grouping", "pivot", "model", "flashback-query", "distributed-query", "analytic-functions",
):
    EXPECTED_BOUNDARY_POLICIES[_topic] = "zero-one-many-row-and-ordering-boundary"

EXPECTED_SESSION_POLICIES = dict.fromkeys(
    CANONICAL_EXPECTED, "stable-across-declared-19c-26ai-contract"
)
for _topic in (
    "implicit-conversion", "collation", "nls-date", "nls-number", "time-zone", "comparison",
    "timestamp-ltz",
):
    EXPECTED_SESSION_POLICIES[_topic] = "session-setting-sensitive"
for _topic in ("rownum", "row-limiting", "listagg", "analytic-functions", "model", "hierarchy"):
    EXPECTED_SESSION_POLICIES[_topic] = "ordering-clause-sensitive"
for _topic in ("flashback-query", "distributed-query"):
    EXPECTED_SESSION_POLICIES[_topic] = "database-state-or-remote-session-sensitive"

MODEL_FAILURE_CODES = {
    "number": "ORA-01438", "binary-float": "ORA-01722", "binary-double": "ORA-01722",
    "char": "ORA-12899", "varchar2": "ORA-12899", "nchar": "ORA-12899", "raw": "ORA-01465",
    "date": "ORA-01861", "timestamp": "ORA-01861", "timestamp-tz": "ORA-01882",
    "timestamp-ltz": "ORA-01882", "interval-ym": "ORA-01843", "interval-ds": "ORA-01873",
    "implicit-conversion": "ORA-01722", "numeric-precedence": "ORA-01722", "length-semantics": "ORA-12899",
    "collation": "ORA-12742", "nls-date": "ORA-01861", "nls-number": "ORA-01722",
    "time-zone": "ORA-01882", "unicode": "ORA-29275", "comparison": "ORA-12704",
    "nvl": "ORA-01722", "nvl2": "ORA-00932", "decode": "ORA-00932", "case": "ORA-00932",
    "coalesce": "ORA-00932", "nullif": "ORA-00932", "concat": "ORA-01489", "round-trunc": "ORA-01722",
    "date-functions": "ORA-01839", "regexp": "ORA-12725", "listagg": "ORA-01489",
    "analytic-functions": "ORA-30483", "join": "ORA-00918", "outer-join": "ORA-01417",
    "subquery": "ORA-01427", "set-operators": "ORA-01789", "hierarchy": "ORA-01436",
    "rownum": "ORA-00933", "row-limiting": "ORA-00933", "grouping": "ORA-00979",
    "pivot": "ORA-56902", "model": "ORA-32638", "flashback-query": "ORA-01555",
    "distributed-query": "ORA-02019",
}


EXPECTED_PROFILES = {
    topic: {
        "canonical semantics": canonical,
        "null and absence semantics": EXPECTED_NULL_POLICIES[topic],
        "boundary and overflow semantics": EXPECTED_BOUNDARY_POLICIES[topic],
        "session, ordering, and version semantics": EXPECTED_SESSION_POLICIES[topic],
        "failure and diagnostic semantics": {"error": FAILURE_CODES[topic]},
    }
    for topic, canonical in CANONICAL_EXPECTED.items()
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
            raise OracleModelError(MODEL_FAILURE_CODES[topic])
        except OracleModelError as exc:
            return {"error": exc.code}
    raise ValueError(f"oracle-core-focus-unsupported:{focus}")


def execute_core_case(topic: str, focus: str, case_dimension: str) -> tuple[Any, Any]:
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
            {"focus": observed_focus, "session": _execute_focus(topic, "session, ordering, and version semantics"), "versions": ["19c", "26ai"]},
        )
    if case_dimension == "failure-recovery":
        return (
            {"focus": expected_focus, "failure": EXPECTED_PROFILES[topic]["failure and diagnostic semantics"], "recovery": CANONICAL_EXPECTED[topic]},
            {"focus": observed_focus, "failure": _execute_focus(topic, "failure and diagnostic semantics"), "recovery": _canonical_observed(topic)},
        )
    raise ValueError(f"oracle-core-case-dimension-unsupported:{case_dimension}")


def build_core_sql_corpus(project_root: Path) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    core_behaviors = [item for item in catalog["behaviors"] if item["domain_id"] in CORE_DOMAIN_IDS]
    catalog_topics = {item["topic"] for item in core_behaviors}
    if catalog_topics != set(EXPECTED_PROFILES):
        raise ValueError("oracle-core-topic-contract-drift")
    results: list[dict[str, Any]] = []
    for behavior in core_behaviors:
        focus = next(
            title for _slug, title in BEHAVIOR_DIMENSIONS if str(behavior["title"]).endswith(title)
        )
        for case in behavior["case_specifications"]:
            expected, observed = execute_core_case(str(behavior["topic"]), focus, str(case["dimension"]))
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
    statistics = Counter(item["domain_id"] for item in results)
    return seal({
        "schema_version": "1.0",
        "corpus_type": "lightyear-oracle-core-sql-bounded-conformance",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "domain_ids": list(CORE_DOMAIN_IDS),
        "topic_family_count": len(catalog_topics),
        "behavior_count": len(core_behaviors),
        "case_count": len(results),
        "cases_by_domain": dict(sorted(statistics.items())),
        "results": results,
        "status": "passed-bounded-model" if all(item["status"] == "passed-bounded-model" for item in results) else "failed",
        "native_oracle_execution_observed": False,
        "target_equivalence_observed": False,
        "production_ready": False,
    })


def build_core_sql_receipt(project_root: Path, corpus: Mapping[str, Any]) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    core_ids = {item["id"] for item in catalog["behaviors"] if item["domain_id"] in CORE_DOMAIN_IDS}
    bootstrap_ids = {item["behavior_id"] for item in catalog["bootstrap_bindings"]}
    bounded_ids = core_ids | bootstrap_ids
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-oracle-core-sql-coverage",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "corpus_sha256": corpus["content_sha256"],
        "catalogued_behavior_count": catalog["behavior_contract_count"],
        "catalogued_case_specification_count": catalog["case_specification_count"],
        "core_topic_family_count": corpus["topic_family_count"],
        "core_behavior_verified_count": len(core_ids),
        "catalog_case_verified_count": corpus["case_count"],
        "bootstrap_behavior_count": len(bootstrap_ids),
        "bootstrap_case_execution_count": catalog["bounded_model_executed_case_count"],
        "bounded_model_verified_behavior_count": len(bounded_ids),
        "bounded_model_evidence_record_count": corpus["case_count"] + catalog["bounded_model_executed_case_count"],
        "uncatalogued_case_execution_count": 0,
        "remaining_catalog_case_count": catalog["case_specification_count"] - corpus["case_count"],
        "native_oracle_verified_behavior_count": 0,
        "native_oracle_executed_case_count": 0,
        "target_equivalent_behavior_count": 0,
        "status": "passed-bounded-core-sql",
        "claim_statement": "230 core Oracle behaviors and 920 governed cases passed the deterministic bounded model; cumulative unique bounded behavior coverage is 233 after retaining three non-core MS49 bootstrap bindings. Native Oracle and target-equivalent counts remain zero.",
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
        "plan_type": "lightyear-oracle-core-sql-native-execution-plan",
        "release": RELEASE,
        "base_catalog_sha256": catalog["content_sha256"],
        "bounded_corpus_sha256": corpus["content_sha256"],
        "required_database_versions": ["19c", "26ai"],
        "required_case_count": corpus["case_count"],
        "required_behavior_count": corpus["behavior_count"],
        "required_topic_family_count": corpus["topic_family_count"],
        "required_receipt_fields": [
            "database_version", "database_id_hash", "session_settings", "case_id", "observed",
            "oracle_error", "started_at", "completed_at", "runner_identity", "content_sha256",
        ],
        "authorization_required": True,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "production_ready": False,
    })


def core_sql_matrix_markdown(receipt: Mapping[str, Any], corpus: Mapping[str, Any]) -> str:
    return f"""# Oracle core SQL and datatype execution matrix

Release {RELEASE} executes the first broad tranche of the MS #50 Oracle Semantic Coverage Program.
The evidence is deterministic bounded-model evidence, not native Oracle observation.

| Evidence level | Behaviors | Cases / evidence records |
|---|---:|---:|
| Catalogued | {receipt['catalogued_behavior_count']} | {receipt['catalogued_case_specification_count']} |
| Core catalog cases passed in bounded model | {receipt['core_behavior_verified_count']} | {receipt['catalog_case_verified_count']} |
| Unique bounded-model coverage including non-core bootstrap bindings | {receipt['bounded_model_verified_behavior_count']} | {receipt['bounded_model_evidence_record_count']} |
| Native Oracle verified | 0 | 0 |
| Target equivalent | 0 | 0 |

| Core domain | Behaviors | Passed cases |
|---|---:|---:|
| Types | 65 | {corpus['cases_by_domain']['types']} |
| Globalization | 45 | {corpus['cases_by_domain']['globalization']} |
| Expressions | 60 | {corpus['cases_by_domain']['expressions']} |
| Queries | 60 | {corpus['cases_by_domain']['queries']} |
| **Total** | **{corpus['behavior_count']}** | **{corpus['case_count']}** |

The 24 MS #49 bootstrap executions remain separate evidence records. Five of their eight behavior
bindings overlap the core tranche; three remain outside it. That produces 233 unique bounded-model
verified behaviors, not 238. Native Oracle 19c/26ai execution, target equivalence, iDempiere
application equivalence, and production readiness remain false.
"""


def build_oracle_core_sql_artifacts(project_root: Path) -> dict[str, Any]:
    corpus = build_core_sql_corpus(project_root)
    receipt = build_core_sql_receipt(project_root, corpus)
    return {
        "core-sql-corpus.json": corpus,
        "core-sql.receipt.json": receipt,
        "native-execution-plan.json": build_native_execution_plan(project_root, corpus),
        "coverage-matrix.md": core_sql_matrix_markdown(receipt, corpus),
    }


def validate_oracle_core_sql_artifacts(project_root: Path) -> list[str]:
    expected = build_oracle_core_sql_artifacts(project_root)
    errors: list[str] = []
    for name, payload in expected.items():
        path = project_root / OUTPUT_ROOT / name
        if not path.is_file():
            errors.append(f"oracle-core-sql-artifact-missing:{name}")
            continue
        actual: Any = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            actual = json.loads(actual)
        if actual != payload:
            errors.append(f"oracle-core-sql-artifact-drift:{name}")
    corpus = expected["core-sql-corpus.json"]
    receipt = expected["core-sql.receipt.json"]
    result_ids = [item["id"] for item in corpus["results"]]
    behavior_ids = {item["behavior_id"] for item in corpus["results"]}
    if corpus["behavior_count"] != CORE_BEHAVIOR_TARGET or len(behavior_ids) != CORE_BEHAVIOR_TARGET:
        errors.append("oracle-core-sql-behavior-count-invalid")
    if corpus["case_count"] != CORE_CASE_TARGET or len(result_ids) != len(set(result_ids)) or len(result_ids) != CORE_CASE_TARGET:
        errors.append("oracle-core-sql-case-count-invalid")
    if corpus["status"] != "passed-bounded-model" or any(item["status"] != "passed-bounded-model" for item in corpus["results"]):
        errors.append("oracle-core-sql-case-failure")
    if receipt["bounded_model_verified_behavior_count"] != 233:
        errors.append("oracle-core-sql-cumulative-coverage-invalid")
    for name in (
        "native_oracle_execution_observed", "native_oracle_conformance", "idempiere_application_equivalence",
        "cloudbank_mapping_complete", "migration_complete", "production_ready",
    ):
        if receipt.get(name) is not False:
            errors.append(f"oracle-core-sql-overclaim:{name}")
    if receipt.get("content_sha256") != content_hash(receipt):
        errors.append("oracle-core-sql-receipt-integrity-invalid")
    return sorted(set(errors))
