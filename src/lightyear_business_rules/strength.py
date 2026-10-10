"""Evidence diversity and strength, independent of agreement and authorization."""
from lightyear_control_tower.decisions import canonical
from .language import check_form, field, RuleError


def diversity(rule, records):
    paths = {path for path, binding in rule.get("bindings", {}).items()
             if path.startswith("output.") and binding["node"] in rule["outputs"]}
    values = {path: set() for path in paths}
    try:
        for i, record in enumerate(records):
            context = {**record, "previous": records[i-1] if i else {},
                       "next": records[i+1] if i+1 < len(records) else {},
                       "position": {"first": i == 0, "last": i+1 == len(records), "index": i}}
            if rule.get("executable") and check_form(rule["executable"], context, rule.get("bindings", {})) is not None:
                for path in paths:
                    values[path].add(canonical(field(context, path)))
    except (RuleError, KeyError, TypeError, ZeroDivisionError):
        return {}, "Output diversity could not be evaluated."
    return {path: len(items) for path, items in sorted(values.items())}, None


def assess(status, counts, mutation=None, error=None):
    if error or not counts or not any(counts.values()):
        return "not-assessed", error or "No applicable output observations."
    if status != "verified":
        return "not-assessed", "Agreement was not established."
    if mutation is not None and mutation.get("outcome") == "not-applicable":
        return "not-assessed", mutation.get("limitation") or "No applicable rule-scoped mutation check."
    if any(n < 2 for n in counts.values()):
        return "weak", "At least one applicable output is constant."
    if mutation is None:
        return "not-assessed", "Rule-scoped mutation assessment has not run."
    if mutation.get("killed_divergent", 0) == 0:
        return "weak", "No anchored mutant diverged on a named rule output."
    return "discriminating", "Diverse applicable outputs and an anchored output-field mutant kill."


def display(status, strength):
    return status if status != "verified" or strength == "discriminating" else f"verified ({'weak evidence' if strength == 'weak' else 'evidence not assessed'})"
