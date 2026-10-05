"""Closed projection of the judge's signed status; never reads its private root."""

import re
from .decisions import digest
from .status_export import read_exports, project_value


def graph_card(value):
    if (not isinstance(value, dict) or value.get("state") not in
            {"none", "pending", "approved", "expired", "rejected"} or
            set(value) - {"state", "projection_sha256", "mode", "node_count", "edge_count",
                          "excluded_count", "leak_check", "decision_sha256"}):
        raise ValueError("verify-graph-status-invalid")
    for field in ("projection_sha256", "decision_sha256"):
        if field in value and not re.fullmatch(r"[a-f0-9]{64}", value[field]):
            raise ValueError("verify-graph-status-hash")
    for field in ("node_count","edge_count","excluded_count"):
        if field in value and (type(value[field]) is not int or value[field]<0):
            raise ValueError("verify-graph-status-count")
    if value.get("mode", "field") not in {"field","confidential"} or value.get("leak_check","pending") not in {"pending","passed","failed","approved"}:
        raise ValueError("verify-graph-status-policy")
    return value


def project(directory, key, campaign_id, bindings, now, *, scope):
    def validate(value):
        d = value["details"]
        if set(d) - {"graph_projection"} != {
            "submissions",
            "refusals",
            "verdicts",
            "budget_exhausted",
            "repeated_diagnostics",
        }:
            raise ValueError("verify-status-fields-invalid")
        if any(
            type(d[k]) is not int or d[k] < 0 for k in ("submissions", "refusals")
        ) or any(
            type(d[k]) is not bool for k in ("budget_exhausted", "repeated_diagnostics")
        ):
            raise ValueError("verify-status-count-invalid")
        if (
            d["submissions"] != value["used"]["submissions"]
            or len(d["verdicts"]) > d["submissions"]
        ):
            raise ValueError("verify-status-count-invalid")
        ids = set()
        for r in d["verdicts"]:
            if (
                set(r) - {"context_projection_sha256"} != {"id", "verdict", "receipt_sha256"}
                or not re.fullmatch(r"attempt-[a-f0-9]{32}", r["id"])
                or not re.fullmatch(r"[a-f0-9]{64}", r["receipt_sha256"])
                or r["verdict"] not in {"equivalent", "divergent", "indeterminate"}
                or r["id"] in ids
            ):
                raise ValueError("verify-status-verdict-invalid")
            if r.get("context_projection_sha256") is not None and not re.fullmatch(r"[a-f0-9]{64}",r["context_projection_sha256"]):
                raise ValueError("verify-status-context-hash")
            ids.add(r["id"])
        graph_card(d.get("graph_projection", {"state":"none"}))

    value = read_exports(
        directory,
        key,
        campaign_id,
        bindings,
        scope=scope,
        profile="lightyear-verify",
        validator=validate,
    )
    result = project_value(value, now)
    details = value["details"]
    result["submissions"] = details["submissions"]
    result["refusals"] = details["refusals"]
    result["verdicts"] = details["verdicts"]
    result["graph_projection"] = graph_card(details.get("graph_projection", {"state":"none"}))
    for flag, code in (
        ("budget_exhausted", "budget-exhausted"),
        ("repeated_diagnostics", "repeated-identical-diagnostics"),
    ):
        if details[flag]:
            result["alerts"].append(
                {"code": code, "changes_verdict": False, "observation_only": True}
            )
    result["content_sha256"] = digest(
        {k: v for k, v in result.items() if k != "content_sha256"}
    )
    return result
