"""Closed JSON language. Exact arithmetic; explicit COBOL receiving assignments.

Each intermediate receiving field must use assign. Unsupported edited PICs,
floating point, dynamic code and implicit rounding fail closed. This is a bounded
executable subset, not a general COBOL interpreter.
"""
import re
from fractions import Fraction


class RuleError(ValueError):
    """A closed error code, never an input value."""


def require(condition, code):
    if not condition:
        raise RuleError(code)


def pic_type(pic):
    require(isinstance(pic, str) and len(pic) <= 80, "unsupported-pic")
    pic = pic.upper()
    require(bool(re.fullmatch(r"S?9(?:\(\d{1,2}\))?9*(?:V9(?:\(\d{1,2}\))?9*)?|X(?:\(\d{1,3}\))?X*", pic)), "unsupported-pic")
    expanded = re.sub(r"([9X])\((\d+)\)", lambda m: m[1] * int(m[2]), pic)
    if expanded.startswith("X"):
        require(1 <= len(expanded) <= 4096, "type-bound")
        return dict(kind="text", length=len(expanded))
    left, _, right = expanded.lstrip("S").partition("V")
    require(1 <= len(left + right) <= 38, "type-bound")
    return dict(kind="decimal", precision=len(left + right), scale=len(right), signed=expanded.startswith("S"))


def number(value):
    if isinstance(value, Fraction):
        return value
    require(type(value) is int or (isinstance(value, str) and bool(re.fullmatch(r"[-+]?\d{1,38}(?:\.\d{1,38})?", value))), "numeric-input-type")
    require(type(value) is not int or abs(value) < 10**38, "numeric-input-bound")
    return Fraction(value)


def assign(value, type_spec, rounding="truncate"):
    spec = pic_type(type_spec["pic"]) if set(type_spec) == {"pic"} else type_spec
    if spec.get("kind") == "text":
        require(set(spec) == {"kind", "length"} and type(spec["length"]) is int and 0 < spec["length"] <= 4096, "type-bound")
        require(isinstance(value, str) and len(value) <= spec["length"], "text-overflow")
        return value.ljust(spec["length"])
    require(set(spec) == {"kind", "precision", "scale", "signed"} and spec["kind"] == "decimal", "unsupported-type")
    precision, scale = spec["precision"], spec["scale"]
    require(type(precision) is int and type(scale) is int and 1 <= precision <= 38 and 0 <= scale <= precision and type(spec["signed"]) is bool, "type-bound")
    require(rounding in {"truncate", "rounded"}, "unsupported-rounding")
    value = number(value)
    require(spec["signed"] or value >= 0, "unsigned-negative")
    scaled = abs(value) * 10**scale
    units = scaled.numerator // scaled.denominator
    if rounding == "rounded" and scaled - units >= Fraction(1, 2):
        units += 1
    require(units < 10**precision, "decimal-overflow")
    return Fraction(-units if value < 0 else units, 10**scale)


def boolean(value):
    require(type(value) is bool, "boolean-input-type")
    return value


def field(context, path):
    require(isinstance(path, str) and bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,159}", path)), "field-path")
    value = context
    for key in path.split("."):
        require(isinstance(value, dict) and key in value, "missing-input")
        value = value[key]
    require(value is None or type(value) in (str, bool, int), "field-input-type")
    return value


def evaluate(node, context, bindings=None, *, _depth=0, _budget=None):
    budget = [2048] if _budget is None else _budget
    budget[0] -= 1
    require(_depth <= 32 and budget[0] >= 0, "expression-bound")
    require(isinstance(node, dict), "expression-shape")
    run = lambda n: evaluate(n, context, bindings, _depth=_depth+1, _budget=budget)
    if set(node) == {"literal"}:
        value = node["literal"]
        require(value is None or type(value) in (bool, str), "literal-type")
        require(not isinstance(value, str) or len(value) <= 4096, "literal-bound")
        return value
    if set(node) == {"number"}:
        return number(node["number"])
    if set(node) == {"field"}:
        value = field(context, node["field"])
        spec = (bindings or {}).get(node["field"], {}).get("type")
        if spec:
            converted = assign(value, spec)
            if isinstance(converted, Fraction):
                require(converted == number(value), "input-scale")
            return converted
        return value
    if set(node) == {"assign", "type", "rounding"}:
        return assign(run(node["assign"]), node["type"], node["rounding"])
    require(set(node) == {"op", "args"} and isinstance(node["args"], list) and len(node["args"]) <= 64, "expression-shape")
    op, args = node["op"], node["args"]
    if op in {"and", "or"}:
        require(bool(args), "operator-arity")
        for n in args:
            result = boolean(run(n))
            if result == (op == "or"):
                return result
        return op == "and"
    if op == "if":
        require(len(args) == 3, "operator-arity")
        return run(args[1] if boolean(run(args[0])) else args[2])
    if op == "not":
        require(len(args) == 1, "operator-arity")
        return not boolean(run(args[0]))
    require(len(args) == 2, "operator-arity")
    a, b = map(run, args)
    if op in {"add", "sub", "mul", "div"}:
        a, b = number(a), number(b)
        require(op != "div" or b != 0, "division-by-zero")
        value = {"add": lambda: a+b, "sub": lambda: a-b, "mul": lambda: a*b, "div": lambda: a/b}[op]()
        require(value.numerator.bit_length() <= 4096 and value.denominator.bit_length() <= 4096, "arithmetic-bound")
        return value
    if op in {"eq", "ne", "lt", "le", "gt", "ge"}:
        require((type(a) == type(b)) or (isinstance(a, Fraction) and type(b) is int) or (isinstance(b, Fraction) and type(a) is int), "comparison-type")
        require(op in {"eq", "ne"} or a is not None, "comparison-type")
        return {"eq": lambda: a == b, "ne": lambda: a != b, "lt": lambda: a < b,
                "le": lambda: a <= b, "gt": lambda: a > b, "ge": lambda: a >= b}[op]()
    if op == "concat":
        require(isinstance(a, str) and isinstance(b, str) and len(a+b) <= 4096, "text-bound")
        return a+b
    raise RuleError("unsupported-operator")


def check_form(executable, context, bindings):
    form = executable.get("form")
    require(form in {"expression", "decision_table", "record_predicate", "sequence_predicate"}, "unsupported-form")
    require("when" in executable, "applicability-required")
    if not boolean(evaluate(executable["when"], context, bindings)):
        return None
    if form == "expression":
        wanted = assign(evaluate(executable["value"], context, bindings), executable["target_type"], executable["rounding"])
        return evaluate({"field": executable["output"]}, context, bindings) == wanted
    if form == "decision_table":
        rows = executable["rows"]
        require(isinstance(rows, list) and 1 <= len(rows) <= 128 and set(rows[-1]) == {"else"}, "decision-else-required")
        require(all(set(row) == {"when", "then"} for row in rows[:-1]), "decision-row-shape")
        wanted = rows[-1]["else"]
        for row in rows[:-1]:
            if boolean(evaluate(row["when"], context, bindings)):
                wanted = row["then"]
                break
        return evaluate({"field": executable["output"]}, context, bindings) == evaluate(wanted, context, bindings)
    if form in {"record_predicate", "sequence_predicate"}:
        return boolean(evaluate(executable["condition"], context, bindings))
    raise RuleError("unsupported-form")
