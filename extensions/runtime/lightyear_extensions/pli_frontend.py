from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


IDENTIFIER = re.compile(r"^[A-Z_$#@][A-Z0-9_$#@-]*$", re.I)
UNSUPPORTED_KEYWORDS = {
    "BASED": "based-storage",
    "CONTROLLED": "controlled-storage",
    "DIMENSION": "array-dimension",
    "GENERIC": "generic-entry",
    "PACKAGE": "package-declaration",
    "PICTURE": "picture-declaration",
    "POINTER": "pointer-storage",
}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


class PliLexError(ValueError):
    def __init__(self, code: str, message: str, line: int, column: int) -> None:
        super().__init__(message)
        self.code = code
        self.line = line
        self.column = column


def lex_pli(text: str) -> list[Token]:
    """Tokenize the supported PL/I subset while preserving exact source locations."""

    tokens: list[Token] = []
    index = 0
    line = 1
    column = 1
    length = len(text)
    while index < length:
        char = text[index]
        if char in " \t\r":
            index += 1
            column += 1
            continue
        if char == "\n":
            index += 1
            line += 1
            column = 1
            continue
        if text.startswith("/*", index):
            start_line, start_column = line, column
            index += 2
            column += 2
            while index < length and not text.startswith("*/", index):
                if text[index] == "\n":
                    line += 1
                    column = 1
                    index += 1
                else:
                    index += 1
                    column += 1
            if index >= length:
                raise PliLexError(
                    "unterminated-comment", "PL/I block comment is not terminated", start_line, start_column
                )
            index += 2
            column += 2
            continue
        if char in {"'", '"'}:
            quote = char
            start_line, start_column = line, column
            value = [char]
            index += 1
            column += 1
            while index < length:
                current = text[index]
                value.append(current)
                index += 1
                if current == "\n":
                    line += 1
                    column = 1
                    continue
                column += 1
                if current == quote:
                    if index < length and text[index] == quote:
                        value.append(text[index])
                        index += 1
                        column += 1
                        continue
                    break
            else:
                raise PliLexError(
                    "unterminated-string", "PL/I string literal is not terminated", start_line, start_column
                )
            tokens.append(Token("STRING", "".join(value), start_line, start_column))
            continue
        if char.isalpha() or char in "_$#@":
            start = index
            start_column = column
            while index < length and (text[index].isalnum() or text[index] in "_$#@-"):
                index += 1
                column += 1
            tokens.append(Token("IDENT", text[start:index].upper(), line, start_column))
            continue
        if char.isdigit():
            start = index
            start_column = column
            while index < length and (text[index].isdigit() or text[index] == "."):
                index += 1
                column += 1
            tokens.append(Token("NUMBER", text[start:index], line, start_column))
            continue
        two = text[index:index + 2]
        if two in {"<=", ">=", "^=", "¬=", "**", "||", "->"}:
            tokens.append(Token("OP", two, line, column))
            index += 2
            column += 2
            continue
        kind = "OP" if char in "=<>+-*/" else "SYMBOL"
        tokens.append(Token(kind, char, line, column))
        index += 1
        column += 1
    return tokens


def _statements(tokens: Iterable[Token]) -> list[list[Token]]:
    statements: list[list[Token]] = []
    current: list[Token] = []
    for token in tokens:
        current.append(token)
        if token.value == ";":
            statements.append(current)
            current = []
    if current:
        statements.append(current)
    return statements


def _values(statement: list[Token]) -> list[str]:
    return [token.value for token in statement]


def _location(token: Token) -> dict[str, int]:
    return {"line": token.line, "column": token.column}


def _construct(kind: str, token: Token, name: str | None = None, **details: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"kind": kind, **_location(token)}
    if name:
        item["name"] = name
    if details:
        item["details"] = details
    return item


def _diagnostic(code: str, message: str, token: Token | None, severity: str = "blocker") -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "message": message, "severity": severity}
    if token is not None:
        item.update(_location(token))
    return item


def _identifier_after(values: list[str], keyword: str) -> str | None:
    try:
        index = values.index(keyword) + 1
    except ValueError:
        return None
    while index < len(values) and not IDENTIFIER.fullmatch(values[index]):
        index += 1
    return values[index] if index < len(values) else None


def _file_handle(statement: list[Token]) -> str | None:
    values = _values(statement)
    try:
        index = values.index("FILE")
    except ValueError:
        return None
    if index + 2 < len(values) and values[index + 1] == "(" and IDENTIFIER.fullmatch(values[index + 2]):
        return values[index + 2]
    return None


def _table_reference(values: list[str]) -> tuple[str, str] | None:
    for marker in ("FROM", "INTO", "UPDATE"):
        if marker not in values:
            continue
        index = values.index(marker) + 1
        if index >= len(values) or not IDENTIFIER.fullmatch(values[index]):
            return None
        first = values[index]
        if index + 2 < len(values) and values[index + 1] == "." and IDENTIFIER.fullmatch(values[index + 2]):
            return first, values[index + 2]
        return "CARDDEMO", first
    return None


def _normalized_tokens(values: list[str]) -> str:
    text = " ".join(values)
    for before, after in (
        (" . ", "."), (" ,", ","), ("( ", "("), (" )", ")"), (" : ", ":"), (";", "")
    ):
        text = text.replace(before, after)
    return " ".join(text.split())


def parse_pli_source(
    text: str,
    path: str,
    *,
    include_names: set[str] | None = None,
) -> dict[str, Any]:
    """Parse a measured PL/I subset; unsupported or ambiguous input is never silently dropped."""

    include_catalog_provided = include_names is not None
    include_names = {name.upper() for name in (include_names or set())}
    try:
        tokens = lex_pli(text)
    except PliLexError as exc:
        return {
            "path": path,
            "status": "blocked",
            "file_kind": "unknown",
            "program": None,
            "constructs": [],
            "references": [],
            "diagnostics": [{
                "code": exc.code,
                "message": str(exc),
                "severity": "blocker",
                "line": exc.line,
                "column": exc.column,
            }],
        }

    constructs: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    program: str | None = None
    procedures: set[str] = set()
    declarations: dict[str, set[str]] = {}
    current_scope: str | None = None
    file_kind = "include" if path.casefold().endswith(".inc") else "program"

    for statement in _statements(tokens):
        significant = [token for token in statement if token.value != ";"]
        if not significant:
            continue
        values = _values(significant)
        first = values[0]

        if first == "%":
            directive = values[1] if len(values) > 1 else ""
            if directive == "INCLUDE" and len(values) > 2 and IDENTIFIER.fullmatch(values[2]):
                name = values[2]
                constructs.append(_construct("include_reference", significant[2], name))
                references.append({"kind": "include", "target": name, "scope": program, **_location(significant[2])})
                if include_catalog_provided and name not in include_names:
                    diagnostics.append(_diagnostic(
                        "missing-include", f"Included member is absent from the bounded source set: {name}", significant[2]
                    ))
            else:
                diagnostics.append(_diagnostic(
                    "unsupported-preprocessor", f"Unsupported PL/I preprocessor directive: %{directive or '?'}", significant[0]
                ))
            continue

        for token in significant:
            unsupported = UNSUPPORTED_KEYWORDS.get(token.value)
            if unsupported:
                diagnostics.append(_diagnostic(
                    f"unsupported-{unsupported}", f"Unsupported PL/I construct: {token.value}", token
                ))

        if len(values) >= 3 and IDENTIFIER.fullmatch(values[0]) and values[1] == ":" and values[2] in {"PROC", "PROCEDURE"}:
            name = values[0]
            is_main = "OPTIONS" in values and "MAIN" in values
            kind = "program" if is_main else "procedure"
            constructs.append(_construct(kind, significant[0], name, options_main=is_main))
            procedures.add(name)
            current_scope = name
            if is_main:
                if program is not None and program != name:
                    diagnostics.append(_diagnostic(
                        "multiple-main-procedures", "More than one OPTIONS(MAIN) procedure is unsupported", significant[0]
                    ))
                program = name
            continue

        if first == "END":
            current_scope = program
            continue

        if first in {"DCL", "DECLARE"}:
            cursor = 1
            level: int | None = None
            if cursor < len(values) and values[cursor].isdigit():
                level = int(values[cursor])
                cursor += 1
            while cursor < len(values) and not IDENTIFIER.fullmatch(values[cursor]):
                cursor += 1
            if cursor >= len(values):
                diagnostics.append(_diagnostic("malformed-declaration", "Declaration has no supported identifier", significant[0]))
                continue
            name = values[cursor]
            attrs = set(values[cursor + 1:])
            classes = declarations.setdefault(name, set())
            declaration_kind = "declaration"
            details: dict[str, Any] = {}
            if level is not None:
                declaration_kind = "structure" if level == 1 else "structure_member"
                details["level"] = level
                classes.add("structure")
            if level is None and "ENTRY" in attrs:
                declaration_kind = "entry_point"
                classes.add("entry")
                details["options_cobol"] = "OPTIONS" in attrs and "COBOL" in attrs
            elif level is None and "FILE" in attrs:
                declaration_kind = "file_declaration"
                classes.add("file")
            elif level is None and ("DECIMAL" in attrs or "DEC" in attrs):
                declaration_kind = "decimal_declaration"
                classes.add("decimal")
                details["fixed"] = "FIXED" in attrs
            elif level is None and ("CHAR" in attrs or "CHARACTER" in attrs):
                declaration_kind = "record_declaration"
                classes.add("record")
                details["varying"] = "VARYING" in attrs or "VAR" in attrs
                details["fixed"] = not details["varying"]
            elif level is None:
                classes.add("scalar")
            constructs.append(_construct(declaration_kind, significant[cursor], name, **details))
            continue

        if first == "ENTRY" and len(values) > 1 and IDENTIFIER.fullmatch(values[1]):
            constructs.append(_construct("entry_point", significant[1], values[1], options_cobol="COBOL" in values))
            declarations.setdefault(values[1], set()).add("entry")
            continue

        if first == "CALL" and len(values) > 1 and IDENTIFIER.fullmatch(values[1]):
            target = values[1]
            references.append({"kind": "call", "target": target, "scope": current_scope or program, **_location(significant[1])})
            constructs.append(_construct("call", significant[0], target, options_cobol=(
                "entry" in declarations.get(target, set()) and any(
                    item.get("kind") == "entry_point" and item.get("name") == target
                    and item.get("details", {}).get("options_cobol")
                    for item in constructs
                )
            )))
            if len(declarations.get(target, set())) > 1:
                diagnostics.append(_diagnostic(
                    "ambiguous-shadowed-call",
                    f"CALL target is shadowed by incompatible declarations: {target}",
                    significant[1],
                ))
            if target == "CBLTDLI":
                constructs.append(_construct("ims_reference", significant[1], target))
            continue

        if first in {"READ", "WRITE"}:
            handle = _file_handle(significant)
            if handle:
                kind = "file_read" if first == "READ" else "file_write"
                constructs.append(_construct(kind, significant[0], handle))
                references.append({"kind": kind, "target": handle, "scope": current_scope or program, **_location(significant[0])})
            else:
                diagnostics.append(_diagnostic("unsupported-file-io", f"Unsupported {first} form", significant[0]))
            continue

        if first == "EXEC" and len(values) > 1:
            subsystem = values[1]
            if subsystem == "SQL":
                operation = values[2] if len(values) > 2 else ""
                if operation == "INCLUDE" and len(values) > 3 and values[3] == "SQLCA":
                    constructs.append(_construct("sqlca_reference", significant[0], "SQLCA"))
                    continue
                table = _table_reference(values)
                if operation not in {"SELECT", "INSERT", "UPDATE", "DELETE"} or table is None:
                    diagnostics.append(_diagnostic("unsupported-sql", "Unsupported or unresolved embedded SQL statement", significant[0]))
                else:
                    schema, table_name = table
                    constructs.append(_construct(
                        "embedded_sql", significant[0], f"{schema}.{table_name}", operation=operation
                    ))
                    references.append({
                        "kind": "sql", "operation": operation, "schema": schema, "target": table_name,
                        "normalized_sql": _normalized_tokens(values[2:]),
                        "scope": current_scope or program, **_location(significant[0]),
                    })
            elif subsystem == "CICS":
                command = values[2] if len(values) > 2 else "UNKNOWN"
                constructs.append(_construct("cics_reference", significant[0], command))
            else:
                diagnostics.append(_diagnostic(
                    "unsupported-exec-subsystem", f"Unsupported EXEC subsystem: {subsystem}", significant[1]
                ))
            continue

        if first == "IF":
            constructs.append(_construct("conditional", significant[0], "IF"))
        elif first in {"SELECT", "WHEN", "OTHERWISE"}:
            constructs.append(_construct("conditional", significant[0], first))
        elif first == "ON":
            condition = values[1] if len(values) > 1 else "UNKNOWN"
            constructs.append(_construct("error_control", significant[0], condition))
        elif first == "DO":
            constructs.append(_construct("control_flow", significant[0], "DO"))
        elif (
            len(values) >= 3
            and IDENTIFIER.fullmatch(values[0])
            and values[0] not in {"ELSE", "THEN", "RETURN", "END"}
            and "=" in values
        ):
            constructs.append(_construct("assignment", significant[0], values[0]))

        if "CBLTDLI" in values:
            token = significant[values.index("CBLTDLI")]
            constructs.append(_construct("ims_reference", token, "CBLTDLI"))

    if file_kind == "program" and program is None:
        diagnostics.append(_diagnostic(
            "missing-main-procedure", "PL/I program has no OPTIONS(MAIN) procedure", tokens[0] if tokens else None
        ))
    if file_kind == "include":
        constructs.insert(0, {"kind": "include_member", "name": path.rsplit("/", 1)[-1].rsplit(".", 1)[0].upper(), "line": 1, "column": 1})

    constructs.sort(key=lambda item: (item.get("line", 0), item.get("column", 0), item["kind"], item.get("name", "")))
    references.sort(key=lambda item: (item.get("line", 0), item.get("column", 0), item["kind"], item.get("target", "")))
    diagnostics.sort(key=lambda item: (item.get("line", 0), item.get("column", 0), item["code"]))
    return {
        "path": path,
        "status": "blocked" if any(item["severity"] == "blocker" for item in diagnostics) else "passed",
        "file_kind": file_kind,
        "program": program,
        "constructs": constructs,
        "references": references,
        "diagnostics": diagnostics,
    }
