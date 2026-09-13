"""MS69: deterministic, source-bound comparison with an explicit coverage ceiling."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from lightyear_common.io import normalize_logical_source, source_hashes

from .contracts import canonical_bytes, content_hash, seal
from .idempiere_divergence import (
    MANIFEST_PATH, PINNED_COMMIT, PROJECT_ID, SEMANTIC_CORE_PATH,
    validate_stage1_artifacts,
)
from .idempiere_sql import Unit, parse_script
from .semantic_core import CompatibilityClass


VERSION = "1.0"
ROOT_PATH = Path("factory/idempiere-divergence-audit")
PILOT_PATH = ROOT_PATH / "stage2-pilot.json"
REPORT_PATH = ROOT_PATH / "stage2-comparison.json"
RECEIPT_PATH = ROOT_PATH / "stage2.receipt.json"
POLICY_PATH = ROOT_PATH / "comparison-policy.json"
SCHEMA_PATH = Path("data-modernization/schema/idempiere-semantic-comparison.schema.json")
HELPER_PATH = "db/postgresql/functions/altercolumn.sql"
CODE_PATHS = (
    "src/lightyear_data/idempiere_sql.py",
    "src/lightyear_data/idempiere_comparison.py",
    "src/lightyear_data/semantic_core.py",
    "src/lightyear_data/contracts.py",
    "src/lightyear_common/io.py",
    "src/lightyear_data/idempiere_divergence.py",
)
CATEGORIES = ("parsed-and-compared", "parsed-but-indeterminate", "unparsed")
CLAIMS = {
    "deterministic_sweep_complete": True,
    "all_constructs_decided": False,
    "agent_triage_complete": False,
    "audit_complete": False,
    "native_execution": False,
    "application_equivalence": False,
    "production_ready": False,
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def policy() -> dict[str, Any]:
    """Narrow static projection, never an implicit execution-equivalence policy."""
    return seal({
        "schema_version": VERSION,
        "policy_id": "idda-static-declared-effects-v1",
        "milestone": 69,
        "verdict_scope": "ordered-declared-schema-effects-not-final-state-or-execution",
        "semantic_core": SEMANTIC_CORE_PATH.as_posix(),
        "compatibility_classes": [item.value for item in CompatibilityClass],
        "equivalence_requires": [
            "all-in-scope-units-fully-parsed-and-decided",
            "identical-ordered-effect-keys-without-resynchronization",
            "at-least-one-in-scope-effect",
            "no-opaque-expression-or-unresolved-domain",
        ],
        "finite_numeric_projection": "Compare explicit precision and scale only, 1<=p<=38 and 0<=s<=p. Excludes PostgreSQL NaN/infinities, runtime conversions and storage; no unrestricted NUMBER/NUMERIC equivalence.",
        "character_policy": "Empty string vs NULL, BYTE/CHAR length units, encoding and collation remain policy decisions even for equal declared lengths.",
        "datetime_policy": "Oracle DATE retains seconds; PostgreSQL DATE does not. Timestamp precision, time-zone and range differences remain unresolved without an admitted domain.",
        "helper_policy": "Project the five positional t_alter_column arguments using the pinned altercolumn.sql implementation. Never discharge catalog lookups, coercion, dependent views, permissions or helper deployment/version history.",
        "dml_policy": "Record INSERT VALUES, UPDATE assignments and DELETE predicates; literals are typed, nonliteral expressions opaque. Baseline column domains, triggers, predicates and coercions are not admitted; DML remains indeterminate, including identical text.",
        "schema_policy": "Compare declared column type facets, explicit defaults and nullability. Constraints, indexes and drops retain domain/catalog obligations. No baseline schema reconstruction, final-state proof, transaction or application claim.",
        "administrative_exclusions": ["Oracle SET DEFINE OFF", "Oracle SET SQLBLANKLINES ON", "SELECT register_migration_script with one filename literal FROM dual"],
        "administrative_boundary": "These known client settings and migration-registration effects are separately counted outside SQL-effect coverage; literal SQL execution and an existing search-path/schema mapping are assumptions, not verified client/runtime behavior. Any other session/client command remains unparsed.",
        "coverage_unit": "Non-comment top-level SQL statement or opaque procedural block on each dialect side, NOT token occurrences. A lexically broken file or unterminated Oracle block may form one opaque remainder unit. Expanded column effects never inflate the statement denominator.",
        "alignment_policy": "Keep order and repetitions. If ordered effect identities differ, all nonadministrative parsed units are indeterminate; do not guess resynchronization or silently drop unmatched operations.",
        "provenance": "not-classified; generated-or-maintained output audit, not evidence of independent hand maintenance",
        "authorities": [
            "https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html",
            "https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html",
            "https://www.postgresql.org/docs/16/datatype-numeric.html",
            "https://www.postgresql.org/docs/16/datatype-character.html",
            "https://www.postgresql.org/docs/16/datatype-datetime.html",
        ],
        "documentation_boundary": "Language references define this bounded profile; they do not establish the runtime database versions or configuration used by iDempiere deployments.",
        "models_called": 0,
        "ms70_handoff": "References to flagged source ranges only; no prompts, work orders, agents or billable calls are created by MS69. MS70 must bound and budget individual contexts using existing workcell controls.",
    })


def compare_effect(left: dict[str, Any], right: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Return verdict, existing semantic-core class, and explicit reason codes."""
    reasons = set(left["reasons"] + right["reasons"])
    lval, rval = left["value"], right["value"]
    facet = left["facet"]
    if facet == "type":
        kinds = {lval["canonical_type"], rval["canonical_type"]}
        if kinds == {"exact-decimal"}:
            admitted = all(v["precision"] is not None and v["scale"] is not None and 1 <= v["precision"] <= 38 and 0 <= v["scale"] <= v["precision"] for v in (lval, rval))
            if not admitted:
                reasons.add("unbounded-or-nonportable-numeric-domain")
        elif kinds <= {"fixed-character", "variable-character"}:
            reasons.add("character-empty-string-length-and-collation-policy")
        elif kinds <= {"date", "timestamp", "timestamp-with-time-zone"}:
            reasons.add("datetime-precision-range-and-zone-policy")
        else:
            reasons.add("type-domain-policy-required")
    if facet == "default":
        if lval["kind"] == "opaque" or rval["kind"] == "opaque":
            reasons.add("opaque-default-expression")
        if lval["kind"] != rval["kind"]:
            reasons.add("default-coercion-context-required")
    if reasons:
        return "indeterminate", CompatibilityClass.POLICY_DECISION_REQUIRED.value, sorted(reasons)
    if lval != rval:
        return "divergent", CompatibilityClass.LOSSY.value, ["declared-" + facet + "-mismatch"]
    return "equivalent", CompatibilityClass.NORMALIZED_EQUIVALENT.value, []


def _identity(effect: dict[str, Any]) -> tuple[str, str, str]:
    return effect["kind"], effect["target"], effect["facet"]


def _effects(units: list[Unit]) -> list[tuple[Unit, dict[str, Any]]]:
    result = []
    for unit in units:
        if unit.administrative:
            continue
        if not unit.parsed:
            result.append((unit, {"kind": "unparsed", "target": "<opaque>", "facet": "statement", "value": None, "reasons": unit.reasons}))
        else:
            result.extend((unit, e) for e in unit.effects)
    return result


def _coverage(segments: list[dict[str, Any]]) -> dict[str, int]:
    count: Counter[str] = Counter()
    for segment in segments:
        count[segment["category"]] += segment["last_unit"] - segment["first_unit"] + 1
    return {"input_units": sum(count.values()), "administrative_units_excluded": count["administrative-excluded"], "sql_units": sum(count[c] for c in CATEGORIES), **{c: count[c] for c in CATEGORIES}}


def _segments(units: list[Unit], decisions: dict[int, list[tuple[str, str, list[str]]]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    signatures: list[list[str]] = []
    for u in units:
        ds = decisions.get(u.ordinal, [])
        if u.administrative:
            category, reasons, kind = "administrative-excluded", [], "client-or-registration"
        elif not u.parsed:
            category, reasons, kind = "unparsed", u.reasons, "unparsed"
        else:
            reasons = sorted({r for _, _, rs in ds for r in rs})
            category = "parsed-but-indeterminate" if not ds or any(v == "indeterminate" for v, _, _ in ds) else "parsed-and-compared"
            kind = "+".join(sorted({e["kind"] for e in u.effects}))
        outcomes = sorted({v for v, _, _ in ds})
        key = (category, reasons, kind, outcomes)
        if groups and key == (groups[-1]["category"], groups[-1]["reason_codes"], groups[-1]["kind"], groups[-1]["outcomes"]):
            groups[-1]["last_unit"] = u.ordinal
            groups[-1]["end_line"] = u.end_line
            signatures[-1].append(u.sha256)
        else:
            groups.append({"first_unit": u.ordinal, "last_unit": u.ordinal, "start_line": u.start_line, "end_line": u.end_line, "category": category, "kind": kind, "outcomes": outcomes, "reason_codes": reasons})
            signatures.append([u.sha256])
    for group, hashes in zip(groups, signatures):
        group["unit_hashes_sha256"] = _sha(hashes)
    return groups


def compare_pair(pair_id: str, oracle_sql: str, postgresql_sql: str) -> dict[str, Any]:
    units = {"oracle": parse_script(oracle_sql, "oracle"), "postgresql": parse_script(postgresql_sql, "postgresql")}
    streams = {d: _effects(us) for d, us in units.items()}
    aligned = [_identity(e) for _, e in streams["oracle"]] == [_identity(e) for _, e in streams["postgresql"]]
    decisions: dict[str, dict[int, list[tuple[str, str, list[str]]]]] = {d: {} for d in units}
    deltas: list[dict[str, Any]] = []
    comparison_hashes: list[str] = []
    if aligned:
        for (lu, le), (ru, re) in zip(streams["oracle"], streams["postgresql"]):
            if le["kind"] == "unparsed":
                continue
            result = compare_effect(le, re)
            for dialect, unit in (("oracle", lu), ("postgresql", ru)):
                decisions[dialect].setdefault(unit.ordinal, []).append(result)
            comparison_hashes.append(_sha([le, re, result]))
            # Retain measured unequal structured values, never claim opaque-token
            # differences are semantic divergences. Context snippets are MS70 work.
            if le["value"] != re["value"] and le["kind"] not in {"insert", "update", "delete"}:
                deltas.append({"effect": list(_identity(le)), "oracle_lines": [lu.start_line, lu.end_line], "postgresql_lines": [ru.start_line, ru.end_line], "oracle_value": le["value"], "postgresql_value": re["value"], "verdict": result[0], "compatibility_class": result[1], "reason_codes": result[2]})
    else:
        for dialect, stream in streams.items():
            for u, e in stream:
                if u.parsed:
                    decisions[dialect].setdefault(u.ordinal, []).append(("indeterminate", CompatibilityClass.POLICY_DECISION_REQUIRED.value, sorted(set(e["reasons"] + ["ordered-effect-alignment-required"]))))
    segments = {d: _segments(us, decisions[d]) for d, us in units.items()}
    coverage = {d: _coverage(ss) for d, ss in segments.items()}
    verdicts = [v for ds in decisions.values() for results in ds.values() for v, _, _ in results]
    unresolved = any(c["unparsed"] or c["parsed-but-indeterminate"] for c in coverage.values())
    verdict = "divergent" if "divergent" in verdicts else ("equivalent" if aligned and verdicts and not unresolved else "indeterminate")
    classification = (CompatibilityClass.LOSSY if verdict == "divergent" else CompatibilityClass.NORMALIZED_EQUIVALENT if verdict == "equivalent" else CompatibilityClass.UNSUPPORTED if any(c["unparsed"] for c in coverage.values()) else CompatibilityClass.POLICY_DECISION_REQUIRED).value
    return seal({
        "pair_id": pair_id, "verdict": verdict, "compatibility_class": classification,
        "ordered_effects_aligned": aligned, "coverage": coverage,
        "segments": segments, "declared_differences": deltas,
        "compared_effects_sha256": _sha(comparison_hashes),
        "compared_effect_count": len(comparison_hashes),
        "maintenance_provenance": "not-classified",
    })


def _totals(results: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = Counter(r["verdict"] for r in results)
    coverage = {d: {k: sum(r["coverage"][d][k] for r in results) for k in ("input_units", "administrative_units_excluded", "sql_units", *CATEGORIES)} for d in ("oracle", "postgresql")}
    combined = {k: sum(c[k] for c in coverage.values()) for k in coverage["oracle"]}
    return {"pairs": len(results), "verdicts": {v: verdicts[v] for v in ("equivalent", "divergent", "indeterminate")}, "coverage_by_dialect": coverage, "coverage_combined": combined, "decided_sql_unit_fraction": round(combined["parsed-and-compared"] / combined["sql_units"], 8) if combined["sql_units"] else 0.0, "flagged_pairs": sum(r["verdict"] != "equivalent" for r in results)}


def _bindings(project_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {"pairing_manifest_sha256": manifest["content_sha256"], "source_commit": manifest["source"]["commit"], "source_tree": manifest["source"]["tree"], "policy_sha256": policy()["content_sha256"], "semantic_core_sha256": _read(project_root / SEMANTIC_CORE_PATH)["content_sha256"], "implementation_logical_sha256": {p: source_hashes(project_root / p)[0] for p in CODE_PATHS}, "schema_logical_sha256": source_hashes(project_root / SCHEMA_PATH)[0]}


def _report(scope: str, results: list[dict[str, Any]], bindings: dict[str, Any], helper: dict[str, Any], pilot_hash: str | None) -> dict[str, Any]:
    return seal({"schema_version": VERSION, "artifact_type": "lightyear-idempiere-semantic-comparison", "milestone": 69, "project_id": PROJECT_ID, "scope": scope, "bindings": bindings, "helper_definition": helper, "pilot_content_sha256": pilot_hash, "statistics": _totals(results), "results": results, "model_calls": 0, "claims": CLAIMS})


def build_stage2_artifacts(project_root: Path, source_root: Path) -> dict[str, dict[str, Any]]:
    errors = validate_stage1_artifacts(project_root, source_root=source_root)
    if errors:
        raise ValueError("Stage 1 admission failed: " + ", ".join(errors))
    manifest = _read(project_root / MANIFEST_PATH)
    bindings = _bindings(project_root, manifest)
    helper = {"path": HELPER_PATH, "source_commit": PINNED_COMMIT, "logical_sha256": source_hashes(source_root / HELPER_PATH)[0], "deployment_and_historical_version_verified": False}
    pilot_pairs = [p for p in manifest["pairs"] if "order-to-cash" in p["pilot_slices"]]
    rest = [p for p in manifest["pairs"] if "order-to-cash" not in p["pilot_slices"]]

    def run(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for pair in pairs:
            texts = {}
            for dialect in ("oracle", "postgresql"):
                raw = normalize_logical_source((source_root / pair[dialect]["path"]).read_bytes())
                if hashlib.sha256(raw).hexdigest() != pair[dialect]["logical_sha256"]:
                    raise ValueError("Source changed during comparison: " + pair[dialect]["path"])
                texts[dialect] = raw.decode("utf-8", errors="strict")
            results.append(compare_pair(pair["pair_id"], texts["oracle"], texts["postgresql"]))
        return results

    # Pilot is computed and sealed before the first nonpilot pair is read.
    pilot = _report("order-to-cash-pilot", run(pilot_pairs), bindings, helper, None)
    results = pilot["results"] + run(rest)
    report = _report("all-current-pairs", results, bindings, helper, pilot["content_sha256"])
    receipt = build_receipt(pilot, report)
    return {POLICY_PATH.name: policy(), PILOT_PATH.name: pilot, REPORT_PATH.name: report, RECEIPT_PATH.name: receipt}


def build_receipt(pilot: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    return seal({
        "schema_version": VERSION, "artifact_type": "lightyear-idempiere-semantic-comparison-receipt", "milestone": 69, "project_id": PROJECT_ID,
        "bindings": report["bindings"], "pilot_sha256": pilot["content_sha256"], "comparison_sha256": report["content_sha256"],
        "status": "bounded-sweep-complete-with-open-findings", "statistics": report["statistics"],
        "execution_order": [{"scope": "order-to-cash-pilot", "pairs": len(pilot["results"])}, {"scope": "remaining-current-pairs", "pairs": len(report["results"]) - len(pilot["results"])}],
        "station_usage": {"planner": "not-called-ms70-only", "analyst": "not-called-ms70-only", "builder": "not-used-audit-does-not-generate", "verifier": "deterministic-source-and-contract-validation", "model_calls": 0},
        "ms70_handoff": {"flagged_pair_ids": [r["pair_id"] for r in report["results"] if r["verdict"] != "equivalent"], "source_ranges": "stage2-comparison.json/results/segments; pair_id resolves paths and hashes in the MS68 manifest", "requires_bounded_context_and_budget_admission": True, "work_orders_created": 0, "model_verdict_authority": False, "ready_for_unattended_model_sweep": False},
        "claims": CLAIMS,
    })


def validate_stage2_artifacts(project_root: Path, *, source_root: Path | None = None, artifacts: dict[str, Any] | None = None) -> list[str]:
    """Offline verifies integrity/accounting, source-bound additionally replays SQL.

    An unsigned hash cannot authenticate evidence. Re-sealed semantic forgery is
    rejected by source-bound replay, not advertised as prevented by offline checks.
    """
    errors = validate_stage1_artifacts(project_root)
    try:
        docs = artifacts if artifacts is not None else {p.name: _read(project_root / p) for p in (POLICY_PATH, PILOT_PATH, REPORT_PATH, RECEIPT_PATH)}
        if docs[POLICY_PATH.name] != policy():
            errors.append("stage2-policy-drift")
        manifest = _read(project_root / MANIFEST_PATH)
        expected_bindings = _bindings(project_root, manifest)
        pilot = docs[PILOT_PATH.name]
        report = docs[REPORT_PATH.name]
        receipt = docs[RECEIPT_PATH.name]
        pilot_pairs = [p for p in manifest["pairs"] if "order-to-cash" in p["pilot_slices"]]
        full_pairs = pilot_pairs + [p for p in manifest["pairs"] if "order-to-cash" not in p["pilot_slices"]]
        for document, pairs, scope in ((pilot, pilot_pairs, "order-to-cash-pilot"), (report, full_pairs, "all-current-pairs")):
            if document["content_sha256"] != content_hash(document):
                errors.append("stage2-report-hash-invalid")
            if document["bindings"] != expected_bindings:
                errors.append("stage2-binding-drift")
            if document["artifact_type"] != "lightyear-idempiere-semantic-comparison" or document["project_id"] != PROJECT_ID or document["milestone"] != 69 or document["scope"] != scope or document["schema_version"] != VERSION:
                errors.append("stage2-identity-invalid")
            if document["claims"] != CLAIMS or document["model_calls"] != 0:
                errors.append("stage2-unsupported-claim")
            if [r["pair_id"] for r in document["results"]] != [p["pair_id"] for p in pairs]:
                errors.append("stage2-pair-denominator-or-order-drift")
            if document["statistics"] != _totals(document["results"]):
                errors.append("stage2-statistics-invalid")
            helper = document["helper_definition"]
            if helper.get("path") != HELPER_PATH or helper.get("source_commit") != PINNED_COMMIT or helper.get("deployment_and_historical_version_verified") is not False or not re.fullmatch(r"[0-9a-f]{64}", helper.get("logical_sha256", "")):
                errors.append("stage2-helper-boundary-invalid")
            pair_sources = {p["pair_id"]: p for p in pairs}
            for result in document["results"]:
                if result["content_sha256"] != content_hash(result):
                    errors.append("stage2-pair-hash-invalid")
                if result["verdict"] not in {"equivalent", "divergent", "indeterminate"} or result["compatibility_class"] not in {c.value for c in CompatibilityClass} or result["maintenance_provenance"] != "not-classified":
                    errors.append("stage2-pair-verdict-or-provenance-invalid")
                for dialect in ("oracle", "postgresql"):
                    segments = result["segments"][dialect]
                    next_unit = 1
                    previous_line = 0
                    for segment in segments:
                        if segment["first_unit"] != next_unit or segment["last_unit"] < next_unit or segment["category"] not in (*CATEGORIES, "administrative-excluded") or not 1 <= segment["start_line"] <= segment["end_line"] or segment["start_line"] < previous_line:
                            errors.append("stage2-segment-accounting-invalid")
                        next_unit = segment["last_unit"] + 1
                        previous_line = segment["end_line"]
                        if segment["category"] == "parsed-and-compared" and (not segment["outcomes"] or "indeterminate" in segment["outcomes"]):
                            errors.append("stage2-coverage-promotion-invalid")
                        if segment["end_line"] > pair_sources[result["pair_id"]][dialect]["lines"] + 1:
                            errors.append("stage2-source-range-invalid")
                        if segment["category"] == "administrative-excluded" and (segment["outcomes"] or segment["reason_codes"] or segment["kind"] != "client-or-registration"):
                            errors.append("stage2-administrative-exclusion-invalid")
                        if segment["category"] == "parsed-but-indeterminate" and ("indeterminate" not in segment["outcomes"] or not segment["reason_codes"]):
                            errors.append("stage2-indeterminate-reason-missing")
                        if segment["category"] == "unparsed" and (segment["outcomes"] or not segment["reason_codes"] or segment["kind"] != "unparsed"):
                            errors.append("stage2-unparsed-promotion-invalid")
                    if result["coverage"][dialect] != _coverage(segments):
                        errors.append("stage2-coverage-invalid")
                all_segments = result["segments"]["oracle"] + result["segments"]["postgresql"]
                divergent = any("divergent" in s["outcomes"] for s in all_segments)
                unresolved = any(s["category"] in {"unparsed", "parsed-but-indeterminate"} for s in all_segments)
                calculated = "divergent" if divergent else "equivalent" if not unresolved and result["compared_effect_count"] > 0 and result["ordered_effects_aligned"] else "indeterminate"
                if result["verdict"] != calculated:
                    errors.append("stage2-verdict-promotion-invalid")
                classification = (CompatibilityClass.LOSSY if calculated == "divergent" else CompatibilityClass.NORMALIZED_EQUIVALENT if calculated == "equivalent" else CompatibilityClass.UNSUPPORTED if any(s["category"] == "unparsed" for s in all_segments) else CompatibilityClass.POLICY_DECISION_REQUIRED).value
                if result["compatibility_class"] != classification:
                    errors.append("stage2-compatibility-class-invalid")
        if report["results"][:len(pilot["results"])] != pilot["results"] or report["pilot_content_sha256"] != pilot["content_sha256"] or pilot["pilot_content_sha256"] is not None:
            errors.append("stage2-pilot-before-sweep-binding-invalid")
        if report["helper_definition"] != pilot["helper_definition"]:
            errors.append("stage2-helper-binding-drift")
        if receipt != build_receipt(pilot, report):
            errors.append("stage2-receipt-invalid")
        if source_root is not None:
            rebuilt = build_stage2_artifacts(project_root, source_root)
            if docs != rebuilt:
                errors.append("stage2-source-replay-mismatch")
    except (KeyError, TypeError, ValueError, OSError, UnicodeError) as exc:
        errors.append("stage2-malformed-artifact: " + str(exc))
    return sorted(set(errors))
