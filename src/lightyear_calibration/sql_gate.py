"""Current calibration gate, separate from the immutable retained audit contract."""
from __future__ import annotations
from typing import Any
from lightyear_data.idempiere_comparison import (_effects, _identity, _segments, _coverage,
    _sha, compare_effect, CompatibilityClass, seal)
from .sql_parser import parse_script
from .sql_context import project


def compare_pair(pair_id: str, oracle_sql: str, postgresql_sql: str, *, context_case=None, context_enabled=False, prefix_alignment=True) -> dict[str, Any]:
    units = {"oracle": parse_script(oracle_sql, "oracle"), "postgresql": parse_script(postgresql_sql, "postgresql")}
    if context_case is not None:
        for lane, members in units.items():
            # A per-file entry snapshot expires at the first schema/session or
            # unknown operation. Never reuse it across a migration mutation.
            valid = True
            for unit in members:
                if not unit.parsed: valid = False
                if unit.parsed and not unit.administrative:
                    if len(unit.effects)==1 and unit.effects[0]['kind'] in ('insert','update','delete'):
                        unit.effects = [project(unit,lane,context_case,context_enabled and valid)]
                    else: valid = False
    streams = {d: _effects(us) for d, us in units.items()}
    aligned = [_identity(e) for _, e in streams["oracle"]] == [_identity(e) for _, e in streams["postgresql"]]
    decisions: dict[str, dict[int, list[tuple[str, str, list[str]]]]] = {d: {} for d in units}
    deltas: list[dict[str, Any]] = []
    comparison_hashes: list[str] = []
    paired = list(zip(streams['oracle'],streams['postgresql']))
    prefix = 0
    if aligned:
        prefix = len(paired)
    elif prefix_alignment:
        # A positional prefix is unambiguous. Stop at the first unknown or
        # identity mismatch; never search ahead, reorder or discard an effect.
        for (_, left), (_, right) in paired:
            if left['kind']=='unparsed' or right['kind']=='unparsed' or _identity(left)!=_identity(right):break
            prefix += 1
    if prefix:
        for (lu, le), (ru, re) in paired[:prefix]:
            if le["kind"] == "unparsed":
                continue
            if le['kind'] in ('insert','update','delete') and context_case is not None:
                lv,rv=le['value'],re['value']
                # A changed predicate/domain is not a proved semantic mismatch.
                if 'domains' in lv and 'domains' in rv:
                    if lv['domains']!=rv['domains']:
                        le['reasons'].append('paired-column-domain-context-required')
                    if le['kind']=='delete' and lv['dml']!=rv['dml'] or le['kind']=='update' and lv['dml']['predicate']!=rv['dml']['predicate']:
                        le['reasons'].append('predicate-equivalence-context-required')
            result = compare_effect(le, re)
            for dialect, unit in (("oracle", lu), ("postgresql", ru)):
                decisions[dialect].setdefault(unit.ordinal, []).append(result)
            comparison_hashes.append(_sha([le, re, result]))
            # Retain measured unequal structured values, never claim opaque-token
            # differences are semantic divergences. Context snippets are MS70 work.
            if le["value"] != re["value"] and le["kind"] not in {"insert", "update", "delete"}:
                deltas.append({"effect": list(_identity(le)), "oracle_lines": [lu.start_line, lu.end_line], "postgresql_lines": [ru.start_line, ru.end_line], "oracle_value": le["value"], "postgresql_value": re["value"], "verdict": result[0], "compatibility_class": result[1], "reason_codes": result[2]})
    if not aligned:
        for dialect, stream in streams.items():
            for u, e in stream[prefix:]:
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
