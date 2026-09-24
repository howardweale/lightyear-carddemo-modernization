"""Complete cause accounting, conservative proposal scopes and measured rerun deltas."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from .contracts import (MAX_CASES, MAX_RECORDS, MAX_UNITS, count, digest, exact,
                        implementation, label, require, seal, sha, verify)

OPEN = {"indeterminate", "unsupported"}
STATUS = OPEN | {"decided", "excluded"}
VERDICTS = {"equivalent", "divergent", "indeterminate"}

# These are review hypotheses, never executable normalizers or semantic waivers.
POLICIES = {
    "character-empty-string-length-and-collation-policy": (
        "Character representation policy", "Distinguish structural padding from meaningful text, and preserve empty-string, NULL, length and collation behavior.",
        ["Column-level character domains and encoding", "Positive and negative examples for padding, NULL, empty strings and collation"]),
    "empty-string-null-domain": (
        "Empty-string and NULL policy", "Admit a mapping only for a domain whose contract makes empty strings and NULL observationally equivalent.",
        ["Nullability and consumer behavior", "Counterexamples proving meaningful empty strings remain distinct"]),
    "datetime-precision-range-and-zone-policy": (
        "Date and time representation policy", "Compare an explicitly admitted time domain without discarding time-of-day, zone or precision.",
        ["Field-level precision, timezone and valid range", "Boundary samples including daylight-saving changes and non-midnight times"]),
    "unbounded-or-nonportable-numeric-domain": (
        "Exact numeric domain policy", "Constrain precision, scale and special values before considering an exact numeric representation mapping.",
        ["Precision, scale and range constraints", "Overflow, fractional and special-value counterexamples"]),
    "type-domain-policy-required": (
        "Type domain policy", "Specify the source and target value domains before defining a lossless representation mapping.",
        ["Source and target type definitions", "Paired boundary values and rejected values"]),
    "unsupported decimal representation": (
        "Exact decimal representation policy", "Consider an additional decimal decoder that preserves every digit and rejects rounding, overflow and sub-cent changes.",
        ["Documented field encoding and currency scale", "Equal-value formatting examples and unequal-value counterexamples"]),
}


def cause(reason):
    bare = reason.split(":", 1)[1] if reason.startswith(("source:", "target:")) else reason
    if bare in POLICIES:
        title, hypothesis, evidence = POLICIES[bare]
        return {"kind": "normalization-proposal", "title": title, "hypothesis": hypothesis, "required_evidence": evidence}
    if "alignment" in bare or "scope mismatch" in bare:
        kind, title = "alignment-work", "Establish matching operations and observation scope"
    elif bare.startswith("missing-") or bare == "no-comparable-sql-units":
        kind, title = "evidence-acquisition", "Supply the missing counterpart or comparable observations"
    elif (bare.startswith("unsupported") or bare in {"unconsumed-syntax", "procedural-block", "identifier-required",
            "insert-column-value-arity", "missing-statement-terminator"} or "unterminated" in bare):
        kind, title = "parser-or-adapter-work", "Extend the parser or observation decoder with conformance tests"
    elif any(word in bare for word in ("context", "catalog", "baseline", "expression", "constraint", "index-")):
        kind, title = "semantic-evidence", "Establish the schema, session and runtime semantics"
    else:
        kind, title = "unclassified-investigation", "Investigate the unrecognized cause without assuming a normalization"
    return {"kind": kind, "title": title, "hypothesis": None,
            "required_evidence": ["Source-bound reproducer", "A test that remains unresolved or divergent when the proposed fix is invalid"]}


def validate_snapshot(snapshot):
    require(isinstance(snapshot, dict), "Invalid calibration snapshot")
    for key in ("corpus_id", "adapter"):
        label(snapshot[key])
    sha(snapshot["corpus_sha256"])
    cases, rows = snapshot["cases"], snapshot["records"]
    require(isinstance(cases, list) and 0 < len(cases) <= MAX_CASES, "Invalid case denominator")
    require(isinstance(rows, list) and len(rows) <= MAX_RECORDS, "Invalid record count")
    case_map = {}
    for case in cases:
        exact(case, {"id", "verdict"})
        label(case["id"])
        require(case["id"] not in case_map and case["verdict"] in VERDICTS, "Invalid or duplicate case")
        case_map[case["id"]] = case["verdict"]
    identities, by_case = set(), defaultdict(list)
    total = 0
    intervals = defaultdict(list)
    for row in rows:
        exact(row, {"id", "case_id", "lane", "kind", "status", "outcomes", "reason_codes", "units", "source"})
        for key in ("id", "case_id", "lane", "kind"):
            label(row[key])
        require(row["id"] not in identities and row["case_id"] in case_map, "Unknown case or duplicate evidence record")
        identities.add(row["id"])
        require(row["status"] in STATUS, "Unknown record status")
        total += count(row["units"])
        require(isinstance(row["source"], dict), "Missing evidence locator")
        first, last = count(row["source"].get("first_unit")), count(row["source"].get("last_unit"))
        require((first == last == row["units"] == 0) or (first > 0 and last >= first and row["units"] == last - first + 1),
                "Unit range does not match weight")
        if first:
            intervals[(row["case_id"], row["lane"])].append((first, last))
        reasons, outcomes = row["reason_codes"], row["outcomes"]
        require(isinstance(reasons, list) and len(reasons) <= 100 and len(set(reasons)) == len(reasons), "Invalid reasons")
        for reason in reasons:
            label(reason)
        require(isinstance(outcomes, list) and set(outcomes) <= VERDICTS, "Invalid unit outcomes")
        if row["status"] in OPEN:
            require(bool(reasons), "Every unresolved record needs a cause")
        elif row["status"] == "decided":
            require(row["units"] > 0 and bool(outcomes) and "indeterminate" not in outcomes, "Invalid decided coverage")
        else:
            require(not reasons and not outcomes, "Excluded record cannot contain a verdict")
        by_case[row["case_id"]].append(row)
    require(total <= MAX_UNITS, "Unit denominator exceeds bound")
    for spans in intervals.values():
        cursor = 1
        for first, last in sorted(spans):
            require(first == cursor, "Overlapping or omitted unit range")
            cursor = last + 1
    for cid, verdict in case_map.items():
        members = by_case[cid]
        require(bool(members), "Case omitted from unit accounting")
        has_divergence = any("divergent" in r["outcomes"] for r in members)
        has_open = any(r["status"] in OPEN for r in members)
        expected = "divergent" if has_divergence else "indeterminate" if has_open or not any(r["status"] == "decided" for r in members) else "equivalent"
        require(verdict == expected, "Case verdict contradicts retained unit evidence")
    return snapshot


def summary(rows, cases):
    quantities = Counter()
    for row in rows:
        quantities[row["status"]] += row["units"]
    input_units = sum(quantities.values())
    in_scope = input_units - quantities["excluded"]
    decided = quantities["decided"]
    verdicts = Counter(case["verdict"] for case in cases)
    return {"input_units": input_units, "excluded_units": quantities["excluded"], "in_scope_units": in_scope,
            "decided_units": decided, "indeterminate_units": quantities["indeterminate"], "unsupported_units": quantities["unsupported"],
            "decidability": {"numerator": decided, "denominator": in_scope, "fraction": decided / in_scope if in_scope else None},
            "decided_fraction_of_all_input_units": decided / input_units if input_units else None,
            "cases": {"total": len(cases), **{v: verdicts[v] for v in sorted(VERDICTS)},
                      "decided": verdicts["equivalent"] + verdicts["divergent"],
                      "decision_fraction": (verdicts["equivalent"] + verdicts["divergent"]) / len(cases) if cases else None}}


def cluster(rows):
    groups, causes = defaultdict(list), defaultdict(list)
    for row in rows:
        if row["status"] not in OPEN:
            continue
        signature = (row["status"], row["kind"], tuple(sorted(row["reason_codes"])))
        groups[signature].append(row)
        for reason in row["reason_codes"]:
            causes[reason].append(row)
    clusters = []
    for (status, kind, reasons), members in sorted(groups.items()):
        clusters.append({"id": "cluster:" + digest([status, kind, reasons])[:24], "status": status, "kind": kind,
                         "reason_codes": list(reasons), "units": sum(r["units"] for r in members),
                         "cases": len({r["case_id"] for r in members}), "record_ids": sorted(r["id"] for r in members)})
    clusters.sort(key=lambda c: (-c["units"], c["id"]))
    cause_rows = []
    for reason, members in causes.items():
        cause_rows.append({"reason_code": reason, **cause(reason), "units": sum(r["units"] for r in members),
                           "cases": len({r["case_id"] for r in members}),
                           "sole_blocker_units": sum(r["units"] for r in members if r["reason_codes"] == [reason]),
                           "record_ids": sorted(r["id"] for r in members)})
    cause_rows.sort(key=lambda c: (-c["units"], c["reason_code"]))
    return clusters, cause_rows


def assess(snapshot, proposal):
    """Recompute all matches, including existing decisions; never simulate verdict promotion."""
    exact(proposal, {"schema_version", "artifact_type", "corpus_sha256", "gate_sha256", "title", "addresses",
                     "selector", "hypothesis", "required_evidence", "owner", "review_after", "status", "executable"})
    require(proposal["schema_version"] == "1.0" and proposal["artifact_type"] == "normalization-proposal" and
            proposal["status"] == "draft" and proposal["executable"] is False, "Only non-executable draft proposals are admitted")
    require(proposal["corpus_sha256"] == snapshot["corpus_sha256"] and
            proposal["gate_sha256"] == digest(snapshot["gate"]), "Proposal is stale or targets a different corpus/gate")
    label(proposal["title"])
    label(proposal["hypothesis"], 4000)
    evidence = proposal["required_evidence"]
    require(isinstance(evidence, list) and 1 <= len(evidence) <= 50, "Proposal needs evidence requirements")
    for item in evidence:
        label(item, 2000)
    for field in ("owner", "review_after"):
        require(proposal[field] is None or isinstance(proposal[field], str), "Invalid review field")
        if proposal[field] is not None:
            label(proposal[field])
    sel = proposal["selector"]
    exact(sel, {"lanes", "kinds", "case_ids"})
    rows = snapshot["records"]
    for field, universe in (("lanes", {r["lane"] for r in rows}), ("kinds", {r["kind"] for r in rows}),
                            ("case_ids", {c["id"] for c in snapshot["cases"]})):
        values = sel[field]
        if field == "case_ids" and values is None:
            continue
        require(isinstance(values, list) and bool(values) and len(values) == len(set(values)) and set(values) <= universe,
                "Selector must use explicit existing " + field)
    addresses = proposal["addresses"]
    require(isinstance(addresses, list) and bool(addresses) and len(addresses) == len(set(addresses)), "Invalid addressed causes")
    require(all(cause(r)["kind"] == "normalization-proposal" for r in addresses), "Parser and evidence gaps cannot become normalizations")
    matched = [r for r in rows if r["lane"] in sel["lanes"] and r["kind"] in sel["kinds"] and
               (sel["case_ids"] is None or r["case_id"] in sel["case_ids"])]
    targeted = [r for r in matched if r["status"] in OPEN and set(r["reason_codes"]) & set(addresses)]
    require(bool(targeted), "Proposal does not address an unresolved record in its scope")
    targeted_ids = {r["id"] for r in targeted}
    remaining = Counter()
    for row in targeted:
        for reason in set(row["reason_codes"]) - set(addresses):
            remaining[reason] += row["units"]
    blast = {"scoped_units": sum(r["units"] for r in matched), "scoped_cases": len({r["case_id"] for r in matched}),
             "targeted_unresolved_units": sum(r["units"] for r in targeted),
             "other_unresolved_units": sum(r["units"] for r in matched if r["status"] in OPEN and r["id"] not in targeted_ids),
             "already_decided_units": sum(r["units"] for r in matched if r["status"] == "decided"),
             "known_divergent_units": sum(r["units"] for r in matched if "divergent" in r["outcomes"]),
             "excluded_units": sum(r["units"] for r in matched if r["status"] == "excluded"),
             "units_with_no_other_recorded_blocker": sum(r["units"] for r in targeted if set(r["reason_codes"]) <= set(addresses)),
             "remaining_blocker_units_by_cause": dict(sorted(remaining.items())),
             "record_ids": sorted(r["id"] for r in matched), "target_record_ids": sorted(r["id"] for r in targeted),
             "predicted_decidability_gain": None,
             "boundary": "Observed scope only. Covering reason codes does not prove semantic validity or a future verdict."}
    return seal({"proposal_id": "proposal:" + digest(proposal)[:24], "entry": proposal, "blast_radius": blast,
                 "required_regressions": ["Rerun the complete bound corpus", "Preserve every existing divergence",
                                          "Test unequal values that a broad rule might collapse", "Keep raw evidence and residual blockers"],
                 "approval": "not-requested-or-granted", "ledger_changed": False})


def proposals(snapshot, causes):
    rows = {r["id"]: r for r in snapshot["records"]}
    result = []
    for item in causes:
        if item["kind"] != "normalization-proposal":
            continue
        members = [rows[rid] for rid in item["record_ids"]]
        entry = {"schema_version": "1.0", "artifact_type": "normalization-proposal",
                 "corpus_sha256": snapshot["corpus_sha256"], "gate_sha256": digest(snapshot["gate"]),
                 "title": item["title"], "addresses": [item["reason_code"]],
                 "selector": {"lanes": sorted({r["lane"] for r in members}), "kinds": sorted({r["kind"] for r in members}), "case_ids": None},
                 "hypothesis": item["hypothesis"], "required_evidence": item["required_evidence"],
                 "owner": None, "review_after": None, "status": "draft", "executable": False}
        result.append(assess(snapshot, entry))
    return sorted(result, key=lambda p: (-p["blast_radius"]["targeted_unresolved_units"], p["proposal_id"]))


def build_report(snapshot, minimum_decidability=None):
    validate_snapshot(snapshot)
    require(minimum_decidability is None or type(minimum_decidability) in {float, int} and 0 <= minimum_decidability <= 1,
            "Threshold must be a fraction between 0 and 1")
    snapshot = {**snapshot, "cases": sorted(snapshot["cases"], key=lambda c: c["id"]),
                "records": sorted(snapshot["records"], key=lambda r: (r["case_id"], r["lane"], r["source"].get("first_unit", 0), r["id"]))}
    counts = summary(snapshot["records"], snapshot["cases"])
    clusters, causes = cluster(snapshot["records"])
    records_by_lane = defaultdict(list)
    for row in snapshot["records"]:
        records_by_lane[row["lane"]].append(row)
    by_lane = {lane: summary(rows, []) for lane, rows in sorted(records_by_lane.items())}
    measured = counts["decidability"]["fraction"]
    threshold_status = "not-configured" if minimum_decidability is None else "no-comparable-units" if measured is None else "met" if measured >= minimum_decidability else "below-minimum"
    return seal({"schema_version": "1.0", "artifact_type": "lightyear-decidability-report", **snapshot,
                 "instrument": implementation({p.name: p for p in Path(__file__).parent.glob("*.py")}),
                 "summary": counts, "by_lane": by_lane, "clusters": clusters, "causes": causes,
                 "normalization_proposals": proposals(snapshot, causes),
                 "threshold": {"minimum_decidability": minimum_decidability, "status": threshold_status,
                               "boundary": "A coverage threshold never establishes equivalence or engagement readiness."},
                 "accounting": {"cluster_units": sum(c["units"] for c in clusters),
                                "unresolved_units": counts["indeterminate_units"] + counts["unsupported_units"],
                                "clusters_are_disjoint": True, "cause_counts_overlap": True,
                                "unit_basis": "SQL statements on each dialect side, or paired transfer observations; never lines of code"},
                 "claims": {"all_unresolved_records_clustered": True, "normalizations_applied": False,
                            "predicted_lift_is_measured": False, "whole_estate_equivalence": False,
                            "production_ready": False, "runtime_invocations": 0}})


def validate_report(report):
    verify(report)
    require(report.get("artifact_type") == "lightyear-decidability-report" and report.get("schema_version") == "1.0", "Unsupported report")
    validate_snapshot(report)
    # Recompute every derived field. A checksum alone cannot validate accounting.
    keys = ("corpus_id", "adapter", "corpus_sha256", "gate", "cases", "records", "provenance")
    rebuilt = build_report({k: report[k] for k in keys}, report["threshold"]["minimum_decidability"])
    require(set(report) == set(rebuilt), "Unknown or missing report fields")
    for key in rebuilt:
        if key not in {"content_sha256", "instrument"}:
            require(report[key] == rebuilt[key], "Derived report drift: " + key)
    require(isinstance(report["instrument"], dict) and bool(report["instrument"]), "Missing instrument identity")
    for value in report["instrument"].values():
        sha(value)
    return report


def compare_reports(before, after):
    validate_report(before)
    validate_report(after)
    require(before["adapter"] == after["adapter"] and before["corpus_sha256"] == after["corpus_sha256"],
            "Rerun comparison requires the same adapter and identical corpus content")
    old, new = ({c["id"]: c["verdict"] for c in report["cases"]} for report in (before, after))
    require(set(old) == set(new), "Rerun case denominator changed")
    transitions = Counter((old[cid], new[cid]) for cid in old)
    dangerous = sorted(cid for cid in old if old[cid] == "divergent" and new[cid] != "divergent")
    lost_decisions = sorted(cid for cid in old if old[cid] != "indeterminate" and new[cid] == "indeterminate")
    changes = [{"case_id": cid, "before": old[cid], "after": new[cid]} for cid in sorted(old) if old[cid] != new[cid]]
    b, a = before["summary"], after["summary"]
    old_rows, new_rows = ({r["id"]: r for r in report["records"]} for report in (before, after))
    same_layout = (set(old_rows) == set(new_rows) and all(
        old_rows[rid]["source"] == new_rows[rid]["source"] and old_rows[rid]["units"] == new_rows[rid]["units"]
        for rid in old_rows))
    unit_changes = [{"record_id": rid, "before": old_rows[rid]["status"], "after": new_rows[rid]["status"],
                     "before_outcomes": old_rows[rid]["outcomes"], "after_outcomes": new_rows[rid]["outcomes"]}
                    for rid in sorted(set(old_rows) & set(new_rows))
                    if old_rows[rid]["source"] == new_rows[rid]["source"] and
                    (old_rows[rid]["status"], old_rows[rid]["outcomes"]) != (new_rows[rid]["status"], new_rows[rid]["outcomes"])]
    lost_unit_decisions = [c["record_id"] for c in unit_changes if c["before"] == "decided" and c["after"] != "decided"]
    lost_unit_divergences = [c["record_id"] for c in unit_changes if "divergent" in c["before_outcomes"] and "divergent" not in c["after_outcomes"]]
    same_units = b["in_scope_units"] == a["in_scope_units"] and b["input_units"] == a["input_units"]
    fraction_delta = (a["decidability"]["fraction"] - b["decidability"]["fraction"]
                      if same_units and same_layout and a["in_scope_units"] else None)
    return seal({"schema_version": "1.0", "artifact_type": "lightyear-decidability-rerun",
                 "before_sha256": before["content_sha256"], "after_sha256": after["content_sha256"],
                 "corpus_sha256": before["corpus_sha256"], "gate_changed": digest(before["gate"]) != digest(after["gate"]),
                 "before": b, "after": a, "unit_denominator_unchanged": same_units,
                 "decidability_fraction_delta": fraction_delta, "unit_partition_unchanged": same_layout,
                 "changed_units": unit_changes, "lost_unit_decisions": lost_unit_decisions,
                 "unit_divergences_no_longer_reported": lost_unit_divergences,
                 "newly_decided_cases": sum(old[cid] == "indeterminate" and new[cid] != "indeterminate" for cid in old),
                 "transitions": [{"before": left, "after": right, "cases": n} for (left, right), n in sorted(transitions.items())],
                 "changed_cases": changes, "lost_decisions": lost_decisions, "divergences_no_longer_reported": dangerous,
                 "review_required": bool(dangerous or lost_decisions or lost_unit_decisions or lost_unit_divergences or not same_units or not same_layout),
                 "normalization_causality_established": False,
                 "boundary": "Measures two supplied gate runs on identical inputs. No causal attribution, automatic approval or verdict promotion."})
