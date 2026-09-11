"""Fail-closed SQL projection for the IDDA audit, not a database emulator.

Every non-comment input unit is retained, including client commands and unsupported
procedural blocks. Only completely consumed productions yield structured effects.
Identifiers, quoted identifiers and string literals remain distinct throughout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from bisect import bisect_left
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Any

from .semantic_core import CANONICAL_TYPES


class Unsupported(ValueError):
    pass


_WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9$#]*")
_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_DOLLAR = re.compile(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$")


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    start: int
    end: int


def lex(sql: str, dialect: str = "postgresql") -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(sql):
        start = i
        if sql[i].isspace():
            i += 1
            continue
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            i = len(sql) if end < 0 else end
            continue
        if sql.startswith("/*", i):
            # Nested comments are legal in PostgreSQL; no text inside is SQL.
            depth = 1
            i += 2
            while i < len(sql) and depth:
                if sql.startswith("/*", i):
                    if dialect == "oracle":
                        raise Unsupported("nested-oracle-comment")
                    depth += 1
                    i += 2
                elif sql.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise Unsupported("unterminated-comment")
            continue
        dollar = _DOLLAR.match(sql, i)
        if dollar:
            tag = dollar.group()
            end = sql.find(tag, i + len(tag))
            if end < 0:
                raise Unsupported("unterminated-dollar-quote")
            i = end + len(tag)
            tokens.append(Token("opaque", sql[start:i], start, i))
            continue
        if sql[i:i + 2].lower() == "q'" and i + 2 < len(sql):
            opening = sql[i + 2]
            closing = {"[": "]", "{": "}", "(": ")", "<": ">"}.get(opening, opening)
            end = sql.find(closing + "'", i + 3)
            if end < 0:
                raise Unsupported("unterminated-oracle-quote")
            i = end + 2
            tokens.append(Token("string" if dialect == "oracle" else "opaque", sql[start + 3:end], start, i))
            continue
        if sql[i] in "'\"":
            quote = sql[i]
            i += 1
            value = ""
            while i < len(sql):
                if sql[i] == quote:
                    if i + 1 < len(sql) and sql[i + 1] == quote:
                        value += quote
                        i += 2
                        continue
                    i += 1
                    break
                value += sql[i]
                i += 1
            else:
                raise Unsupported("unterminated-quote")
            tokens.append(Token("string" if quote == "'" else "quoted", value, start, i))
            continue
        word = _WORD.match(sql, i)
        if word:
            i += len(word.group())
            tokens.append(Token("word", word.group().lower(), start, i))
            continue
        number = _NUMBER.match(sql, i)
        if number:
            i += len(number.group())
            tokens.append(Token("number", number.group(), start, i))
            continue
        operator = next((s for s in ("::", "<=", ">=", "<>", "!=", "||", ":=") if sql.startswith(s, i)), sql[i])
        i += len(operator)
        tokens.append(Token("symbol", operator, start, i))
    return tokens


@dataclass
class Unit:
    ordinal: int
    start_line: int
    end_line: int
    sha256: str
    tokens: list[Token]
    lexical_error: str | None = None
    effects: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    parsed: bool = False
    administrative: bool = False


def split_units(sql: str, dialect: str) -> list[Unit]:
    sql = sql.replace("\r\n", "\n").replace("\r", "\n")
    units: list[Unit] = []
    newlines = [m.start() for m in re.finditer("\n", sql)]

    def add(tokens: list[Token], error: str | None = None) -> None:
        start = tokens[0].start if tokens else 0
        end = tokens[-1].end if tokens else len(sql)
        units.append(Unit(len(units) + 1, bisect_left(newlines, start) + 1,
                          bisect_left(newlines, end) + 1,
                          hashlib.sha256(sql[start:end].encode()).hexdigest(), tokens, error))

    try:
        tokens = lex(sql, dialect)
    except Unsupported as exc:
        # A broken quote can swallow arbitrary later SQL. Count one failed file
        # unit, not invented inner statements, and publish this denominator limit.
        add([], str(exc))
        return units
    i = 0
    while i < len(tokens):
        start = i
        first = tokens[i]
        line_end = sql.find("\n", first.start)
        line_end = len(sql) if line_end < 0 else line_end
        at_line_start = not sql[sql.rfind("\n", 0, first.start) + 1:first.start].strip()
        # SQL*Plus slash repeats SQL; never silently discard a standalone slash.
        if at_line_start and (first.value in {"set", "prompt", "spool", "whenever", "exit", "quit", "@", "\\"}
                              or (first.value == "/" and not sql[first.end:line_end].strip())):
            while i < len(tokens) and tokens[i].start < line_end:
                i += 1
            add(tokens[start:i])
            continue
        prefix = [t.value for t in tokens[i:i + 7] if t.kind == "word"]
        procedural = dialect == "oracle" and (first.value in {"begin", "declare"}
                      or (first.value == "create" and any(w in prefix for w in ("function", "procedure", "trigger", "package"))))
        if procedural:
            while i < len(tokens):
                token = tokens[i]
                endline = sql.find("\n", token.start)
                endline = len(sql) if endline < 0 else endline
                if token.value == "/" and not sql[sql.rfind("\n", 0, token.start) + 1:token.start].strip() and not sql[token.end:endline].strip():
                    i += 1
                    break
                i += 1
            add(tokens[start:i], "procedural-block")
            continue
        while i < len(tokens) and not (tokens[i].kind == "symbol" and tokens[i].value == ";"):
            i += 1
        if i < len(tokens):
            i += 1
            add(tokens[start:i])
        else:
            add(tokens[start:i], "missing-statement-terminator")
    return units


class Cursor:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def is_word(self, word: str) -> bool:
        return self.pos < len(self.tokens) and self.tokens[self.pos].kind == "word" and self.tokens[self.pos].value == word

    def accept(self, value: str) -> bool:
        if self.pos < len(self.tokens) and self.tokens[self.pos].value == value and self.tokens[self.pos].kind in {"word", "symbol"}:
            self.pos += 1
            return True
        return False

    def need(self, value: str) -> None:
        if not self.accept(value):
            raise Unsupported("unsupported-syntax")

    def name(self) -> str:
        if self.pos >= len(self.tokens) or self.tokens[self.pos].kind not in {"word", "quoted"}:
            raise Unsupported("identifier-required")
        token = self.tokens[self.pos]
        self.pos += 1
        # Explicit quoting is deliberately not equated to dialect case folding.
        return '"' + token.value.replace('"', '""') + '"' if token.kind == "quoted" else token.value

    def qualified(self) -> str:
        result = self.name()
        if self.accept("."):
            result += "." + self.name()
        return result

    def group(self) -> list[Token]:
        self.need("(")
        start = self.pos
        depth = 1
        while self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            self.pos += 1
            if token.kind == "symbol":
                depth += (token.value == "(") - (token.value == ")")
            if depth == 0:
                return self.tokens[start:self.pos - 1]
        raise Unsupported("unbalanced-parentheses")

    def finish(self) -> None:
        if self.pos != len(self.tokens):
            raise Unsupported("unconsumed-syntax")


def comma_parts(tokens: list[Token]) -> list[list[Token]]:
    result: list[list[Token]] = []
    start = depth = 0
    for i, token in enumerate(tokens):
        if token.kind == "symbol":
            depth += (token.value == "(") - (token.value == ")")
            if depth < 0:
                raise Unsupported("unbalanced-parentheses")
            if token.value == "," and depth == 0:
                if i == start:
                    raise Unsupported("empty-list-item")
                result.append(tokens[start:i])
                start = i + 1
    if depth or start == len(tokens):
        raise Unsupported("invalid-list")
    return result + [tokens[start:]]


def literal(tokens: list[Token], dialect: str) -> dict[str, Any]:
    if len(tokens) == 1:
        token = tokens[0]
        if token.kind == "string":
            if "\\" in token.value:
                raise Unsupported("string-escape-session-policy")
            return {"kind": "null"} if dialect == "oracle" and not token.value else {"kind": "string", "value": token.value}
        if token.kind == "word" and token.value == "null":
            return {"kind": "null"}
    value = "".join(t.value for t in tokens)
    numeric_tokens = (len(tokens) == 1 and tokens[0].kind == "number") or (len(tokens) == 2 and tokens[0].kind == "symbol" and tokens[0].value in {"+", "-"} and tokens[1].kind == "number")
    if numeric_tokens and len(value) <= 100 and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value):
        try:
            number = Decimal(value)
            # Decimal.normalize uses context precision. Do not round long literals.
            normalized = format(number, "f")
            if "." in normalized:
                normalized = normalized.rstrip("0").rstrip(".")
            if number == 0:
                normalized = "0"
            return {"kind": "number", "value": normalized}
        except InvalidOperation:
            pass
    raise Unsupported("expression-outside-literal-grammar")


def expression(tokens: list[Token], dialect: str) -> tuple[dict[str, Any], list[str]]:
    if not tokens:
        raise Unsupported("empty-expression")
    try:
        value = literal(tokens, dialect)
        return value, (["empty-string-null-domain"] if any(t.kind == "string" and t.value == "" for t in tokens) else [])
    except Unsupported:
        # An opaque expression is never compared by normalized text as semantics.
        return {"kind": "opaque", "tokens_sha256": hashlib.sha256(repr([(t.kind, t.value) for t in tokens]).encode()).hexdigest()}, ["expression-requires-dialect-or-session-semantics"]


def type_spec(cursor: Cursor, dialect: str) -> dict[str, Any]:
    name = cursor.name()
    allowed = {"number", "numeric", "decimal", "varchar2", "varchar", "char", "date", "timestamp", "clob", "blob", "text", "bytea"}
    if name not in allowed or (dialect == "oracle" and name in {"numeric", "text", "bytea"}) or (dialect == "postgresql" and name in {"number", "varchar2", "clob", "blob"}):
        raise Unsupported("unsupported-data-type")
    args: list[str] = []
    if cursor.pos < len(cursor.tokens) and cursor.tokens[cursor.pos].value == "(":
        args = [" ".join(t.value for t in part) for part in comma_parts(cursor.group())]
    if name in {"number", "numeric", "decimal"}:
        if len(args) > 2 or any(not re.fullmatch(r"-?\s*\d+", a) for a in args):
            raise Unsupported("unsupported-numeric-facets")
        precision = int(args[0].replace(" ", "")) if args else None
        scale = int(args[1].replace(" ", "")) if len(args) > 1 else (0 if args else None)
        if precision is not None and not 1 <= precision <= (38 if dialect == "oracle" else 1000):
            raise Unsupported("invalid-numeric-precision")
        if scale is not None and not ((-84 <= scale <= 127) if dialect == "oracle" else (-1000 <= scale <= 1000)):
            raise Unsupported("invalid-numeric-scale")
        return {"canonical_type": "exact-decimal", "precision": precision, "scale": scale}
    if name in {"varchar2", "varchar", "char"}:
        if len(args) > 1 or (args and not re.fullmatch(r"[1-9]\d*(?: (?:byte|char))?", args[0])):
            raise Unsupported("unsupported-character-facets")
        if not args and name in {"varchar2", "varchar"}:
            raise Unsupported("unbounded-character-type")
        parts = (args[0] if args else "1").split()
        unit = parts[1] if len(parts) == 2 else ("session" if dialect == "oracle" else "char")
        if dialect == "postgresql" and len(parts) > 1:
            raise Unsupported("invalid-postgresql-length-unit")
        return {"canonical_type": "fixed-character" if name == "char" else "variable-character", "length": int(parts[0]), "length_unit": unit, "empty_string_is_null": dialect == "oracle"}
    if name in {"date", "timestamp"}:
        if name == "date" and args:
            raise Unsupported("invalid-date-facets")
        if len(args) > 1 or (args and not re.fullmatch(r"\d+", args[0])):
            raise Unsupported("unsupported-timestamp-facets")
        precision = int(args[0]) if args else (0 if name == "date" else 6)
        if not 0 <= precision <= (9 if dialect == "oracle" else 6):
            raise Unsupported("invalid-timestamp-precision")
        zone = "none"
        if cursor.accept("with"):
            zone = "local" if cursor.accept("local") else "offset"
            cursor.need("time")
            cursor.need("zone")
        elif cursor.accept("without"):
            cursor.need("time")
            cursor.need("zone")
        kind = "date" if name == "date" and dialect == "postgresql" else ("timestamp-with-time-zone" if zone != "none" else "timestamp")
        return {"canonical_type": kind, "fractional_seconds": precision, "zone": zone, "dialect_domain": dialect}
    if args:
        raise Unsupported("unsupported-lob-facets")
    return {"canonical_type": "large-text" if name in {"clob", "text"} else "large-binary", "dialect_domain": dialect}


def effect(kind: str, target: str, facet: str, value: Any, reasons: list[str] | None = None) -> dict[str, Any]:
    return {"kind": kind, "target": target, "facet": facet, "value": value, "reasons": reasons or []}


def column_effects(cursor: Cursor, table: str, mode: str, dialect: str) -> list[dict[str, Any]]:
    column = cursor.name()
    target = table + "." + column
    result = []
    if mode == "add" or not (cursor.is_word("default") or cursor.is_word("not") or cursor.is_word("null")):
        datatype = type_spec(cursor, dialect)
        assert datatype["canonical_type"] in CANONICAL_TYPES
        result.append(effect(mode, target, "type", datatype))
    seen: set[str] = set()
    while cursor.pos < len(cursor.tokens):
        if cursor.accept("default"):
            if "default" in seen:
                raise Unsupported("duplicate-column-clause")
            seen.add("default")
            start = cursor.pos
            depth = 0
            while cursor.pos < len(cursor.tokens):
                t = cursor.tokens[cursor.pos]
                if depth == 0 and cursor.pos > start and (cursor.is_word("not") or cursor.is_word("null") or cursor.is_word("constraint") or cursor.is_word("primary") or cursor.is_word("unique")):
                    break
                if t.kind == "symbol":
                    depth += (t.value == "(") - (t.value == ")")
                cursor.pos += 1
            value, reasons = expression(cursor.tokens[start:cursor.pos], dialect)
            result.append(effect(mode, target, "default", value, reasons))
        elif cursor.is_word("not") or cursor.is_word("null"):
            if "nullable" in seen:
                raise Unsupported("duplicate-column-clause")
            seen.add("nullable")
            nullable = not cursor.accept("not")
            cursor.need("null")
            result.append(effect(mode, target, "nullable", nullable))
        else:
            raise Unsupported("unsupported-column-clause")
    if not result:
        raise Unsupported("empty-column-change")
    return result


def names(tokens: list[Token]) -> list[str]:
    result = []
    for part in comma_parts(tokens):
        c = Cursor(part)
        result.append(c.name())
        c.finish()
    if len(set(result)) != len(result):
        raise Unsupported("duplicate-column-name")
    return result


def constraint(cursor: Cursor, table: str) -> list[dict[str, Any]]:
    constraint_name = cursor.name() if cursor.accept("constraint") else "<unnamed>"
    if cursor.accept("primary"):
        cursor.need("key")
        kind = "primary-key"
    elif cursor.accept("unique"):
        kind = "unique"
    elif cursor.accept("foreign"):
        cursor.need("key")
        kind = "foreign-key"
    else:
        raise Unsupported("unsupported-constraint")
    value: dict[str, Any] = {"kind": kind, "columns": names(cursor.group())}
    if kind == "foreign-key":
        cursor.need("references")
        value["references"] = cursor.qualified()
        value["reference_columns"] = names(cursor.group())
        if len(value["columns"]) != len(value["reference_columns"]):
            raise Unsupported("foreign-key-arity")
        value["on_delete"] = "no-action"
        if cursor.accept("on"):
            cursor.need("delete")
            if cursor.accept("cascade"):
                value["on_delete"] = "cascade"
            elif cursor.accept("set"):
                cursor.need("null")
                value["on_delete"] = "set-null"
            else:
                raise Unsupported("unsupported-referential-action")
    cursor.finish()
    return [effect("constraint", table + "." + constraint_name, "definition", value, ["constraint-column-domain-required"])]


def parse_statement(tokens: list[Token], dialect: str) -> tuple[list[dict[str, Any]], bool]:
    c = Cursor(tokens)
    words = [(t.kind, t.value) for t in tokens]
    if dialect == "oracle" and words in [[("word", "set"), ("word", "define"), ("word", "off")], [("word", "set"), ("word", "sqlblanklines"), ("word", "on")]]:
        return [], True
    if c.accept("select"):
        c.need("register_migration_script")
        args = comma_parts(c.group())
        if len(args) != 1 or len(args[0]) != 1 or args[0][0].kind != "string" or not re.fullmatch(r"[A-Za-z0-9_.-]+\.sql", args[0][0].value):
            raise Unsupported("unsupported-registration")
        c.need("from")
        c.need("dual")
        c.finish()
        return [], True
    if c.accept("alter"):
        c.need("table")
        table = c.qualified()
        if c.accept("add"):
            if dialect == "postgresql":
                c.accept("column")
            if c.is_word("constraint") or c.is_word("primary") or c.is_word("foreign") or c.is_word("unique"):
                return constraint(Cursor(c.tokens[c.pos:]), table), False
            if c.pos < len(tokens) and tokens[c.pos].value == "(":
                if dialect != "oracle":
                    raise Unsupported("oracle-only-add-column-list")
                result = []
                for part in comma_parts(c.group()):
                    result.extend(column_effects(Cursor(part), table, "add", dialect))
            else:
                result = column_effects(c, table, "add", dialect)
        elif dialect == "oracle" and c.accept("modify"):
            if c.pos < len(tokens) and tokens[c.pos].value == "(":
                result = []
                for part in comma_parts(c.group()):
                    result.extend(column_effects(Cursor(part), table, "modify", dialect))
            else:
                result = column_effects(c, table, "modify", dialect)
        elif dialect == "postgresql" and c.accept("alter"):
            c.accept("column")
            column = c.name()
            target = table + "." + column
            if c.accept("type"):
                result = [effect("modify", target, "type", type_spec(c, dialect))]
            elif c.accept("set"):
                if c.accept("default"):
                    value, reasons = expression(c.tokens[c.pos:], dialect)
                    c.pos = len(tokens)
                    result = [effect("modify", target, "default", value, reasons)]
                else:
                    c.need("not")
                    c.need("null")
                    result = [effect("modify", target, "nullable", False)]
            elif c.accept("drop"):
                if c.accept("default"):
                    result = [effect("modify", target, "default", {"kind": "null"})]
                else:
                    c.need("not")
                    c.need("null")
                    result = [effect("modify", target, "nullable", True)]
            else:
                raise Unsupported("unsupported-alter-column")
        elif c.accept("drop"):
            if c.accept("constraint"):
                result = [effect("drop", table + "." + c.name(), "constraint", True, ["baseline-object-required"])]
            else:
                c.accept("column")
                result = [effect("drop", table + "." + c.name(), "column", True, ["baseline-object-required"])]
        else:
            raise Unsupported("unsupported-alter-table")
        c.finish()
        return result, False
    if c.accept("create"):
        if c.accept("table"):
            table = c.qualified()
            parts = comma_parts(c.group())
            c.finish()
            result = [effect("create", table, "table", True)]
            for part in parts:
                sub = Cursor(part)
                if sub.is_word("constraint") or sub.is_word("primary") or sub.is_word("unique") or sub.is_word("foreign"):
                    result.extend(constraint(sub, table))
                else:
                    result.extend(column_effects(sub, table, "add", dialect))
            keys = [(e["kind"], e["target"], e["facet"]) for e in result]
            if len(set(keys)) != len(keys):
                raise Unsupported("duplicate-schema-effect")
            return result, False
        unique = c.accept("unique")
        c.need("index")
        index = c.qualified()
        c.need("on")
        table = c.qualified()
        columns = []
        for part in comma_parts(c.group()):
            sub = Cursor(part)
            name = sub.name()
            if sub.accept("desc"):
                direction = "desc"
            else:
                sub.accept("asc")
                direction = "asc"
            sub.finish()
            columns.append([name, direction])
        c.finish()
        return [effect("index", index, "definition", {"table": table, "unique": unique, "columns": columns}, ["index-null-collation-and-column-domain-required"])], False
    if c.accept("drop"):
        kind = c.name()
        if kind not in {"table", "index", "view", "sequence"}:
            raise Unsupported("unsupported-drop-object")
        name = c.qualified()
        c.finish()
        return [effect("drop", name, kind, True, ["baseline-object-required"])], False
    if c.accept("insert"):
        c.need("into")
        table = c.qualified()
        columns = names(c.group()) if c.pos < len(tokens) and tokens[c.pos].value == "(" else None
        c.need("values")
        values = comma_parts(c.group())
        c.finish()
        if table == "t_alter_column" and dialect == "postgresql":
            if columns is not None or len(values) != 5:
                raise Unsupported("unsupported-helper-signature")
            args = [literal(v, dialect) for v in values]
            if any(a["kind"] not in {"string", "null"} for a in args) or any(a["kind"] != "string" or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", a["value"]) for a in args[:2]):
                raise Unsupported("unsupported-helper-arguments")
            target = args[0]["value"].lower() + "." + args[1]["value"].lower()
            result = []
            helper_reason = ["helper-catalog-and-dependent-view-effects"]
            if args[2]["kind"] != "null":
                sub = Cursor(lex(args[2]["value"]))
                datatype = type_spec(sub, dialect)
                sub.finish()
                result.append(effect("modify", target, "type", datatype, helper_reason))
            if args[4]["kind"] != "null":
                value = args[4]["value"]
                if value.lower() == "null":
                    default, reasons = {"kind": "null"}, []
                elif "(" in value or value.lower() == "current_timestamp":
                    default, reasons = expression(lex(value), dialect)
                elif "'" in value or "\\" in value:
                    raise Unsupported("helper-default-quoting")
                else:
                    default, reasons = {"kind": "string", "value": value}, []
                result.append(effect("modify", target, "default", default, helper_reason + reasons))
            if args[3]["kind"] != "null":
                value = args[3]["value"].lower()
                if value not in {"null", "not null"}:
                    raise Unsupported("unsupported-helper-null-clause")
                result.append(effect("modify", target, "nullable", value == "null", helper_reason))
            if not result:
                raise Unsupported("helper-no-op")
            return result, False
        if columns is None or len(columns) != len(values):
            raise Unsupported("insert-column-value-arity")
        expressions = [expression(v, dialect) for v in values]
        return [effect("insert", table, "row", dict(zip(columns, [v for v, _ in expressions])), ["dml-schema-trigger-and-coercion-context-required"] + sorted({r for _, rs in expressions for r in rs}))], False
    if c.accept("update"):
        table = c.qualified()
        c.need("set")
        start = c.pos
        depth = 0
        while c.pos < len(tokens):
            t = tokens[c.pos]
            if depth == 0 and c.is_word("where"):
                break
            if t.kind == "symbol":
                depth += (t.value == "(") - (t.value == ")")
            c.pos += 1
        assignments = {}
        reasons = ["dml-schema-trigger-and-coercion-context-required"]
        for part in comma_parts(tokens[start:c.pos]):
            sub = Cursor(part)
            name = sub.name()
            sub.need("=")
            if name in assignments:
                raise Unsupported("duplicate-update-assignment")
            assignments[name], extra = expression(part[sub.pos:], dialect)
            reasons.extend(extra)
        has_where = c.accept("where")
        predicate = tokens[c.pos:] if has_where else []
        # WHERE is retained as opaque; no predicate is silently considered true.
        if has_where and not predicate:
            raise Unsupported("empty-predicate")
        c.pos = len(tokens)
        pred, extra = expression(predicate, dialect) if predicate else ({"kind": "all-rows"}, [])
        return [effect("update", table, "rows", {"assignments": assignments, "predicate": pred}, sorted(set(reasons + extra)))], False
    if c.accept("delete"):
        c.need("from")
        table = c.qualified()
        if c.accept("where"):
            pred, reasons = expression(tokens[c.pos:], dialect)
            c.pos = len(tokens)
        else:
            pred, reasons = {"kind": "all-rows"}, []
        c.finish()
        return [effect("delete", table, "rows", pred, ["dml-schema-trigger-and-coercion-context-required"] + reasons)], False
    raise Unsupported("unsupported-statement")


def parse_script(sql: str, dialect: str) -> list[Unit]:
    if dialect not in {"oracle", "postgresql"}:
        raise ValueError("Unknown SQL dialect")
    units = split_units(sql, dialect)
    for unit in units:
        if unit.lexical_error:
            unit.reasons = [unit.lexical_error]
            continue
        tokens = unit.tokens[:-1] if unit.tokens and unit.tokens[-1].kind == "symbol" and unit.tokens[-1].value == ";" else unit.tokens
        try:
            unit.effects, unit.administrative = parse_statement(tokens, dialect)
            unit.parsed = True
        except Unsupported as exc:
            unit.effects = []
            unit.reasons = [str(exc)]
    return units
