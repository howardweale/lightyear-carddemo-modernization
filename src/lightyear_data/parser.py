from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .contracts import SCHEMA_VERSION, seal


TYPE_PATTERN = re.compile(r"^(CHAR|VARCHAR|DECIMAL|SMALLINT|INTEGER|DATE|TIMESTAMP)\s*(?:\(([^)]*)\))?", re.I)


def _clean(text: str) -> str:
    return re.sub(r"--[^\n]*", "", text).replace("\r\n", "\n").replace("\r", "\n")


def _split_commas(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        depth += char == "("
        depth -= char == ")"
        if char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def parse_db2_ddl(text: str, path: str = "") -> dict[str, Any]:
    source = _clean(text)
    table_match = re.search(r"CREATE\s+TABLE\s+([A-Z0-9_]+)\.([A-Z0-9_]+)\s*\((.*?)\)\s*;", source, re.I | re.S)
    if not table_match:
        raise ValueError("Db2 DDL contains no CREATE TABLE statement")
    schema, name, body = table_match.groups()
    columns: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    for ordinal, item in enumerate(_split_commas(body), 1):
        primary = re.match(r"PRIMARY\s+KEY\s*\(([^)]*)\)", item, re.I)
        if primary:
            constraints.append({
                "id": "pk:" + name.upper(), "kind": "primary_key",
                "columns": [value.strip().upper() for value in primary.group(1).split(",")],
            })
            continue
        match = re.match(r"([A-Z0-9_]+)\s+(.+)", item, re.I | re.S)
        if not match:
            raise ValueError(f"Unsupported Db2 column declaration: {item}")
        column_name, declaration = match.groups()
        type_match = TYPE_PATTERN.match(declaration.strip())
        if not type_match:
            raise ValueError(f"Unsupported Db2 type for {column_name}: {declaration}")
        base, arguments = type_match.groups()
        args = [int(value.strip()) for value in arguments.split(",")] if arguments else []
        columns.append({
            "name": column_name.upper(), "ordinal": ordinal, "source_type": base.upper(),
            "length": args[0] if base.upper() in {"CHAR", "VARCHAR"} and args else None,
            "precision": args[0] if base.upper() == "DECIMAL" and args else None,
            "scale": args[1] if base.upper() == "DECIMAL" and len(args) > 1 else None,
            "nullable": not bool(re.search(r"\bNOT\s+NULL\b", declaration, re.I)),
        })
    indexes = []
    for match in re.finditer(
        r"CREATE\s+(UNIQUE\s+)?INDEX\s+([A-Z0-9_]+)\.([A-Z0-9_]+)\s+ON\s+([A-Z0-9_]+)\.([A-Z0-9_]+)\s*\(([^)]*)\)",
        source, re.I | re.S,
    ):
        unique, index_schema, index_name, table_schema, table_name, index_body = match.groups()
        indexes.append({
            "schema": index_schema.upper(), "name": index_name.upper(), "unique": bool(unique),
            "table": f"{table_schema.upper()}.{table_name.upper()}",
            "columns": [
                {"name": bits[0].upper(), "order": bits[1].upper() if len(bits) > 1 else "ASC"}
                for bits in (value.split() for value in _split_commas(index_body))
            ],
        })
    return seal({
        "schema_version": SCHEMA_VERSION, "model_type": "factorydark-canonical-data-model",
        "source": {"dialect": "db2-zos", "path": path},
        "schema": schema.upper(), "name": name.upper(), "columns": columns,
        "constraints": constraints, "indexes": indexes,
    })


def parse_dcl(text: str, path: str = "") -> dict[str, Any]:
    source = _clean(text)
    declaration = re.search(r"DECLARE\s+[A-Z0-9_]+\.[A-Z0-9_]+\s+TABLE\s*\((.*?)\)\s*END-EXEC", source, re.I | re.S)
    if not declaration:
        raise ValueError("DCL contains no DECLARE TABLE block")
    names = [name.upper() for name in re.findall(r"(?:^|,)\s*([A-Z][A-Z0-9_]*)\s+", declaration.group(1), re.M)]
    return seal({
        "schema_version": SCHEMA_VERSION, "contract_type": "db2-dcl-host-contract",
        "path": path, "declared_columns": names,
        "host_fields": [name.upper() for name in re.findall(r"^\s*\d+\s+([A-Z][A-Z0-9-]+)", source, re.M)],
    })


def parse_embedded_sql(text: str, path: str = "") -> dict[str, Any]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()
    paragraphs: list[tuple[int, str]] = []
    for number, line in enumerate(lines, 1):
        match = re.match(r"^\s{0,7}([0-9A-Z][0-9A-Z-]+)\.\s*(?:$|\s)", line, re.I)
        if match:
            paragraphs.append((number, match.group(1).upper()))
    statements = []
    for ordinal, match in enumerate(re.finditer(r"EXEC\s+SQL\s+(.*?)\s+END-EXEC", normalized, re.I | re.S), 1):
        body = re.sub(r"\s+", " ", match.group(1)).strip()
        line_start = normalized[:match.start()].count("\n") + 1
        line_end = line_start + match.group(0).count("\n")
        operation_match = re.match(r"(INSERT|UPDATE|DELETE|SELECT|INCLUDE)\b", body, re.I)
        if not operation_match:
            continue
        operation = operation_match.group(1).upper()
        table_match = re.search(r"(?:INTO|UPDATE|FROM)\s+([A-Z0-9_.]+)", body, re.I)
        paragraph = next((name for number, name in reversed(paragraphs) if number <= line_start), "PROGRAM")
        columns: list[str] = []
        if operation == "INSERT":
            col_match = re.search(r"INTO\s+[A-Z0-9_.]+\s*\((.*?)\)\s*VALUES", body, re.I)
            columns = [item.strip().upper() for item in _split_commas(col_match.group(1))] if col_match else []
        elif operation == "UPDATE":
            set_match = re.search(r"\bSET\s+(.*?)\s+WHERE\b", body, re.I)
            columns = [item.split("=", 1)[0].strip().upper() for item in _split_commas(set_match.group(1))] if set_match else []
        statements.append({
            "id": f"sql:{Path(path).stem.upper()}:{line_start}:{ordinal}", "operation": operation,
            "table": table_match.group(1).upper() if table_match else None, "columns": columns,
            "paragraph": paragraph, "line_start": line_start, "line_end": line_end,
            "normalized_sql": body,
        })
    return seal({
        "schema_version": SCHEMA_VERSION, "contract_type": "embedded-sql-inventory",
        "path": path, "statements": statements,
    })


def parse_files(ddl_path: Path, dcl_path: Path, program_path: Path) -> dict[str, Any]:
    return {
        "model": parse_db2_ddl(ddl_path.read_text(encoding="utf-8", errors="replace"), ddl_path.as_posix()),
        "dcl": parse_dcl(dcl_path.read_text(encoding="utf-8", errors="replace"), dcl_path.as_posix()),
        "sql": parse_embedded_sql(program_path.read_text(encoding="utf-8", errors="replace"), program_path.as_posix()),
    }
