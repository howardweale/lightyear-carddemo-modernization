"""Project admitted verdict evidence into actions without changing its conclusions.

This module has no model, process runner, database writer, or approval constructor.
Unknown reasons are engineering backlog, never an implicit business exception.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json

from lightyear_data.contracts import content_hash, seal
from lightyear_data.idempiere_comparison import REPORT_PATH, validate_stage2_artifacts
from lightyear_data.idempiere_divergence import MANIFEST_PATH, validate_stage1_artifacts
from lightyear_common.io import source_hashes
from .policy import CATALOG, parse_policy

POLICY_PATH = Path("control-tower/workflow-policy.json")
IMPLEMENTATION_PATHS = ("src/lightyear_workflow/policy.py", "src/lightyear_workflow/planner.py",
                        "src/lightyear_workflow/artifacts.py", "src/lightyear_workflow/__main__.py")
SUB_VERDICTS = ("no-output", "unparsed", "undecidable", "uncovered", "unauthorised")
# Exact reason codes, not substring matching or an agent's classification.
POLICY_REASONS = frozenset({
    "character-empty-string-length-and-collation-policy", "datetime-precision-range-and-zone-policy",
    "unbounded-or-nonportable-numeric-domain", "empty-string-null-domain", "type-domain-policy-required",
    "isolation-policy-required", "sequence-state-policy-required",
})
CONTEXT_REASONS = frozenset({
    "dml-schema-trigger-and-coercion-context-required", "baseline-object-required",
    "constraint-column-domain-required", "helper-catalog-and-dependent-view-effects",
    "index-null-collation-and-column-domain-required", "default-coercion-context-required",
    "path-uncovered", "corpus-path-uncovered",
})
ACCESS_REASONS = {
    "zos-baseline-required": "require-authorised-baseline",
    "authorized-baseline-required": "require-authorised-baseline",
    "customer-authorization-required": "require-customer-authorization",
    "approved-provider-required": "require-approved-provider",
    "ms67-platform-qualification": "require-authorised-baseline",
}
NO_OUTPUT_REASONS = frozenset({"no-output", "candidate-no-output", "candidate-run-failed"})
QUESTIONS = {
    "datetime-precision-range-and-zone-policy": "Oracle DATE can retain seconds; PostgreSQL DATE does not. What precision and time-zone behavior must this scope preserve? Any accepted loss needs an explicit signed normalization.",
    "character-empty-string-length-and-collation-policy": "Must this scope preserve empty strings, NULL, character lengths and collation exactly? Describe any acceptable difference.",
    "unbounded-or-nonportable-numeric-domain": "What numeric range and precision does the business require? Is any loss acceptable within this exact scope?",
}


def classify_reason(reason: str, category: str) -> str:
    if category == "unparsed":
        return "unparsed"
    if reason in NO_OUTPUT_REASONS:
        return "no-output"
    if reason in ACCESS_REASONS:
        return "unauthorised"
    if reason in POLICY_REASONS:
        return "undecidable"
    if reason in CONTEXT_REASONS:
        return "uncovered"
    # Includes opaque expressions, unsupported syntax, and ordered alignment:
    # these are our missing analysis capability, not a permanent database limit.
    return "unparsed"


def _action(kind: str, reasons: list[str], evidence: list[dict], record: dict, policy: dict) -> dict:
    spec = CATALOG[kind]
    action_class = spec.action_class
    if action_class == "autonomous" and policy["autonomy"][kind] == "always-ask":
        action_class = "approval-required"
    owner = policy["owners"].get(spec.owner_role)
    action = {
        "kind": kind, "class": action_class, "policy_mode": policy["autonomy"][kind],
        "owner_role": spec.owner_role, "owner": owner, "owner_assignment_required": owner is None,
        "entity_id": record["pair_id"], "source_verdict": record["verdict"],
        "source_verdict_sha256": record["content_sha256"], "reason_codes": reasons,
        "evidence": evidence, "status": "proposed", "execution_enabled": False,
        "preconditions": list(spec.preconditions),
        "impact": {"sql_units": sum(e["unit_count"] for e in evidence),
                   "files": len({e["path"] for e in evidence}),
                   "suppressed_comparisons": 0, "suppression_estimate": "not-assessed"},
        "decision_provenance": [],
    }
    if action_class == "approval-required":
        action.update({
            "question": next((QUESTIONS[r] for r in reasons if r in QUESTIONS),
                             "Which business behavior must this scope preserve? Describe any intentional difference for a scoped human decision."),
            "decision_kind": "normalization" if kind == "propose-normalization" else kind,
            "signature_enabled": False,
            "signature_blocker": "Exact proposed terms, measured blast radius and the bound decision workflow are required before signing.",
            "if_approved": "A signed, scoped decision may authorize a later deterministic rerun. Approval alone does not establish equivalence.",
            "if_refused": "No exception is granted. Existing divergence remains divergent; indeterminate remains unresolved until evidence decides it.",
        })
    action["id"] = "action:" + content_hash(action)
    return action


def plan_pair(record: dict, source_pair: dict, policy: dict) -> dict:
    """One input verdict remains one output verdict; evidence ranges retain their identity."""
    policy = parse_policy(policy)
    if record.get("content_sha256") != content_hash(record):
        raise ValueError("Invalid source verdict hash")
    verdict = record["verdict"]
    if verdict not in {"equivalent", "divergent", "indeterminate"} or source_pair["pair_id"] != record["pair_id"]:
        raise ValueError("Unknown verdict or mismatched source identity")
    buckets = defaultdict(list)
    reasons_by_kind = defaultdict(set)
    subtype_units = Counter()
    subtypes = set()
    for dialect in ("oracle", "postgresql"):
        source = source_pair[dialect]
        for segment in record["segments"][dialect]:
            category = segment["category"]
            if category == "administrative-excluded":
                continue
            divergent = "divergent" in segment["outcomes"]
            if category == "parsed-and-compared" and not divergent:
                continue
            reasons = segment["reason_codes"] or (["observed-divergence"] if divergent else ["unclassified-analysis-gap"])
            types = {classify_reason(r, category) for r in reasons} if not divergent else set()
            subtypes.update(types)
            units = segment["last_unit"] - segment["first_unit"] + 1
            # Exclusive attribution for coverage accounting, multiple reasons retained.
            primary = next((s for s in SUB_VERDICTS if s in types), None)
            if primary:
                subtype_units[primary] += units
            evidence = {"dialect": dialect, "path": source["path"], "source_sha256": source["logical_sha256"],
                        "start_line": segment["start_line"], "end_line": segment["end_line"],
                        "first_unit": segment["first_unit"], "last_unit": segment["last_unit"],
                        "unit_count": units, "unit_hashes_sha256": segment["unit_hashes_sha256"]}
            kinds = defaultdict(set)
            if divergent:
                kinds["classify-intentional-change"].update(reasons)
            else:
                for reason in reasons:
                    subtype = classify_reason(reason, category)
                    kind = {"no-output": "rerun", "unparsed": "require-parser-work",
                            "undecidable": "propose-normalization", "uncovered": "require-customer-authorization",
                            "unauthorised": ACCESS_REASONS.get(reason, "require-customer-authorization")}[subtype]
                    kinds[kind].add(reason)
            for kind, rs in kinds.items():
                buckets[kind].append(evidence)
                reasons_by_kind[kind].update(rs)
    if verdict == "indeterminate" and not any(record["coverage"][d]["input_units"] for d in ("oracle", "postgresql")):
        subtypes.add("no-output")
        buckets["rerun"] = []
        reasons_by_kind["rerun"].add("candidate-no-output")
    actions = [_action(kind, sorted(reasons_by_kind[kind]), evidence, record, policy) for kind, evidence in sorted(buckets.items())]
    return {"entity_id": record["pair_id"], "verdict": verdict,
            "source_verdict_sha256": record["content_sha256"], "evidence_class": "static-declared-effects",
            "observations": 0, "agreement": None,
            "sub_verdict": next((s for s in SUB_VERDICTS if s in subtypes), None) if verdict == "indeterminate" else None,
            "sub_verdicts": [s for s in SUB_VERDICTS if s in subtypes],
            "exclusive_unresolved_units": {s: subtype_units[s] for s in SUB_VERDICTS},
            "actions": actions, "stop_reason": "actions-emitted-not-executed" if actions else
            "no-in-scope-effects" if verdict == "indeterminate" else "bounded-static-verdict-complete"}


def _summary(results: list[dict]) -> dict:
    actions = [a for r in results for a in r["actions"]]
    classes = Counter(a["class"] for a in actions)
    return {
        "entities": len(results), "actions": len(actions),
        "source_verdicts": dict(Counter(r["verdict"] for r in results)),
        "actions_by_class": {c: classes[c] for c in ("autonomous", "approval-required", "blocked")},
        "autonomous_actions_planned": classes["autonomous"],
        "resolved_autonomously": 0, "awaiting_decision_design": classes["approval-required"],
        "blocked_on_access": sum(a["class"] == "blocked" and a["kind"] != "require-parser-work" for a in actions),
        "blocked_on_parser": sum(a["kind"] == "require-parser-work" for a in actions),
        "owner_assignment_required": sum(a["owner_assignment_required"] for a in actions),
        "converged_cannot_improve": 0,
        "entities_without_next_action": sum(not r["actions"] for r in results),
        "exclusive_unresolved_units": {s: sum(r["exclusive_unresolved_units"][s] for r in results) for s in SUB_VERDICTS},
        "parser_units_reported_by_comparator": None,
        "counting_basis": "Action counts can overlap entities. SQL-unit taxonomy is exclusive with priority: no-output, unparsed, undecidable, uncovered, unauthorised. No execution or convergence is claimed.",
    }


def build_plan(root: Path, policy: dict) -> dict:
    policy = parse_policy(policy)
    errors = validate_stage1_artifacts(root) + validate_stage2_artifacts(root)
    if errors:
        raise ValueError("Source evidence admission failed: " + ", ".join(sorted(set(errors))))
    report = json.loads((root / REPORT_PATH).read_text(encoding="utf-8"))
    manifest = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    pairs = {p["pair_id"]: p for p in manifest["pairs"]}
    results = [plan_pair(r, pairs[r["pair_id"]], policy) for r in report["results"]]
    summary = _summary(results)
    summary["parser_units_reported_by_comparator"] = report["statistics"]["coverage_combined"]["unparsed"]
    return seal({
        "schema_version": "1.0", "artifact_type": "lightyear-evidence-action-plan", "mode": "emit-only",
        "project_id": report["project_id"],
        "bindings": {"source_report": REPORT_PATH.as_posix(), "source_report_sha256": report["content_sha256"],
                     "manifest_sha256": manifest["content_sha256"], "source_commit": report["bindings"]["source_commit"],
                     "policy_sha256": content_hash(policy),
                     "implementation_sha256": {p: source_hashes(root / p)[0] for p in IMPLEMENTATION_PATHS}},
        "policy": policy, "results": results, "summary": summary,
        "execution": {"actions_executed": 0, "model_calls": 0, "decisions_created": 0,
                      "ledger_entries_created": 0, "ledger_entries_applied": 0, "claims_promoted": 0},
        "convergence": {"measured": False, "reason": "Step 1 emits actions; no execution loop exists."},
    })


def markdown_report(plan: dict) -> str:
    s = plan["summary"]
    rows = [("Resolved autonomously", 0), ("Autonomous actions planned", s["autonomous_actions_planned"]),
            ("Approval proposals (signature workflow pending)", s["awaiting_decision_design"]),
            ("Blocked on access / authorization", s["blocked_on_access"]),
            ("Blocked on our parser / analysis", s["blocked_on_parser"]),
            ("Converged, cannot improve", 0)]
    lines = ["# Control Tower action plan — Step 1", "", "The headless engine emitted this plan. No actions executed and no decisions or claims changed.", "",
             "| Action category | Count |", "|---|---:|"]
    lines += [f"| {label} | {count:,} |" for label, count in rows]
    lines += ["", s["counting_basis"], "", f"Source: {s['entities']:,} pairs. Original comparator unparsed SQL units: {s['parser_units_reported_by_comparator']:,}.",
              f"Actions without an assigned accountable person or team: {s['owner_assignment_required']:,}. These are explicitly unassigned, not owned by an invented customer contact.",
              "", "## Unresolved SQL units by primary cause", "", "| Cause | SQL units |", "|---|---:|"]
    lines += [f"| {kind} | {count:,} |" for kind, count in s["exclusive_unresolved_units"].items()]
    lines += ["", "Parser/analysis backlog also includes opaque expressions and ordered alignment. It is broader than the comparator's grammar-only unparsed count. Reasons and all source ranges remain available in the JSON plan.",
              "", "Approving a proposal would authorize only its specified terms and scope; it would not automatically establish equivalence. Refusal cannot turn missing evidence into a proven divergence.",
              "", f"Source comparison SHA-256: `{plan['bindings']['source_report_sha256']}`", f"Plan SHA-256: `{plan['content_sha256']}`", ""]
    return "\n".join(lines)
