"""Closed disclosure projections. Raw observations/captures never enter the UI."""

from datetime import datetime, timezone, timedelta
from .requests import read_json, confined


def workspace_status(value):
    """Status sharing exposes aggregate fields only, never journey/estate details."""
    result = {k: value[k] for k in ("scope", "configured", "counts") if k in value}
    result["slice"] = {
        k: value.get("slice", {})[k]
        for k in ("id", "lane_pair")
        if k in value.get("slice", {})
    }
    result["progress"] = {
        k: value.get("progress", {})[k]
        for k in ("state", "completed", "total")
        if k in value.get("progress", {})
    }
    return result


def evidence_view(root, item):
    if item.get("scope") == "factory":
        from .factory_policy import load_contract
        contract = load_contract(root, item)
        # Closed policy validation occurs before this explicit projection.
        keys = ("schema", "kind", "program", "sources", "details")
        return {"disclosure": "public-development", "records": {
            "factory": {k: contract[k] for k in keys},
            "source_artifact_sha256": item["bound"]["contract"],
            "covers": contract["kind"],
            "does_not_cover": "No execution, model calls, native runs, customer release or independent attestation",
        }}
    output = {}
    allowed = {
        "leak_check": ("schema", "annotation", "eligible", "inventory_sha256", "portable"),
        "outcome_summary": ("annotation", "runs", "passes", "failures", "eligible_for_verified", "flagged", "failure_after_apply_rate", "attribution"),
        "policy": ("schema", "routes", "review_after", "rule", "compiler_output", "model_versions"),
        "matrix_receipt": ("schema", "content_sha256", "cells", "false_acceptances"),
        "provider": ("id", "version", "local"),
        "qualification": (
            "schema",
            "content_sha256",
            "scope",
            "platform_versions",
            "clock_policy",
            "positive_controls",
            "false_rejection_bound",
            "mutation_score",
            "limits",
            "reference_review",
            "controls",
            "replay_command",
            "fixture_only",
        ),
        "rule": (
            "schema",
            "id",
            "title",
            "operation",
            "parameters",
            "owner",
            "review_after",
            "workload",
            "lane_pair",
            "field",
            "proposed_by",
        ),
        "diagnostic": (
            "schema",
            "id",
            "category",
            "class",
            "kind",
            "location",
            "public_stage",
            "thrown_by",
            "candidate_frame",
        ),
        "plan": (
            "schema",
            "artifact_type",
            "content_sha256",
            "max_client_invocations",
            "max_compilations",
            "max_elapsed_seconds",
            "limits",
            "stop_rules",
            "analysis",
        ),
        "slice": (
            "id",
            "lane_pair",
            "programs",
            "journeys",
            "clock_policy",
            "budget",
            "success_criteria",
        ),
        "archive": ("schema", "scope", "disclosure", "content_sha256"),
    }
    for name, keys in allowed.items():
        if name not in item["evidence"]:
            continue
        try:
            value = read_json(confined(root, item["evidence"][name]))
            if isinstance(value, dict):
                output[name] = {k: value[k] for k in keys if k in value}
        except (ValueError, OSError):
            pass
    if item.get("kind") in {"graph-annotation","graph-annotation-verified"}:
        from .knowledge_status import annotation_view
        output["annotation"] = annotation_view(root,item)
    if item.get("kind") == "verify-graph-projection":
        from .graph_review import projection_review
        output["graph_review"] = projection_review(root, item)
        for name, keys in {
            "manifest": ("included_kinds", "included_relations", "excluded", "mode", "projection_sha256"),
            "leak_check": ("passed", "watch_list_size", "matches", "projection_sha256"),
        }.items():
            value = read_json(confined(root, item["evidence"][name]))
            output[name] = {k:value[k] for k in keys if k in value}
    return {
        "disclosure": "no observation values or private captures",
        "records": output,
    }


def age(item, days, *, now=None):
    created = item.get("created_at_utc")
    if not created:
        return {"known": False, "overdue": False}
    try:
        start = datetime.fromisoformat(created)
        if start.tzinfo is None:
            raise ValueError("Timezone required")
    except (ValueError, TypeError):
        return {"known": False, "overdue": False}
    due = start
    for _ in range(days):
        due += timedelta(days=1)
        while due.weekday() >= 5:
            due += timedelta(days=1)
    current = now or datetime.now(timezone.utc)
    return {
        "known": True,
        "created_at_utc": start.isoformat(),
        "due_at_utc": due.isoformat(),
        "waiting_seconds": max(0, (current - start).total_seconds()),
        "overdue": current >= due,
    }


# Closed Factory adapter table. Files and projected fields are reviewed code,
# never query-string paths or a caller-controlled JSON pointer.
FACTORY_FILES = {
    "systematic-intcalc-review311.json": ("summary", "mutants"),
    "systematic-posttran-review311.json": ("summary", "mutants"),
    "systematic-review311-summary.json": ("programs", "dated_corrections", "schema"),
    "gnucobol-twin-result.json": ("oracle_class", "zos_confirmation", "run_class"),
    "twin-limits.md": None,
    "keep-or-fix-register.json": ("defects", "default_conversion_policy"),
    "io-gap-arguments.json": ("arguments", "gaps", "schema"),
    "posttran-human-review-sheet.json": ("records", "oracle_class", "oracle_status", "zos_confirmation"),
    "posttran-decisions-unsigned-2026-10-11.json": ("decisions", "sheet_sha256", "source_sha256", "reviewer"),
    "posttran-second-opinion/attempt-1-public-summary-2026-10-11.json": ("status", "phase1_validation_completed", "phase2_authorized", "usage", "plan_sha256", "finished_at"),
    "current-status-before-tower.json": ("conditional_threshold", "posttran_phase2_authorized", "b06_execution_authorized", "b06_window", "b06_request_due", "b07_freeze_ready", "decision_time"),
    "generated-review311-classification.json": ("cases", "unresolved", "observed_head"),
    "tower-display-policy.json": ("schema", "business_logic_outcomes", "legacy_mutants_killed", "minimum_systematic_mutants", "distinct_values_per_output_field", "status"),
}
FACTORY_SUMMARY_FIELDS = ("job", "source_sha256", "observed_head", "run_url", "before_faults", "after_faults",
    "mutant_count", "mutation_counts", "kill_rate", "eligible_kill_rate", "not_compiled", "unresolved_survivors",
    "post_campaign_adjusted_kill_rate", "remaining_unexplained_survivors", "fault_count", "fault_expectations_met")
FACTORY_MUTANT_FIELDS = ("id", "status", "operator", "line", "end_line", "source_sha256", "disposition", "argument", "killed_by")
FACTORY_REGISTER_FIELDS = ("id", "program", "source_sha256", "source_lines", "observed_behavior", "disposition", "classification", "dependent_arguments")
BUSINESS_RULE_EVIDENCE_FIELDS = ("evidence_strength", "evidence_strength_reason", "scenario_adequacy", "scenario_reasons")

FACTORY_FRESH_FIELDS = FACTORY_SUMMARY_FIELDS + ("campaign_head", "evidence_gap_ids", "generator_avoided_count", "oracle_class", "oracle_status", "zos_confirmation")
for _program in ("INTCALC", "POSTTRAN"):
    FACTORY_FILES["tower-run-38198096890/"+_program+"/fresh.json"] = FACTORY_FRESH_FIELDS
    FACTORY_FILES["tower-run-38198096890/"+_program+"/summary.json"] = ("current_head", "disposition_counts", "resource_usage", "compiler_scope", "source_sha256", "population")
    FACTORY_FILES["tower-run-38198096890/"+_program+"/results.json"] = ("id", "status", "class_covered", "refuted", "TCE", "argument", "mutant", "targeted_evidence_complete", "targeted_evidence_gaps")
    FACTORY_FILES["tower-run-38198096890/"+_program+"/threshold.json"] = ("twin", "zos-facing")
FACTORY_THRESHOLD_FIELDS = ("business", "io", "below_two_values", "distinct_values_per_output_field", "compared_fields", "blocking_reasons", "mutation", "conditions_met", "current_head", "source_sha256", "accepted_uncovered_IO", "unaccepted_outcomes")
