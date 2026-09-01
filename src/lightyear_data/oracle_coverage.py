from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import content_hash, seal


OUTPUT_ROOT = Path("data-modernization/oracle-semantic-coverage")
CATALOG_ID = "lightyear-oracle-semantic-coverage-v1"
CASE_DIMENSIONS = (
    ("canonical", "Canonical documented behavior"),
    ("null-boundary", "Null, absence, and boundary behavior"),
    ("session-version", "Session setting and database-version behavior"),
    ("failure-recovery", "Failure, error code, and recovery behavior"),
)
BEHAVIOR_DIMENSIONS = (
    ("canonical", "canonical semantics"),
    ("null-absence", "null and absence semantics"),
    ("boundary", "boundary and overflow semantics"),
    ("session-order", "session, ordering, and version semantics"),
    ("failure", "failure and diagnostic semantics"),
)


def _topics(raw: str) -> tuple[tuple[str, str, str], ...]:
    return tuple(tuple(field.strip() for field in line.split("|", 2)) for line in raw.strip().splitlines())


DOMAIN_SPECS = (
    ("types", "TYPE", "Datatypes, nulls, numbers, dates, and intervals", 65, _topics("""
number | NUMBER precision and scale | sqlrf/Data-Types.html
binary-float | BINARY_FLOAT special values | sqlrf/Data-Types.html
binary-double | BINARY_DOUBLE precedence | sqlrf/Data-Types.html
char | CHAR blank-padding semantics | sqlrf/Data-Type-Comparison-Rules.html
varchar2 | VARCHAR2 empty-string and length semantics | sqlrf/Data-Types.html
nchar | NCHAR national-character semantics | sqlrf/Data-Types.html
raw | RAW binary-value semantics | sqlrf/Data-Types.html
date | DATE second precision and arithmetic | sqlrf/Data-Types.html
timestamp | TIMESTAMP fractional-second semantics | sqlrf/Data-Types.html
timestamp-tz | TIMESTAMP WITH TIME ZONE semantics | sqlrf/Data-Types.html
timestamp-ltz | TIMESTAMP WITH LOCAL TIME ZONE normalization | sqlrf/Data-Types.html
interval-ym | INTERVAL YEAR TO MONTH semantics | sqlrf/Data-Types.html
interval-ds | INTERVAL DAY TO SECOND semantics | sqlrf/Data-Types.html
""")),
    ("globalization", "NLS", "Character semantics, NLS, collation, and conversion", 45, _topics("""
implicit-conversion | Implicit datatype conversion | sqlrf/Data-Type-Comparison-Rules.html
numeric-precedence | Numeric precedence and coercion | sqlrf/Data-Type-Comparison-Rules.html
length-semantics | BYTE and CHAR length semantics | sqlrf/Data-Types.html
collation | Linguistic and binary collation | sqlrf/NLSSORT.html
nls-date | NLS date parsing and formatting | sqlrf/Format-Models.html
nls-number | NLS numeric characters | sqlrf/TO_CHAR-number.html
time-zone | Session and database time zones | sqlrf/Data-Types.html
unicode | Database and national character-set conversion | sqlrf/Data-Types.html
comparison | Text comparison and trailing spaces | sqlrf/Data-Type-Comparison-Rules.html
""")),
    ("expressions", "EXPR", "Functions and expression evaluation", 60, _topics("""
nvl | NVL coercion | sqlrf/NVL.html
nvl2 | NVL2 return-type selection | sqlrf/NVL2.html
decode | DECODE null matching and coercion | sqlrf/DECODE.html
case | CASE short-circuit evaluation | sqlrf/CASE-Expressions.html
coalesce | COALESCE short-circuit evaluation | sqlrf/COALESCE.html
nullif | NULLIF comparison semantics | sqlrf/NULLIF.html
concat | Concatenation and null operands | sqlrf/Concatenation-Operator.html
round-trunc | Numeric ROUND and TRUNC | sqlrf/ROUND-number.html
date-functions | ADD_MONTHS and month-end behavior | sqlrf/ADD_MONTHS.html
regexp | Regular-expression matching | sqlrf/REGEXP_LIKE.html
listagg | LISTAGG ordering and overflow | sqlrf/LISTAGG.html
analytic-functions | Analytic window evaluation | sqlrf/Analytic-Functions.html
""")),
    ("queries", "QUERY", "Queries, joins, analytics, hierarchy, and set operations", 60, _topics("""
join | ANSI join semantics | sqlrf/Joins.html
outer-join | Oracle outer-join operator | sqlrf/Joins.html
subquery | Scalar and correlated subqueries | sqlrf/Using-Subqueries.html
set-operators | UNION, INTERSECT, and MINUS | sqlrf/The-UNION-ALL-INTERSECT-MINUS-Operators.html
hierarchy | CONNECT BY hierarchical queries | sqlrf/Hierarchical-Queries.html
rownum | ROWNUM evaluation order | sqlrf/ROWNUM-Pseudocolumn.html
row-limiting | OFFSET and FETCH row limiting | sqlrf/SELECT.html
grouping | GROUP BY and HAVING | sqlrf/SELECT.html
pivot | PIVOT and UNPIVOT | sqlrf/SELECT.html
model | SQL MODEL clause | sqlrf/SELECT.html
flashback-query | AS OF flashback query | sqlrf/SELECT.html
distributed-query | Database-link query semantics | sqlrf/SELECT.html
""")),
    ("schema-dml", "DML", "DML, DDL, constraints, and indexes", 50, _topics("""
insert | INSERT value and subquery forms | sqlrf/INSERT.html
update | UPDATE evaluation and row counts | sqlrf/UPDATE.html
delete | DELETE and cascading effects | sqlrf/DELETE.html
merge | MERGE match and delete semantics | sqlrf/MERGE.html
returning | DML RETURNING INTO | sqlrf/RETURNING-INTO-Clause.html
constraints | Constraint enforcement and deferral | sqlrf/constraint.html
identity | Identity-column generation | sqlrf/CREATE-TABLE.html
defaults | Defaults and default-on-null | sqlrf/CREATE-TABLE.html
indexes | B-tree, bitmap, and function indexes | sqlrf/CREATE-INDEX.html
alter-table | ALTER TABLE schema evolution | sqlrf/ALTER-TABLE.html
""")),
    ("transactions", "TXN", "Transactions, isolation, locking, and concurrency", 45, _topics("""
commit | COMMIT durability and write completion | sqlrf/COMMIT.html
rollback | ROLLBACK transaction effects | sqlrf/ROLLBACK.html
savepoint | SAVEPOINT and partial rollback | sqlrf/SAVEPOINT.html
read-committed | READ COMMITTED statement consistency | sqlrf/SET-TRANSACTION.html
serializable | SERIALIZABLE conflict behavior | sqlrf/SET-TRANSACTION.html
read-only | Read-only transaction snapshots | sqlrf/SET-TRANSACTION.html
for-update | SELECT FOR UPDATE locking | sqlrf/SELECT.html
lock-table | Explicit table locking | sqlrf/LOCK-TABLE.html
deadlock | Deadlock detection and rollback scope | cncpt/data-concurrency-and-consistency.html
""")),
    ("plsql", "PLSQL", "PL/SQL, packages, cursors, exceptions, and triggers", 80, _topics("""
blocks | Anonymous and stored PL/SQL blocks | lnpls/plsql-block.html
variables | Variables, constants, and subtypes | lnpls/plsql-data-types.html
select-into | SELECT INTO cardinality | lnpls/SELECT-INTO-statement.html
exceptions | Predefined and user exceptions | lnpls/predefined-exceptions.html
raise | RAISE and RAISE_APPLICATION_ERROR | lnpls/raising-exceptions-explicitly.html
procedures | Procedure parameter modes | lnpls/subprogram-parameters.html
functions | Function purity and SQL invocation | lnpls/plsql-subprograms.html
packages | Package specification and state | lnpls/plsql-packages.html
cursors | Explicit cursors and cursor attributes | lnpls/explicit-cursor.html
cursor-for | Cursor FOR LOOP behavior | lnpls/cursor-FOR-LOOP-statement.html
bulk-collect | BULK COLLECT semantics | lnpls/SELECT-INTO-statement.html
forall | FORALL bulk DML and SAVE EXCEPTIONS | lnpls/FORALL-statement.html
collections | Associative arrays, nested tables, and varrays | lnpls/plsql-collections-and-records.html
dynamic-sql | EXECUTE IMMEDIATE native dynamic SQL | lnpls/EXECUTE-IMMEDIATE-statement.html
triggers | DML, compound, and system triggers | lnpls/plsql-triggers.html
autonomous | Autonomous transaction boundaries | lnpls/AUTONOMOUS_TRANSACTION-pragma.html
""")),
    ("schema-objects", "OBJ", "Views, sequences, synonyms, partitions, and materialized views", 35, _topics("""
views | View projection and check options | sqlrf/CREATE-VIEW.html
materialized-views | Materialized-view refresh and query rewrite | sqlrf/CREATE-MATERIALIZED-VIEW.html
sequences | Sequence allocation and caching | sqlrf/CREATE-SEQUENCE.html
synonyms | Private and public name resolution | sqlrf/CREATE-SYNONYM.html
partitioning | Range, list, and hash partitioning | sqlrf/CREATE-TABLE.html
iot | Index-organized tables | sqlrf/CREATE-TABLE.html
editioning | Editioning views and object visibility | adfns/editions.html
""")),
    ("structured-data", "DATA", "LOB, JSON, XML, and object types", 35, _topics("""
blob | BLOB binary semantics | sqlrf/Data-Types.html
clob | CLOB and NCLOB character semantics | sqlrf/Data-Types.html
securefile | SecureFiles LOB storage behavior | adlob/introduction-to-large-objects.html
json | SQL/JSON generation and query | adjsn/json-in-oracle-database.html
json-datatype | Native JSON datatype version delta | sqlrf/Data-Types.html
xmltype | XMLType storage and query | sqlrf/Data-Types.html
object-types | Object types, nested tables, and REF values | sqlrf/CREATE-TYPE.html
""")),
    ("operations", "OPS", "CDC, metadata, session, and security behavior", 25, _topics("""
logminer | Redo and LogMiner change capture | sutil/steps-in-a-typical-logminer-session.html
dictionary | Data dictionary metadata visibility | refrn/static-data-dictionary-views.html
session | ALTER SESSION and current schema | sqlrf/ALTER-SESSION.html
privileges | Object and system privilege checks | sqlrf/GRANT.html
errors | Oracle error identity and diagnostics | errmg/ORA-00000.html
""")),
)


def _doc_url(path: str) -> str:
    return f"https://docs.oracle.com/en/database/oracle/oracle-database/19/{path}"


def _build_behaviors() -> list[dict[str, Any]]:
    behaviors: list[dict[str, Any]] = []
    for domain_id, code, _title, quota, topics in DOMAIN_SPECS:
        if len(topics) * len(BEHAVIOR_DIMENSIONS) != quota:
            raise ValueError(f"oracle-coverage-domain-quota-invalid:{domain_id}")
        sequence = 0
        for topic_slug, topic_title, doc_path in topics:
            for _dimension_slug, dimension_title in BEHAVIOR_DIMENSIONS:
                sequence += 1
                behavior_id = f"ORA-{code}-{sequence:03d}"
                cases = [
                    {
                        "id": f"{behavior_id}-CASE-{case_number:02d}",
                        "dimension": case_slug,
                        "intent": case_title,
                        "status": "specified-not-executed",
                        "expected_evidence": "native-oracle-result-and-diagnostic-required",
                    }
                    for case_number, (case_slug, case_title) in enumerate(CASE_DIMENSIONS, 1)
                ]
                behaviors.append({
                    "id": behavior_id,
                    "domain_id": domain_id,
                    "topic": topic_slug,
                    "title": f"{topic_title}: {dimension_title}",
                    "documentation": _doc_url(doc_path),
                    "version_scope": {
                        "baseline": "19c",
                        "delta": "26ai",
                        "native_versions_executed": [],
                    },
                    "case_specifications": cases,
                    "case_specification_count": len(cases),
                    "catalog_status": "catalogued-not-executed",
                    "native_oracle_verified": False,
                    "target_equivalent": False,
                    "production_ready": False,
                })
    return behaviors


def _bootstrap_bindings(behaviors: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    fixture_ids = (
        "oracle-empty-string-null", "oracle-number-precision-scale", "oracle-date-time-arithmetic",
        "oracle-nvl-decode-coercion", "oracle-rownum-ordering", "oracle-select-for-update-sequence",
        "oracle-select-into-no-data-found", "oracle-lob-boundaries",
    )
    topic_targets = (
        ("varchar2", "null and absence semantics"), ("number", "boundary and overflow semantics"),
        ("date", "boundary and overflow semantics"), ("nvl", "canonical semantics"),
        ("rownum", "session, ordering, and version semantics"), ("for-update", "canonical semantics"),
        ("select-into", "failure and diagnostic semantics"), ("blob", "boundary and overflow semantics"),
    )
    found = {
        (item["topic"], dimension): str(item["id"])
        for item in behaviors
        for _slug, dimension in BEHAVIOR_DIMENSIONS
        if str(item["title"]).endswith(dimension)
    }
    return [
        {"fixture_id": fixture_id, "behavior_id": found[target], "evidence_status": "passed-bounded-model-only"}
        for fixture_id, target in zip(fixture_ids, topic_targets)
    ]


def build_behavior_catalog(project_root: Path) -> dict[str, Any]:
    prior = json.loads((project_root / "data-modernization/oracle-dialect-conformance/fixture-catalog.json").read_text(encoding="utf-8"))
    behaviors = _build_behaviors()
    domains = []
    for domain_id, _code, title, quota, _topics_rows in DOMAIN_SPECS:
        selected = [item for item in behaviors if item["domain_id"] == domain_id]
        domains.append({
            "id": domain_id,
            "title": title,
            "behavior_contract_target": quota,
            "behavior_contract_count": len(selected),
            "case_specification_count": sum(item["case_specification_count"] for item in selected),
        })
    return seal({
        "schema_version": "1.0",
        "catalog_type": "lightyear-oracle-semantic-behavior-catalog",
        "catalog_id": CATALOG_ID,
        "release": "0.50.0",
        "version_strategy": {
            "installed_base_baseline": "Oracle Database 19c",
            "current_long_term_delta": "Oracle AI Database 26ai",
            "sample_schema_asset_release": "v23.3",
        },
        "authority_policy": "Oracle documentation is behavior authority; sample schemas are source examples.",
        "prior_fixture_catalog_sha256": prior["content_sha256"],
        "domains": domains,
        "behaviors": behaviors,
        "bootstrap_bindings": _bootstrap_bindings(behaviors),
        "behavior_contract_count": len(behaviors),
        "case_specification_count": sum(item["case_specification_count"] for item in behaviors),
        "bounded_model_verified_behavior_count": 8,
        "bounded_model_executed_case_count": 24,
        "native_oracle_verified_behavior_count": 0,
        "native_oracle_executed_case_count": 0,
        "target_equivalent_behavior_count": 0,
        "catalog_complete": True,
        "case_implementation_complete": False,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "migration_complete": False,
        "production_ready": False,
    })


def build_coverage_receipt(catalog: Mapping[str, Any]) -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-oracle-semantic-coverage",
        "catalog_id": CATALOG_ID,
        "catalog_sha256": catalog["content_sha256"],
        "domain_count": len(catalog["domains"]),
        "behavior_contract_count": catalog["behavior_contract_count"],
        "case_specification_count": catalog["case_specification_count"],
        "bounded_model_verified_behavior_count": catalog["bounded_model_verified_behavior_count"],
        "bounded_model_executed_case_count": catalog["bounded_model_executed_case_count"],
        "native_oracle_verified_behavior_count": 0,
        "native_oracle_executed_case_count": 0,
        "target_equivalent_behavior_count": 0,
        "status": "catalogued-program-foundation",
        "claim_statement": "500 catalogued behaviors and 2,000 specified cases; 8 behaviors and 24 cases have bounded-model evidence; none has native Oracle verification in this receipt.",
        "case_implementation_complete": False,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "idempiere_application_equivalence": False,
        "cloudbank_mapping_complete": False,
        "migration_complete": False,
        "production_ready": False,
    })


def coverage_matrix_markdown(catalog: Mapping[str, Any]) -> str:
    rows = "\n".join(
        f"| {domain['title']} | {domain['behavior_contract_count']} | {domain['case_specification_count']} |"
        for domain in catalog["domains"]
    )
    return f"""# Oracle semantic coverage matrix

Release 0.50.0 establishes the governed coverage contract. It does not claim that all catalogued
behaviors have been implemented or executed.

| Domain | Behavior contracts | Specified cases |
|---|---:|---:|
{rows}
| **Total** | **{catalog['behavior_contract_count']}** | **{catalog['case_specification_count']}** |

## Evidence ladder

| Level | Behaviors | Cases | Meaning |
|---|---:|---:|---|
| Catalogued | 500 | 2,000 | Governed scope with Oracle documentation authority |
| Bounded-model verified | 8 | 24 | Existing MS #49 bootstrap evidence only |
| Native Oracle verified | 0 | 0 | Requires an authorized Oracle 19c/26ai execution receipt |
| Target equivalent | 0 | 0 | Requires source-versus-target comparison evidence |

The architect-facing coverage answer must always carry the evidence level. Catalogued does not mean
supported, bounded-model execution does not mean native Oracle conformance, and native verification
does not by itself establish target equivalence or production readiness.
"""


def build_oracle_coverage_artifacts(project_root: Path) -> dict[str, Any]:
    catalog = build_behavior_catalog(project_root)
    return {
        "behavior-catalog.json": catalog,
        "coverage.receipt.json": build_coverage_receipt(catalog),
        "coverage-matrix.md": coverage_matrix_markdown(catalog),
    }


def validate_oracle_coverage_artifacts(project_root: Path) -> list[str]:
    expected = build_oracle_coverage_artifacts(project_root)
    output_root = project_root / OUTPUT_ROOT
    errors: list[str] = []
    for name, payload in expected.items():
        path = output_root / name
        if not path.is_file():
            errors.append(f"oracle-coverage-artifact-missing:{name}")
            continue
        actual: Any = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            actual = json.loads(actual)
        if actual != payload:
            errors.append(f"oracle-coverage-artifact-drift:{name}")
    catalog = expected["behavior-catalog.json"]
    receipt = expected["coverage.receipt.json"]
    ids = [item["id"] for item in catalog["behaviors"]]
    case_ids = [case["id"] for item in catalog["behaviors"] for case in item["case_specifications"]]
    if len(ids) != 500 or len(set(ids)) != 500:
        errors.append("oracle-coverage-behavior-count-invalid")
    if len(case_ids) != 2000 or len(set(case_ids)) != 2000:
        errors.append("oracle-coverage-case-count-invalid")
    if any(not str(item["documentation"]).startswith("https://docs.oracle.com/") for item in catalog["behaviors"]):
        errors.append("oracle-coverage-authority-invalid")
    if len(catalog["bootstrap_bindings"]) != 8:
        errors.append("oracle-coverage-bootstrap-binding-invalid")
    for name in (
        "case_implementation_complete", "native_oracle_execution_observed", "native_oracle_conformance",
        "idempiere_application_equivalence", "cloudbank_mapping_complete", "migration_complete", "production_ready",
    ):
        if receipt.get(name) is not False:
            errors.append(f"oracle-coverage-overclaim:{name}")
    if receipt.get("content_sha256") != content_hash(receipt):
        errors.append("oracle-coverage-receipt-integrity-invalid")
    return sorted(set(errors))
