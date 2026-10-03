"""Typed proposals use registered operations, never executable free text."""

from datetime import date
from carddemo_oracle.compare import NORMALIZATION_RULES
from .requests import identifier


def typed_rule(rule):
    if not isinstance(rule, dict):
        raise ValueError("Typed rule must be an object")
    if rule.get("schema") != "tower-rule-proposal/1":
        raise ValueError("Unsupported rule schema")
    identifier(rule.get("id"))
    for field in ("owner", "title", "proposed_by", "workload", "lane_pair", "field"):
        if not isinstance(rule.get(field), str) or not rule[field].strip():
            raise ValueError("Missing rule field: " + field)
    date.fromisoformat(rule["review_after"])
    known = {r["id"]: r for r in NORMALIZATION_RULES}
    if rule.get("operation") not in known:
        raise ValueError("No registered validator for this typed operation")
    if rule.get("parameters", {}) != {}:
        raise ValueError("This rule type takes no parameters")
    return rule
