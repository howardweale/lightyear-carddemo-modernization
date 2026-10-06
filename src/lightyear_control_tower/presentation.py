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
    output = {}
    allowed = {
        "leak_check": ("schema", "annotation", "eligible", "inventory_sha256", "portable"),
        "outcome_summary": ("annotation", "runs", "passes", "failures", "eligible_for_verified", "flagged", "failure_after_apply_rate", "attribution"),
        "policy": ("schema", "routes", "review_after"),
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
