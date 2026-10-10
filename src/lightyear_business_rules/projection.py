"""Optional rule enrichment for the existing approved graph projection."""
import json
import re
from .engine import replay
from .language import require


def enrich(node, rules, receipt, records, judge_key, *, public_lane, approved_source):
    replay(receipt, rules, records, judge_key)
    require(public_lane and receipt["visibility"] == "public-development", "public-rule-projection-required")
    rule = next((r for r in rules if r["id"] == node["id"]), None)
    if not rule or rule["provenance"] not in {"source-observed", "asserted"}:
        return node
    result = {**node, "properties": dict(node["properties"])}
    status = next(r for r in receipt["rules"] if r["id"] == rule["id"])
    result["properties"].update(rule_status=status["status"], rule_receipt_sha256=receipt["content_sha256"])
    def constants(value):
        if isinstance(value, dict):
            for k,v in value.items():
                if k in {"literal", "number"} and type(v) not in (bool, type(None)):
                    yield str(v)
                else: yield from constants(v)
        elif isinstance(value, list):
            for v in value: yield from constants(v)
    # Exact lexical constants only, never substring acceptance (12 is not 1200).
    literals = set(re.findall(r"(?<![\w.-])[-+]?\d+(?:\.\d+)?(?![\w.-])", approved_source))
    literals.update(m[1] for m in re.finditer(r"['\"]([^'\"]*)['\"]", approved_source))
    form = rule.get("executable")
    if form and set(constants(form)) <= literals:
        result["properties"]["rule_executable_json"] = json.dumps(form, sort_keys=True, separators=(",", ":"))
    return result
