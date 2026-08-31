from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from lightyear_common.io import source_hashes

from .model import KnowledgeGraph, evidence


LEGACY_SOURCE_ID = "source:aws-carddemo"
MODERN_SOURCE_ID = "source:lightyear-carddemo"
LEGACY_EXTENSIONS = {
    ".asm", ".bms", ".cbl", ".cpy", ".csd", ".ctl", ".dbd", ".dcl", ".ddl",
    ".jcl", ".mac", ".prc", ".psb", ".txt",
}
ASSEMBLER_EXTENSIONS = {".asm", ".mac"}


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _add_file_node(
    graph: KnowledgeGraph,
    prefix: str,
    path: Path,
    root: Path,
    source_id: str,
    language: str,
) -> str:
    relative = _relative(path, root)
    content_sha256, transport_content_sha256 = source_hashes(path)
    return graph.add_node(
        f"{prefix}:file:{relative}",
        "source_file",
        path.name,
        properties={
            "path": relative,
            "language": language,
            "estate": prefix,
            "content_sha256": content_sha256,
            "hash_basis": "normalized-lf",
            "transport_content_sha256": transport_content_sha256,
        },
        evidence_items=[evidence(source_id, relative, 1, max(1, len(_lines(path))))],
    )


def extract_legacy(graph: KnowledgeGraph, root: Path) -> None:
    app_root = root / "app"
    assembler_programs = {
        path.stem.upper()
        for path in app_root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".asm"
    }
    for path in sorted(item for item in app_root.rglob("*") if item.is_file()):
        if path.suffix.lower() not in LEGACY_EXTENSIONS and path.suffix:
            continue
        suffix = path.suffix.lower()
        if suffix in {".cbl"}:
            _extract_cobol(graph, path, root, assembler_programs)
        elif suffix in {".cpy"}:
            _extract_copybook(graph, path, root)
        elif suffix == ".bms":
            _extract_bms(graph, path, root)
        elif suffix == ".csd":
            _extract_csd(graph, path, root)
        elif suffix in ASSEMBLER_EXTENSIONS:
            _extract_assembler(graph, path, root)
        elif suffix == ".ddl":
            _extract_db2_ddl(graph, path, root)
        elif suffix == ".dcl":
            _extract_db2_dcl(graph, path, root)
        elif suffix == ".dbd":
            _extract_ims_dbd(graph, path, root)
        elif suffix == ".psb":
            _extract_ims_psb(graph, path, root)
        elif suffix in {".jcl", ".prc"}:
            _extract_jcl(graph, path, root)
        else:
            _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, suffix.lstrip(".") or "text")
    _resolve_ims_dli_segments(graph)


def _extract_cobol(
    graph: KnowledgeGraph,
    path: Path,
    root: Path,
    assembler_programs: set[str] | None = None,
) -> None:
    lines = _lines(path)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, "cobol")
    joined = "\n".join(lines)
    program_match = re.search(r"\bPROGRAM-ID\.\s+([A-Z0-9-]+)", joined, re.IGNORECASE)
    program_name = (program_match.group(1) if program_match else path.stem).upper().rstrip(".")
    program_id = f"legacy:cobol-program:{program_name}"
    program_line = next(
        (index for index, line in enumerate(lines, 1) if "PROGRAM-ID" in line.upper()), 1
    )
    graph.add_node(
        program_id,
        "cobol_program",
        program_name,
        properties={"path": relative, "language": "COBOL"},
        evidence_items=[evidence(LEGACY_SOURCE_ID, relative, program_line)],
    )
    graph.add_edge(file_id, "DECLARES", program_id)

    file_handles: dict[str, str] = {}
    select_pattern = re.compile(
        r"\bSELECT\s+([A-Z0-9-]+)\s+ASSIGN\s+TO\s+([A-Z0-9-]+)", re.IGNORECASE
    )
    for match in select_pattern.finditer(joined):
        logical_name, dd_name = (value.upper() for value in match.groups())
        line_number = joined[: match.start()].count("\n") + 1
        handle_id = f"legacy:file-handle:{program_name}:{logical_name}"
        dd_id = f"legacy:dd-name:{dd_name}"
        file_handles[logical_name] = handle_id
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_number)]
        graph.add_node(
            handle_id,
            "cobol_file_handle",
            logical_name,
            properties={"program": program_name},
            evidence_items=ev,
        )
        graph.add_node(dd_id, "jcl_dd_name", dd_name)
        graph.add_edge(program_id, "DECLARES", handle_id, evidence_items=ev)
        graph.add_edge(handle_id, "ASSIGNED_TO", dd_id, evidence_items=ev)

    current_scope = program_id
    paragraph_pattern = re.compile(r"^\s{0,7}([0-9A-Z][0-9A-Z-]+)\.\s*(?:$|\s)", re.IGNORECASE)
    for line_number, line in enumerate(lines, 1):
        upper = line.upper()
        paragraph_match = paragraph_pattern.match(line)
        if paragraph_match:
            paragraph_name = paragraph_match.group(1).upper()
            if paragraph_name not in {
                "IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE", "FILE-CONTROL",
                "INPUT-OUTPUT", "WORKING-STORAGE", "LINKAGE", "FILE", "CONFIGURATION",
            } and not paragraph_name.isdigit():
                current_scope = f"legacy:cobol-paragraph:{program_name}:{paragraph_name}"
                graph.add_node(
                    current_scope,
                    "cobol_paragraph",
                    paragraph_name,
                    properties={"program": program_name, "path": relative},
                    evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
                )
                graph.add_edge(program_id, "CONTAINS", current_scope)

        for copy_name in re.findall(r"\bCOPY\s+([A-Z0-9-]+)", upper):
            copy_id = f"legacy:copybook:{copy_name}"
            graph.add_node(copy_id, "copybook", copy_name)
            ev = [evidence(LEGACY_SOURCE_ID, relative, line_number)]
            graph.add_edge(program_id, "USES_COPYBOOK", copy_id, evidence_items=ev)

        for target in re.findall(r"\bPERFORM\s+([0-9A-Z][0-9A-Z-]+)", upper):
            target_id = f"legacy:cobol-paragraph:{program_name}:{target}"
            graph.add_node(target_id, "cobol_paragraph", target, properties={"program": program_name})
            graph.add_edge(
                current_scope,
                "CALLS",
                target_id,
                evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
            )

        for called in re.findall(r"\bCALL\s+['\"]([A-Z0-9-]+)['\"]", upper):
            if called in (assembler_programs or set()):
                called_id = f"legacy:assembler-program:{called}"
                graph.add_node(called_id, "assembler_program", called)
            else:
                called_id = f"legacy:cobol-program:{called}"
                graph.add_node(called_id, "cobol_program", called)
            graph.add_edge(
                current_scope,
                "CALLS",
                called_id,
                evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
            )

        io_patterns = (
            (r"\bREAD\s+([A-Z0-9-]+)", "READS"),
            (r"\bWRITE\s+([A-Z0-9-]+)", "WRITES"),
            (r"\bREWRITE\s+([A-Z0-9-]+)", "WRITES"),
            (r"\bDELETE\s+([A-Z0-9-]+)", "WRITES"),
        )
        for pattern, relation in io_patterns:
            for handle_name in re.findall(pattern, upper):
                handle_id = file_handles.get(handle_name)
                if handle_id:
                    graph.add_edge(
                        current_scope,
                        relation,
                        handle_id,
                        evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
                    )

        open_match = re.search(r"\bOPEN\s+(INPUT|OUTPUT|I-O|EXTEND)\s+([A-Z0-9-]+)", upper)
        if open_match:
            mode, handle_name = open_match.groups()
            handle_id = file_handles.get(handle_name)
            if handle_id:
                relation = "READS" if mode == "INPUT" else "WRITES" if mode in {"OUTPUT", "EXTEND"} else "READS_WRITES"
                graph.add_edge(
                    current_scope,
                    relation,
                    handle_id,
                    properties={"operation": "OPEN", "mode": mode},
                    evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
                )

    _extract_cics_commands(graph, lines, relative, program_id, program_name)
    _extract_embedded_sql(graph, lines, relative, program_id, program_name)
    _extract_ims_dli_calls(graph, lines, relative, program_id, program_name)


def _extract_ims_dli_calls(
    graph: KnowledgeGraph,
    lines: list[str],
    relative: str,
    program_id: str,
    program_name: str,
) -> None:
    """Model statically identifiable EXEC DLI calls without claiming execution."""

    text = "\n".join(lines)
    paragraph_starts: list[tuple[int, str]] = []
    excluded = {
        "IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE", "FILE-CONTROL",
        "INPUT-OUTPUT", "WORKING-STORAGE", "LINKAGE", "FILE", "CONFIGURATION",
    }
    for line_number, line in enumerate(lines, 1):
        match = re.match(r"^\s{0,7}([0-9A-Z][0-9A-Z-]+)\.\s*(?:$|\s)", line, re.IGNORECASE)
        if match and match.group(1).upper() not in excluded and not match.group(1).isdigit():
            paragraph_starts.append((line_number, match.group(1).upper()))

    for occurrence, match in enumerate(
        re.finditer(r"\bEXEC\s+DLI\s+(.*?)\bEND-EXEC", text, re.IGNORECASE | re.DOTALL),
        start=1,
    ):
        body = re.sub(r"\s+", " ", match.group(1)).strip()
        operation_match = re.match(r"(GN|GNP|GU|GHN|GHNP|GHU|ISRT|REPL|DLET|CHKP)\b", body, re.IGNORECASE)
        if not operation_match:
            continue
        operation = operation_match.group(1).upper()
        segment_match = re.search(
            r"\bSEGMENT\s*\(\s*([A-Z0-9$#@-]+)\s*\)", body, re.IGNORECASE
        )
        line_start = text[: match.start()].count("\n") + 1
        line_end = line_start + match.group(0).count("\n")
        paragraph = next(
            (name for number, name in reversed(paragraph_starts) if number <= line_start), None
        )
        scope_id = (
            f"legacy:cobol-paragraph:{program_name}:{paragraph}" if paragraph else program_id
        )
        graph.add_node(
            scope_id,
            "cobol_paragraph" if paragraph else "cobol_program",
            paragraph or program_name,
            properties={"program": program_name, "path": relative},
        )
        statement_id = f"legacy:ims-dli:{program_name}:{line_start}:{occurrence}"
        segment_name = segment_match.group(1).upper() if segment_match else ""
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, line_end)]
        graph.add_node(
            statement_id,
            "ims_dli_statement",
            f"{operation} {segment_name}".strip(),
            properties={
                "operation": operation,
                "program": program_name,
                "paragraph": paragraph or "PROGRAM",
                "segment": segment_name,
                "normalized_call": body,
                "evidence_class": "static-source",
                "runtime_observed": False,
            },
            evidence_items=ev,
        )
        graph.add_edge(scope_id, "ISSUES_DLI", statement_id, evidence_items=ev)


def _resolve_ims_dli_segments(graph: KnowledgeGraph) -> None:
    """Resolve DLI segment names through the program's PSB/PCB view where possible."""

    outgoing: dict[str, list[dict[str, object]]] = {}
    for edge in graph.edges.values():
        outgoing.setdefault(edge["source"], []).append(edge)
    segments_by_name: dict[str, set[str]] = {}
    for node in graph.nodes.values():
        if node["kind"] == "ims_segment":
            segments_by_name.setdefault(node["name"].upper(), set()).add(node["id"])

    read_operations = {"GN", "GNP", "GU", "GHN", "GHNP", "GHU"}
    write_operations = {"ISRT", "REPL", "DLET"}
    for statement in graph.nodes.values():
        if statement["kind"] != "ims_dli_statement":
            continue
        segment_name = statement["properties"].get("segment", "")
        if not segment_name:
            statement["properties"]["target_resolution"] = "not-applicable"
            continue
        candidates = set(segments_by_name.get(str(segment_name).upper(), set()))
        program_id = f"legacy:cobol-program:{statement['properties']['program']}"
        authorized: set[str] = set()
        for program_edge in outgoing.get(program_id, []):
            if program_edge["relation"] != "USES_PSB":
                continue
            for psb_edge in outgoing.get(str(program_edge["target"]), []):
                if psb_edge["relation"] != "CONTAINS":
                    continue
                for pcb_edge in outgoing.get(str(psb_edge["target"]), []):
                    if pcb_edge["relation"] == "SENSITIVE_TO":
                        authorized.add(str(pcb_edge["target"]))
        if authorized:
            candidates.intersection_update(authorized)
        if len(candidates) != 1:
            statement["properties"]["target_resolution"] = "ambiguous-or-unresolved"
            continue
        target = next(iter(candidates))
        statement["properties"]["target_resolution"] = "psb-authorized-segment"
        operation = statement["properties"]["operation"]
        relation = (
            "READS_SEGMENT" if operation in read_operations
            else "WRITES_SEGMENT" if operation in write_operations
            else None
        )
        if relation is not None:
            graph.add_edge(
                statement["id"],
                relation,
                target,
                properties={"operation": operation, "runtime_observed": False},
                evidence_items=list(statement["evidence"]),
            )


def _db2_table_id(schema: str, table: str) -> str:
    return f"legacy:db2-table:{schema.upper()}.{table.upper()}"


def _extract_db2_ddl(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    text = "\n".join(lines)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, "db2-ddl")
    table = re.search(r"CREATE\s+TABLE\s+([A-Z0-9_]+)\.([A-Z0-9_]+)\s*\((.*?)\)\s*;", text, re.I | re.S)
    if table:
        schema, name, body = table.groups()
        table_id = _db2_table_id(schema, name)
        line = text[:table.start()].count("\n") + 1
        ev = [evidence(LEGACY_SOURCE_ID, relative, line, line + table.group(0).count("\n"))]
        graph.add_node(table_id, "db2_table", f"{schema.upper()}.{name.upper()}", properties={"schema": schema.upper(), "table": name.upper()}, evidence_items=ev)
        graph.add_edge(file_id, "DECLARES", table_id, evidence_items=ev)
        for ordinal, match in enumerate(re.finditer(r"^\s*([A-Z][A-Z0-9_]*)\s+(CHAR|VARCHAR|DECIMAL|SMALLINT|INTEGER|DATE|TIMESTAMP)\s*(?:\(([^)]*)\))?([^,\n]*)", body, re.I | re.M), 1):
            column, source_type, arguments, tail = match.groups()
            column_id = f"legacy:db2-column:{schema.upper()}.{name.upper()}.{column.upper()}"
            column_line = line + body[:match.start()].count("\n") + 1
            column_ev = [evidence(LEGACY_SOURCE_ID, relative, column_line)]
            graph.add_node(column_id, "db2_column", column.upper(), properties={"ordinal": ordinal, "source_type": source_type.upper(), "arguments": arguments or "", "nullable": not bool(re.search(r"NOT\s+NULL", tail, re.I))}, evidence_items=column_ev)
            graph.add_edge(table_id, "HAS_COLUMN", column_id, evidence_items=column_ev)
        primary = re.search(r"PRIMARY\s+KEY\s*\(([^)]*)\)", body, re.I)
        if primary:
            constraint_id = f"legacy:db2-constraint:{schema.upper()}.{name.upper()}:PRIMARY_KEY"
            constraint_line = line + body[:primary.start()].count("\n") + 1
            constraint_ev = [evidence(LEGACY_SOURCE_ID, relative, constraint_line)]
            graph.add_node(constraint_id, "db2_constraint", f"{name.upper()} primary key", properties={"kind": "primary_key", "columns": [value.strip().upper() for value in primary.group(1).split(",")]}, evidence_items=constraint_ev)
            graph.add_edge(table_id, "HAS_CONSTRAINT", constraint_id, evidence_items=constraint_ev)
    index = re.search(r"CREATE\s+(UNIQUE\s+)?INDEX\s+([A-Z0-9_]+)\.([A-Z0-9_]+)\s+ON\s+([A-Z0-9_]+)\.([A-Z0-9_]+)\s*\(([^)]*)\)", text, re.I | re.S)
    if index:
        unique, index_schema, index_name, table_schema, table_name, columns = index.groups()
        index_id = f"legacy:db2-index:{index_schema.upper()}.{index_name.upper()}"
        table_id = _db2_table_id(table_schema, table_name)
        line = text[:index.start()].count("\n") + 1
        ev = [evidence(LEGACY_SOURCE_ID, relative, line, line + index.group(0).count("\n"))]
        graph.add_node(table_id, "db2_table", f"{table_schema.upper()}.{table_name.upper()}")
        graph.add_node(index_id, "db2_index", f"{index_schema.upper()}.{index_name.upper()}", properties={"unique": bool(unique), "columns": re.sub(r"\s+", " ", columns).strip()}, evidence_items=ev)
        graph.add_edge(file_id, "DECLARES", index_id, evidence_items=ev)
        graph.add_edge(index_id, "INDEXES", table_id, evidence_items=ev)


def _extract_db2_dcl(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    text = "\n".join(lines)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, "db2-dcl")
    table = re.search(r"DECLARE\s+([A-Z0-9_]+)\.([A-Z0-9_]+)\s+TABLE", text, re.I)
    if not table:
        return
    schema, name = table.groups()
    dcl_id = f"legacy:db2-dcl:{schema.upper()}.{name.upper()}"
    table_id = _db2_table_id(schema, name)
    line = text[:table.start()].count("\n") + 1
    ev = [evidence(LEGACY_SOURCE_ID, relative, line)]
    graph.add_node(table_id, "db2_table", f"{schema.upper()}.{name.upper()}")
    graph.add_node(dcl_id, "db2_dcl", f"{schema.upper()}.{name.upper()} host contract", properties={"table": f"{schema.upper()}.{name.upper()}"}, evidence_items=ev)
    graph.add_edge(file_id, "DECLARES", dcl_id, evidence_items=ev)
    graph.add_edge(dcl_id, "DESCRIBES", table_id, evidence_items=ev)


def _extract_embedded_sql(graph: KnowledgeGraph, lines: list[str], relative: str, program_id: str, program_name: str) -> None:
    text = "\n".join(lines)
    paragraphs: list[tuple[int, str]] = []
    for number, line in enumerate(lines, 1):
        match = re.match(r"^\s{0,7}([0-9A-Z][0-9A-Z-]+)\.\s*(?:$|\s)", line, re.I)
        if match:
            paragraphs.append((number, match.group(1).upper()))
    for occurrence, match in enumerate(re.finditer(r"EXEC\s+SQL\s+(.*?)\s+END-EXEC", text, re.I | re.S), 1):
        body = re.sub(r"\s+", " ", match.group(1)).strip()
        operation_match = re.match(r"(INSERT|UPDATE|DELETE|SELECT)\b", body, re.I)
        table_match = re.search(r"(?:INTO|UPDATE|FROM)\s+(?:([A-Z0-9_]+)\.)?([A-Z0-9_]+)", body, re.I)
        if not operation_match or not table_match:
            continue
        operation = operation_match.group(1).upper()
        schema = (table_match.group(1) or "CARDDEMO").upper()
        table_name = table_match.group(2).upper()
        line_start = text[:match.start()].count("\n") + 1
        line_end = line_start + match.group(0).count("\n")
        paragraph = next((name for number, name in reversed(paragraphs) if number <= line_start), None)
        scope_id = f"legacy:cobol-paragraph:{program_name}:{paragraph}" if paragraph else program_id
        graph.add_node(scope_id, "cobol_paragraph" if paragraph else "cobol_program", paragraph or program_name, properties={"program": program_name, "path": relative})
        statement_id = f"legacy:db2-sql:{program_name}:{line_start}:{occurrence}"
        table_id = _db2_table_id(schema, table_name)
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, line_end)]
        graph.add_node(table_id, "db2_table", f"{schema}.{table_name}")
        graph.add_node(statement_id, "db2_sql_statement", f"{operation} {schema}.{table_name}", properties={"operation": operation, "program": program_name, "paragraph": paragraph or "PROGRAM", "normalized_sql": body}, evidence_items=ev)
        graph.add_edge(scope_id, "ISSUES_SQL", statement_id, evidence_items=ev)
        graph.add_edge(statement_id, "READS_TABLE" if operation == "SELECT" else "WRITES_TABLE", table_id, evidence_items=ev)
        referenced: set[str] = set()
        if operation == "INSERT":
            columns = re.search(r"INTO\s+(?:[A-Z0-9_]+\.)?[A-Z0-9_]+\s*\((.*?)\)\s*VALUES", body, re.I)
            if columns:
                referenced.update(value.strip().upper() for value in columns.group(1).split(","))
        elif operation == "UPDATE":
            assignments = re.search(r"\bSET\s+(.*?)\s+WHERE\b", body, re.I)
            if assignments:
                referenced.update(value.split("=", 1)[0].strip().upper() for value in assignments.group(1).split(","))
        where = re.search(r"\bWHERE\s+(.*)", body, re.I)
        if where:
            referenced.update(value.upper() for value in re.findall(r"\b([A-Z][A-Z0-9_]*)\s*=", where.group(1), re.I))
        for column in sorted(referenced):
            column_id = f"legacy:db2-column:{schema}.{table_name}.{column}"
            graph.add_node(column_id, "db2_column", column)
            graph.add_edge(statement_id, "REFERENCES_COLUMN", column_id, evidence_items=ev)


def _extract_cics_commands(
    graph: KnowledgeGraph,
    lines: list[str],
    relative: str,
    program_id: str,
    program_name: str,
) -> None:
    """Extract EXEC CICS blocks and resolve literal resource names.

    This intentionally models the command boundary instead of pretending to be a
    full COBOL parser. Every inferred link retains the exact command span and the
    literal's source span remains available on the program source node.
    """
    joined = "\n".join(lines)
    literals = {
        name.upper(): value.strip().upper()
        for name, value in re.findall(
            r"\b(LIT-[A-Z0-9-]+)\s+PIC\s+[^\n]+\n\s*VALUE\s+'([^']*)'",
            joined,
            re.IGNORECASE,
        )
    }
    paragraph_starts: list[tuple[int, str]] = []
    paragraph_pattern = re.compile(r"^\s{0,7}([0-9A-Z][0-9A-Z-]+)\.\s*(?:$|\s)", re.IGNORECASE)
    excluded = {
        "IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE", "FILE-CONTROL",
        "INPUT-OUTPUT", "WORKING-STORAGE", "LINKAGE", "FILE", "CONFIGURATION",
    }
    for line_number, line in enumerate(lines, 1):
        match = paragraph_pattern.match(line)
        if match and match.group(1).upper() not in excluded and not match.group(1).isdigit():
            paragraph_starts.append((line_number, match.group(1).upper()))

    for occurrence, match in enumerate(
        re.finditer(r"\bEXEC\s+CICS\s+(.*?)\bEND-EXEC", joined, re.IGNORECASE | re.DOTALL),
        start=1,
    ):
        body = re.sub(r"\s+", " ", match.group(1)).strip()
        if not body:
            continue
        line_start = joined[: match.start()].count("\n") + 1
        line_end = line_start + match.group(0).count("\n")
        words = body.split()
        command = words[0].upper()
        specialized = re.match(r"^(SEND|RECEIVE)\s+(MAP|TEXT)\b", body, re.IGNORECASE)
        if specialized:
            command = f"{specialized.group(1).upper()} {specialized.group(2).upper()}"
        scope = program_id
        for paragraph_line, paragraph_name in paragraph_starts:
            if paragraph_line > line_start:
                break
            scope = f"legacy:cobol-paragraph:{program_name}:{paragraph_name}"
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, line_end)]
        command_id = f"legacy:cics-command:{program_name}:{line_start}:{occurrence}"
        operands: dict[str, str] = {}
        for key, raw in re.findall(
            r"\b(MAPSET|MAP|DATASET|FILE|PROGRAM|TRANSID)\s*\(\s*([^)]+?)\s*\)",
            body,
            re.IGNORECASE,
        ):
            token = raw.strip().strip("'\"").upper()
            operands[key.upper()] = literals.get(token, token).strip()
        graph.add_node(
            command_id,
            "cics_command",
            command,
            properties={"command": command, "operands": operands, "program": program_name},
            evidence_items=ev,
        )
        graph.add_edge(scope, "ISSUES", command_id, evidence_items=ev)

        mapset = operands.get("MAPSET")
        map_name = operands.get("MAP")
        if mapset:
            mapset_id = f"legacy:bms-mapset:{mapset}"
            graph.add_node(mapset_id, "bms_mapset", mapset)
            graph.add_edge(command_id, "USES_MAPSET", mapset_id, evidence_items=ev)
        if map_name:
            map_id = f"legacy:bms-map:{map_name}"
            graph.add_node(map_id, "bms_map", map_name)
            graph.add_edge(command_id, "USES_MAP", map_id, evidence_items=ev)
        resource = operands.get("DATASET") or operands.get("FILE")
        if resource:
            file_id = f"legacy:cics-file:{resource}"
            graph.add_node(file_id, "cics_file_resource", resource)
            graph.add_edge(
                command_id,
                "ACCESSES",
                file_id,
                properties={"operation": command},
                evidence_items=ev,
            )


def _logical_macro_statements(lines: list[str]) -> list[tuple[int, int, str]]:
    statements: list[tuple[int, int, str]] = []
    current: list[str] = []
    start = 1
    for line_number, line in enumerate(lines, 1):
        if not current:
            start = line_number
        current.append(line.rstrip().removesuffix("-").strip())
        if not line.rstrip().endswith("-"):
            statements.append((start, line_number, " ".join(current)))
            current = []
    if current:
        statements.append((start, len(lines), " ".join(current)))
    return statements


def _macro_attributes(text: str) -> dict[str, str]:
    return {
        key.upper(): value.strip().strip("'")
        for key, value in re.findall(
            r"\b([A-Z][A-Z0-9]+)\s*=\s*(\([^)]*\)|'[^']*'|[^,\s]+)",
            text,
            re.IGNORECASE,
        )
    }


def _extract_bms(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, "bms")
    current_mapset: str | None = None
    current_map: str | None = None
    anonymous = 0
    for line_start, line_end, statement in _logical_macro_statements(lines):
        match = re.match(r"^([A-Z0-9-]*)\s+(DFHMSD|DFHMDI|DFHMDF)\b(.*)$", statement, re.IGNORECASE)
        if not match:
            continue
        label, macro, remainder = match.groups()
        label = label.upper()
        macro = macro.upper()
        attrs = _macro_attributes(remainder)
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, line_end)]
        if macro == "DFHMSD":
            current_mapset = label or path.stem.upper()
            mapset_id = f"legacy:bms-mapset:{current_mapset}"
            graph.add_node(mapset_id, "bms_mapset", current_mapset, properties=attrs, evidence_items=ev)
            graph.add_edge(file_id, "DECLARES", mapset_id, evidence_items=ev)
        elif macro == "DFHMDI" and current_mapset:
            current_map = label
            map_id = f"legacy:bms-map:{current_map}"
            graph.add_node(map_id, "bms_map", current_map, properties=attrs, evidence_items=ev)
            graph.add_edge(f"legacy:bms-mapset:{current_mapset}", "HAS_MAP", map_id, evidence_items=ev)
        elif macro == "DFHMDF" and current_map:
            anonymous += 1
            field_name = label or f"ANONYMOUS-{anonymous}"
            field_id = f"legacy:bms-field:{current_map}:{field_name}:{line_start}"
            graph.add_node(
                field_id,
                "bms_field",
                field_name,
                properties={**attrs, "map": current_map, "mapset": current_mapset},
                evidence_items=ev,
            )
            graph.add_edge(f"legacy:bms-map:{current_map}", "HAS_FIELD", field_id, evidence_items=ev)


def _csd_blocks(lines: list[str]) -> list[tuple[int, int, str, str, str]]:
    starts = [
        (index, match.group(1).upper(), match.group(2).upper())
        for index, line in enumerate(lines, 1)
        if (match := re.match(r"^\s*DEFINE\s+([A-Z]+)\(([^)]+)\)", line, re.IGNORECASE))
    ]
    blocks = []
    for offset, (line_start, kind, name) in enumerate(starts):
        line_end = starts[offset + 1][0] - 1 if offset + 1 < len(starts) else len(lines)
        blocks.append((line_start, line_end, kind, name, " ".join(lines[line_start - 1 : line_end])))
    return blocks


def _extract_csd(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, "csd")
    for line_start, line_end, resource_kind, name, block in _csd_blocks(lines):
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, line_end)]
        properties = {key.lower(): value for key, value in re.findall(r"\b([A-Z][A-Z0-9]+)\(([^)]*)\)", block)}
        if resource_kind == "TRANSACTION":
            node_id = f"legacy:cics-transaction:{name}"
            graph.add_node(node_id, "cics_transaction", name, properties=properties, evidence_items=ev)
            graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)
            program = properties.get("program", "").upper()
            if program:
                target = f"legacy:cics-program-resource:{program}"
                graph.add_node(target, "cics_program_resource", program)
                graph.add_edge(node_id, "STARTS_PROGRAM", target, evidence_items=ev)
        elif resource_kind == "PROGRAM":
            node_id = f"legacy:cics-program-resource:{name}"
            graph.add_node(node_id, "cics_program_resource", name, properties=properties, evidence_items=ev)
            graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)
            target = f"legacy:cobol-program:{name}"
            graph.add_node(target, "cobol_program", name)
            graph.add_edge(node_id, "RESOLVES_TO", target, evidence_items=ev)
        elif resource_kind == "FILE":
            node_id = f"legacy:cics-file:{name}"
            graph.add_node(node_id, "cics_file_resource", name, properties=properties, evidence_items=ev)
            graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)
            dsn = properties.get("dsname", "").upper()
            if dsn:
                target_kind = "vsam_path" if dsn.endswith(".PATH") else "vsam_cluster"
                prefix = "vsam-path" if target_kind == "vsam_path" else "vsam-cluster"
                target = f"legacy:{prefix}:{dsn}"
                graph.add_node(target, target_kind, dsn)
                graph.add_edge(node_id, "BACKED_BY", target, evidence_items=ev)
        elif resource_kind == "MAPSET":
            node_id = f"legacy:bms-mapset:{name}"
            graph.add_node(node_id, "bms_mapset", name, properties=properties, evidence_items=ev)
            graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)


def _hlasm_parts(line: str) -> tuple[str, str, str] | None:
    """Return label, operation, and operands for one physical HLASM line."""
    if not line.strip() or line.lstrip().startswith("*"):
        return None
    body = line[:71].rstrip()
    tokens = body.split(None, 2)
    if not tokens:
        return None
    has_label = bool(body and not body[0].isspace())
    if has_label:
        label = tokens[0].upper()
        operation = tokens[1].upper() if len(tokens) > 1 else ""
        operands = tokens[2].strip() if len(tokens) > 2 else ""
    else:
        label = ""
        operation = tokens[0].upper()
        operands = tokens[1].strip() if len(tokens) > 1 else ""
        if len(tokens) > 2:
            operands = f"{operands} {tokens[2]}".strip()
    return label, operation, operands


_HLASM_DIRECTIVES = {
    "AMODE", "CSECT", "COPY", "DC", "DROP", "DS", "DSECT", "END", "ENTRY",
    "EQU", "EXITCTL", "ICTL", "LTORG", "MACRO", "MEND", "ORG", "PRINT", "RMODE",
    "SPACE", "START", "TITLE", "USING",
}
_HLASM_BRANCHES = {
    "B", "BAL", "BALR", "BAS", "BASR", "BC", "BCR", "BE", "BH", "BL", "BM", "BNE",
    "BNH", "BNL", "BNM", "BNO", "BNP", "BNZ", "BO", "BP", "BR", "BZ", "J", "JE",
    "JH", "JL", "JNE", "JNH", "JNL", "JNM", "JNO", "JNP", "JNZ", "JO", "JP", "JZ",
}


def _extract_assembler(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    relative = _relative(path, root)
    language = "hlasm-macro" if path.suffix.lower() == ".mac" else "hlasm"
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, language)
    parsed = [(line_number, parts) for line_number, line in enumerate(lines, 1)
              if (parts := _hlasm_parts(line))]

    macro_name: str | None = None
    for index, (_, (_, operation, _)) in enumerate(parsed):
        if operation == "MACRO" and index + 1 < len(parsed):
            macro_name = parsed[index + 1][1][1]
            break
    if macro_name:
        header_line = next(number for number, parts in parsed if parts[1] == macro_name)
        macro_id = f"legacy:assembler-macro:{macro_name}"
        ev = [evidence(LEGACY_SOURCE_ID, relative, header_line)]
        graph.add_node(
            macro_id,
            "assembler_macro",
            macro_name,
            properties={"path": relative, "language": "HLASM"},
            evidence_items=ev,
        )
        graph.add_edge(file_id, "DECLARES", macro_id, evidence_items=ev)

    dsects: dict[str, str] = {}
    for line_number, (label, operation, _) in parsed:
        if operation == "DSECT" and label:
            dsect_id = f"legacy:assembler-dsect:{label}"
            dsects[label] = dsect_id
            ev = [evidence(LEGACY_SOURCE_ID, relative, line_number)]
            graph.add_node(
                dsect_id,
                "assembler_dsect",
                label,
                properties={"path": relative},
                evidence_items=ev,
            )
            graph.add_edge(file_id, "DECLARES", dsect_id, evidence_items=ev)

    if path.suffix.lower() == ".mac" and dsects:
        current_dsect: str | None = None
        for line_number, (label, operation, operands) in parsed:
            if operation == "DSECT" and label:
                current_dsect = dsects[label]
                continue
            if current_dsect and label and operation in {"DS", "DC"}:
                field_id = f"legacy:assembler-field:{current_dsect.rsplit(':', 1)[-1]}:{label}"
                ev = [evidence(LEGACY_SOURCE_ID, relative, line_number)]
                graph.add_node(
                    field_id,
                    "assembler_field",
                    label,
                    properties={"declaration": operands, "storage": operation},
                    evidence_items=ev,
                )
                graph.add_edge(current_dsect, "HAS_FIELD", field_id, evidence_items=ev)

    if path.suffix.lower() != ".asm":
        return

    entry = next(
        ((line_number, label, operation) for line_number, (label, operation, _) in parsed
         if operation in {"CSECT", "START"} and label),
        (1, path.stem.upper(), "UNKNOWN"),
    )
    entry_line, program_name, entry_directive = entry
    program_id = f"legacy:assembler-program:{program_name}"
    program_ev = [evidence(LEGACY_SOURCE_ID, relative, entry_line)]
    graph.add_node(
        program_id,
        "assembler_program",
        program_name,
        properties={"entry_directive": entry_directive, "language": "HLASM", "path": relative},
        evidence_items=program_ev,
    )
    graph.add_edge(file_id, "DECLARES", program_id, evidence_items=program_ev)

    symbols: dict[str, str] = {}
    instruction_sequence = 0
    known_macro_files = {
        candidate.stem.upper()
        for candidate in (root / "app" / "maclib").glob("*.mac")
    }
    for line_number, (label, operation, operands) in parsed:
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_number)]
        if label and operation not in {"CSECT", "START", "DSECT"}:
            symbol_id = f"legacy:assembler-symbol:{program_name}:{label}"
            symbols[label] = symbol_id
            graph.add_node(
                symbol_id,
                "assembler_symbol",
                label,
                properties={"operation": operation, "program": program_name},
                evidence_items=ev,
            )
            graph.add_edge(program_id, "CONTAINS", symbol_id, evidence_items=ev)
        if operation == "COPY":
            dsect_name = operands.split()[0].rstrip(",").upper()
            dsect_id = f"legacy:assembler-dsect:{dsect_name}"
            graph.add_node(dsect_id, "assembler_dsect", dsect_name)
            graph.add_edge(program_id, "USES_DSECT", dsect_id, evidence_items=ev)
        if operation in known_macro_files:
            macro_id = f"legacy:assembler-macro:{operation}"
            graph.add_node(macro_id, "assembler_macro", operation)
            graph.add_edge(program_id, "USES_MACRO", macro_id, evidence_items=ev)
        if operation and operation not in _HLASM_DIRECTIVES and operation not in known_macro_files:
            instruction_sequence += 1
            instruction_id = f"legacy:assembler-instruction:{program_name}:{line_number}:{instruction_sequence}"
            graph.add_node(
                instruction_id,
                "assembler_instruction",
                operation,
                properties={"operands": operands, "program": program_name},
                evidence_items=ev,
            )
            graph.add_edge(program_id, "CONTAINS", instruction_id, evidence_items=ev)
            if operation in _HLASM_BRANCHES and operands:
                target_name = operands.split(",")[-1].split()[0].strip().upper()
                if re.fullmatch(r"[A-Z$#@][A-Z0-9$#@]*", target_name):
                    target_id = f"legacy:assembler-symbol:{program_name}:{target_name}"
                    graph.add_node(
                        target_id,
                        "assembler_symbol",
                        target_name,
                        properties={"program": program_name},
                    )
                    graph.add_edge(instruction_id, "BRANCHES_TO", target_id, evidence_items=ev)


def _ims_statements(lines: list[str], operations: set[str]) -> list[tuple[int, int, str, str, str]]:
    starts: list[tuple[int, str, str, str]] = []
    for line_number, line in enumerate(lines, 1):
        parts = _hlasm_parts(line)
        if not parts:
            continue
        label, operation, operands = parts
        if operation in operations:
            starts.append((line_number, label, operation, operands))
    result = []
    for index, (line_start, label, operation, operands) in enumerate(starts):
        line_end = starts[index + 1][0] - 1 if index + 1 < len(starts) else line_start
        continuation = " ".join(
            line[:71].rstrip().rstrip("CX").strip()
            for line in lines[line_start:line_end]
            if line.strip() and not line.lstrip().startswith("*")
        )
        result.append((line_start, line_end, label, operation, f"{operands} {continuation}".strip()))
    return result


def _ims_attrs(text: str) -> dict[str, str]:
    return {
        key.upper(): value.strip().strip("'")
        for key, value in re.findall(
            r"\b([A-Z][A-Z0-9]+)\s*=\s*(\([^)]*\)|'[^']*'|[^,\s]+)",
            text,
            re.IGNORECASE,
        )
    }


def _extract_ims_dbd(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, "ims-dbd")
    statements = _ims_statements(lines, {"DBD", "DATASET", "SEGM", "FIELD", "LCHILD"})
    dbd_stmt = next((item for item in statements if item[3] == "DBD"), None)
    if not dbd_stmt:
        return
    line_start, line_end, _, _, operands = dbd_stmt
    attrs = _ims_attrs(operands)
    dbd_name = attrs.get("NAME", path.stem).strip("()").upper()
    dbd_id = f"legacy:ims-database:{dbd_name}"
    access = attrs.get("ACCESS", "").strip("()").split(",")
    ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, line_end)]
    graph.add_node(
        dbd_id,
        "ims_database",
        dbd_name,
        properties={"access_method": access[0] if access else "", "organization": access, "path": relative},
        evidence_items=ev,
    )
    graph.add_edge(file_id, "DECLARES", dbd_id, evidence_items=ev)
    current_segment: str | None = None
    for line_start, line_end, label, operation, operands in statements:
        attrs = _ims_attrs(operands)
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, line_end)]
        if operation == "DATASET":
            group_name = label or f"GROUP-{line_start}"
            group_id = f"legacy:ims-dataset-group:{dbd_name}:{group_name}"
            graph.add_node(group_id, "ims_dataset_group", group_name, properties=attrs, evidence_items=ev)
            graph.add_edge(dbd_id, "HAS_DATASET_GROUP", group_id, evidence_items=ev)
        elif operation == "SEGM":
            segment_name = attrs.get("NAME", label).strip("()").upper()
            current_segment = f"legacy:ims-segment:{dbd_name}:{segment_name}"
            graph.add_node(
                current_segment,
                "ims_segment",
                segment_name,
                properties={**attrs, "database": dbd_name},
                evidence_items=ev,
            )
            graph.add_edge(dbd_id, "CONTAINS", current_segment, evidence_items=ev)
            parent = attrs.get("PARENT", "").strip("()").split(",")[0].strip("()")
            if parent and parent != "0":
                parent_id = f"legacy:ims-segment:{dbd_name}:{parent.upper()}"
                graph.add_node(parent_id, "ims_segment", parent.upper(), properties={"database": dbd_name})
                graph.add_edge(parent_id, "PARENT_OF", current_segment, evidence_items=ev)
        elif operation == "FIELD" and current_segment:
            raw_name = attrs.get("NAME", label).strip("()")
            field_name = raw_name.split(",")[0].upper()
            field_id = f"legacy:ims-field:{dbd_name}:{field_name}"
            graph.add_node(
                field_id,
                "ims_field",
                field_name,
                properties={**attrs, "database": dbd_name},
                evidence_items=ev,
            )
            graph.add_edge(current_segment, "HAS_FIELD", field_id, evidence_items=ev)
        elif operation == "LCHILD" and current_segment:
            raw = attrs.get("NAME", "").strip("()")
            parts = [part.strip().upper() for part in raw.split(",")]
            if len(parts) >= 2:
                target = f"legacy:ims-segment:{parts[1]}:{parts[0]}"
                graph.add_node(target, "ims_segment", parts[0], properties={"database": parts[1]})
                graph.add_edge(current_segment, "INDEXES", target, evidence_items=ev)


def _extract_ims_psb(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, "ims-psb")
    statements = _ims_statements(lines, {"PCB", "SENSEG", "PSBGEN"})
    psb_stmt = next((item for item in statements if item[3] == "PSBGEN"), None)
    if not psb_stmt:
        return
    line_start, line_end, _, _, operands = psb_stmt
    attrs = _ims_attrs(operands)
    psb_name = attrs.get("PSBNAME", path.stem).strip("()").upper()
    psb_id = f"legacy:ims-psb:{psb_name}"
    ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, line_end)]
    graph.add_node(psb_id, "ims_psb", psb_name, properties={**attrs, "path": relative}, evidence_items=ev)
    graph.add_edge(file_id, "DECLARES", psb_id, evidence_items=ev)
    current_pcb: str | None = None
    current_database: str | None = None
    for line_start, line_end, label, operation, operands in statements:
        attrs = _ims_attrs(operands)
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, line_end)]
        if operation == "PCB":
            pcb_name = label or f"PCB-{line_start}"
            current_pcb = f"legacy:ims-pcb:{psb_name}:{pcb_name}"
            current_database = attrs.get("DBDNAME", "").strip("()").upper()
            graph.add_node(current_pcb, "ims_pcb", pcb_name, properties=attrs, evidence_items=ev)
            graph.add_edge(psb_id, "CONTAINS", current_pcb, evidence_items=ev)
            if current_database:
                dbd_id = f"legacy:ims-database:{current_database}"
                graph.add_node(dbd_id, "ims_database", current_database)
                graph.add_edge(current_pcb, "USES_DBD", dbd_id, evidence_items=ev)
        elif operation == "SENSEG" and current_pcb and current_database:
            segment_name = attrs.get("NAME", label).strip("()").upper()
            segment_id = f"legacy:ims-segment:{current_database}:{segment_name}"
            graph.add_node(segment_id, "ims_segment", segment_name, properties={"database": current_database})
            graph.add_edge(current_pcb, "SENSITIVE_TO", segment_id, evidence_items=ev)


def _extract_copybook(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, "copybook")
    name = path.stem.upper()
    copybook_id = f"legacy:copybook:{name}"
    graph.add_node(
        copybook_id,
        "copybook",
        name,
        properties={"path": relative},
        evidence_items=[evidence(LEGACY_SOURCE_ID, relative, 1, max(1, len(lines)))],
    )
    graph.add_edge(file_id, "DECLARES", copybook_id)
    stack: list[tuple[int, str]] = []
    field_pattern = re.compile(r"^\s*(\d{2})\s+([A-Z0-9-]+)(.*)$", re.IGNORECASE)
    for line_number, line in enumerate(lines, 1):
        match = field_pattern.match(line[6:] if len(line) > 6 else line)
        if not match:
            continue
        level = int(match.group(1))
        field_name = match.group(2).upper()
        remainder = match.group(3).upper()
        field_id = f"legacy:cobol-field:{name}:{field_name}:{line_number}"
        picture = re.search(r"\bPIC(?:TURE)?\s+([^\s.]+)", remainder)
        redefines = re.search(r"\bREDEFINES\s+([A-Z0-9-]+)", remainder)
        occurs = re.search(r"\bOCCURS\s+([0-9]+)", remainder)
        graph.add_node(
            field_id,
            "cobol_field",
            field_name,
            properties={
                "copybook": name,
                "level": level,
                "picture": picture.group(1) if picture else "",
                "redefines": redefines.group(1) if redefines else "",
                "occurs": int(occurs.group(1)) if occurs else 1,
            },
            evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
        )
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else copybook_id
        graph.add_edge(parent, "CONTAINS", field_id)
        stack.append((level, field_id))


def _extract_jcl(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, "jcl")
    job_id: str | None = None
    step_id: str | None = None
    allocation_id: str | None = None
    for line_number, line in enumerate(lines, 1):
        job_match = re.match(r"^//([A-Z0-9$#@]+)\s+JOB\b", line, re.IGNORECASE)
        if job_match:
            job_name = job_match.group(1).upper()
            job_id = f"legacy:jcl-job:{job_name}"
            graph.add_node(
                job_id,
                "jcl_job",
                job_name,
                properties={"path": relative},
                evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
            )
            graph.add_edge(file_id, "DECLARES", job_id)
            continue
        exec_match = re.match(
            r"^//([A-Z0-9$#@]+)\s+EXEC\s+(?:PGM=)?([A-Z0-9$#@-]+)", line, re.IGNORECASE
        )
        if exec_match:
            step_name, executable = (value.upper() for value in exec_match.groups())
            owner = job_id or f"legacy:jcl-procedure:{path.stem.upper()}"
            if job_id is None:
                graph.add_node(owner, "jcl_procedure", path.stem.upper(), properties={"path": relative})
                graph.add_edge(file_id, "DECLARES", owner)
            step_id = f"legacy:jcl-step:{owner.rsplit(':', 1)[-1]}:{step_name}"
            graph.add_node(
                step_id,
                "jcl_step",
                step_name,
                properties={"executable": executable, "path": relative},
                evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
            )
            graph.add_edge(owner, "CONTAINS", step_id)
            cobol_program_id = f"legacy:cobol-program:{executable}"
            assembler_program_id = f"legacy:assembler-program:{executable}"
            if cobol_program_id in graph.nodes:
                executable_id = cobol_program_id
            elif assembler_program_id in graph.nodes:
                executable_id = assembler_program_id
            else:
                executable_id = f"legacy:executable:{executable}"
                graph.add_node(
                    executable_id,
                    "executable",
                    executable,
                    properties={"resolution": "external-or-unresolved"},
                )
            graph.add_edge(
                step_id,
                "EXECUTES",
                executable_id,
                evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
            )
            allocation_id = None
            continue
        dd_match = re.match(r"^//([A-Z0-9$#@]+)\s+DD\b(.*)$", line, re.IGNORECASE)
        if dd_match and step_id:
            dd_name, remainder = dd_match.groups()
            dd_name = dd_name.upper()
            allocation_id = f"legacy:jcl-dd:{step_id.rsplit(':', 2)[-2]}:{step_id.rsplit(':', 1)[-1]}:{dd_name}"
            dd_name_id = f"legacy:dd-name:{dd_name}"
            graph.add_node(
                allocation_id,
                "jcl_dd_allocation",
                dd_name,
                properties={"path": relative},
                evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
            )
            graph.add_node(dd_name_id, "jcl_dd_name", dd_name)
            graph.add_edge(step_id, "HAS_DD", allocation_id)
            graph.add_edge(allocation_id, "BINDS", dd_name_id)
            _extract_dsn(graph, allocation_id, remainder, relative, line_number)
            continue
        if allocation_id and line.startswith("//"):
            _extract_dsn(graph, allocation_id, line, relative, line_number)

    _extract_idcams(graph, file_id, lines, relative)
    _extract_ims_jcl_bindings(graph, lines, relative)


def _extract_ims_jcl_bindings(
    graph: KnowledgeGraph, lines: list[str], relative: str
) -> None:
    """Bind IMS BMP/DLI program identities to the PSB named in EXEC parameters."""
    joined = "\n".join(lines)
    for match in re.finditer(
        r"PARM\s*=\s*['\"](?:BMP|DLI)\s*,\s*([A-Z0-9$#@-]+)\s*,\s*([A-Z0-9$#@-]+)",
        joined,
        re.IGNORECASE,
    ):
        program_name, psb_name = (value.upper() for value in match.groups())
        program_id = f"legacy:cobol-program:{program_name}"
        if program_id not in graph.nodes:
            assembler_id = f"legacy:assembler-program:{program_name}"
            if assembler_id in graph.nodes:
                program_id = assembler_id
            else:
                graph.add_node(program_id, "cobol_program", program_name)
        psb_id = f"legacy:ims-psb:{psb_name}"
        graph.add_node(psb_id, "ims_psb", psb_name)
        line_number = joined[: match.start()].count("\n") + 1
        graph.add_edge(
            program_id,
            "USES_PSB",
            psb_id,
            evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
        )


def _extract_idcams(
    graph: KnowledgeGraph, file_id: str, lines: list[str], relative: str
) -> None:
    """Extract VSAM catalog definitions embedded in IDCAMS SYSIN streams."""
    normalized_lines = [line.rstrip().removesuffix("-").strip() for line in lines]
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(normalized_lines, 1):
        match = re.match(r"^DEFINE\s+(CLUSTER|ALTERNATEINDEX|PATH)\b", line, re.IGNORECASE)
        if match:
            starts.append((index, match.group(1).upper()))
    for offset, (line_start, definition) in enumerate(starts):
        next_start = starts[offset + 1][0] if offset + 1 < len(starts) else len(lines) + 1
        line_end = next_start - 1
        for index in range(line_start, next_start):
            if normalized_lines[index - 1].startswith("/*"):
                line_end = index - 1
                break
        block = " ".join(normalized_lines[line_start - 1 : line_end])
        names = re.findall(r"\bNAME\s*\(\s*([A-Z0-9.$#@-]+)\s*\)", block, re.IGNORECASE)
        if not names:
            continue
        name = names[0].upper()
        ev = [evidence(LEGACY_SOURCE_ID, relative, line_start, max(line_start, line_end))]
        common: dict[str, object] = {}
        keys = re.search(r"\bKEYS\s*\(\s*(\d+)\s*[, ]\s*(\d+)\s*\)", block, re.IGNORECASE)
        records = re.search(r"\bRECORDSIZE\s*\(\s*(\d+)\s*[, ]\s*(\d+)\s*\)", block, re.IGNORECASE)
        shares = re.search(r"\bSHAREOPTIONS\s*\(\s*(\d+)\s*[, ]\s*(\d+)\s*\)", block, re.IGNORECASE)
        if keys:
            common.update({"key_length": int(keys.group(1)), "key_offset": int(keys.group(2))})
        if records:
            common.update({"record_size_min": int(records.group(1)), "record_size_max": int(records.group(2))})
        if shares:
            common.update({"share_cross_region": int(shares.group(1)), "share_cross_system": int(shares.group(2))})
        common.update({
            "erase": bool(re.search(r"\bERASE\b", block, re.IGNORECASE)),
            "reuse": bool(re.search(r"\bREUSE\b", block, re.IGNORECASE)),
        })

        if definition == "CLUSTER":
            organization = (
                "KSDS" if re.search(r"\bINDEXED\b", block, re.IGNORECASE)
                else "RRDS" if re.search(r"\bNUMBERED\b", block, re.IGNORECASE)
                else "LDS" if re.search(r"\bLINEAR\b", block, re.IGNORECASE)
                else "ESDS" if re.search(r"\bNONINDEXED\b", block, re.IGNORECASE)
                else "UNKNOWN"
            )
            node_id = f"legacy:vsam-cluster:{name}"
            graph.add_node(
                node_id,
                "vsam_cluster",
                name,
                properties={**common, "organization": organization},
                evidence_items=ev,
            )
            graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)
            for component_name in names[1:]:
                component_name = component_name.upper()
                component_id = f"legacy:vsam-component:{component_name}"
                component_type = "INDEX" if component_name.endswith(".INDEX") else "DATA"
                graph.add_node(
                    component_id,
                    "vsam_component",
                    component_name,
                    properties={"component_type": component_type},
                    evidence_items=ev,
                )
                graph.add_edge(node_id, "HAS_COMPONENT", component_id, evidence_items=ev)
        elif definition == "ALTERNATEINDEX":
            node_id = f"legacy:vsam-alternate-index:{name}"
            graph.add_node(node_id, "vsam_alternate_index", name, properties=common, evidence_items=ev)
            graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)
            relate = re.search(r"\bRELATE\s*\(\s*([A-Z0-9.$#@-]+)\s*\)", block, re.IGNORECASE)
            if relate:
                target_name = relate.group(1).upper()
                target = f"legacy:vsam-cluster:{target_name}"
                graph.add_node(target, "vsam_cluster", target_name)
                graph.add_edge(node_id, "TARGETS", target, evidence_items=ev)
        else:
            node_id = f"legacy:vsam-path:{name}"
            graph.add_node(node_id, "vsam_path", name, evidence_items=ev)
            graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)
            entry = re.search(r"\bPATHENTRY\s*\(\s*([A-Z0-9.$#@-]+)\s*\)", block, re.IGNORECASE)
            if entry:
                target_name = entry.group(1).upper()
                target = f"legacy:vsam-alternate-index:{target_name}"
                graph.add_node(target, "vsam_alternate_index", target_name)
                graph.add_edge(node_id, "TARGETS", target, evidence_items=ev)

        dataset_id = f"legacy:dataset:{name}"
        if dataset_id in graph.nodes:
            graph.add_edge(dataset_id, "RESOLVES_TO", node_id, evidence_items=ev)


def _extract_dsn(
    graph: KnowledgeGraph, allocation_id: str, text: str, relative: str, line_number: int
) -> None:
    dsn_match = re.search(r"\bDSN=([^,\s]+)", text, re.IGNORECASE)
    if not dsn_match:
        return
    dsn = dsn_match.group(1).upper()
    dataset_id = f"legacy:dataset:{dsn}"
    graph.add_node(dataset_id, "dataset", dsn)
    graph.add_edge(
        allocation_id,
        "ALLOCATES",
        dataset_id,
        evidence_items=[evidence(LEGACY_SOURCE_ID, relative, line_number)],
    )


def extract_modern(
    graph: KnowledgeGraph,
    root: Path,
    declared_paths: list[Path] | None = None,
) -> None:
    if declared_paths is None:
        java_root = root / "candidate-java"
        java_paths = sorted(java_root.rglob("*.java"))
        pom_paths = [java_root / "pom.xml"] if (java_root / "pom.xml").exists() else []
        python_paths = sorted(
            {
                *root.joinpath("src").rglob("*.py"),
                *root.joinpath("tests").rglob("*.py"),
                *root.joinpath("factory").rglob("*.py"),
            }
        )
    else:
        java_paths = sorted(path for path in declared_paths if path.suffix.casefold() == ".java")
        pom_paths = sorted(path for path in declared_paths if path.name == "pom.xml")
        python_paths = sorted(path for path in declared_paths if path.suffix.casefold() == ".py")

    for path in java_paths:
        _extract_java(graph, path, root)
    for path in pom_paths:
        _extract_maven(graph, path, root)
    for path in python_paths:
        _add_file_node(graph, "modern", path, root, MODERN_SOURCE_ID, "python")


def _extract_java(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    lines = _lines(path)
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "modern", path, root, MODERN_SOURCE_ID, "java")
    package = ""
    current_type_id: str | None = None
    current_type_name = ""
    pending_test = False
    method_pattern = re.compile(
        r"^\s*(?:(?:public|protected|private)\s+)?(?:(?:static|final|synchronized)\s+)*"
        r"(?:<[^>]+>\s+)?[A-Za-z0-9_<>,.?\[\] ]+\s+([a-zA-Z_$][\w$]*)\s*\("
    )
    for line_number, line in enumerate(lines, 1):
        package_match = re.match(r"\s*package\s+([\w.]+);", line)
        if package_match:
            package = package_match.group(1)
        type_match = re.search(r"\b(class|record|interface|enum)\s+([A-Za-z_$][\w$]*)", line)
        if type_match and current_type_id is None:
            type_kind, current_type_name = type_match.groups()
            qualified = f"{package}.{current_type_name}" if package else current_type_name
            current_type_id = f"modern:java-type:{qualified}"
            graph.add_node(
                current_type_id,
                "java_type",
                qualified,
                properties={"type": type_kind, "path": relative},
                evidence_items=[evidence(MODERN_SOURCE_ID, relative, line_number)],
            )
            graph.add_edge(file_id, "DECLARES", current_type_id)
        if "@Test" in line:
            pending_test = True
            continue
        method_match = method_pattern.match(line)
        if method_match and current_type_id:
            method_name = method_match.group(1)
            if method_name in {"if", "for", "while", "switch", "catch", "return", "new"}:
                continue
            qualified_type = current_type_id.removeprefix("modern:java-type:")
            kind = "test_case" if pending_test else "java_method"
            prefix = "modern:test" if pending_test else "modern:java-method"
            method_id = f"{prefix}:{qualified_type}#{method_name}"
            graph.add_node(
                method_id,
                kind,
                method_name,
                properties={"type": qualified_type, "path": relative},
                evidence_items=[evidence(MODERN_SOURCE_ID, relative, line_number)],
            )
            graph.add_edge(current_type_id, "CONTAINS", method_id)
            pending_test = False
        elif pending_test and line.strip() and not line.strip().startswith("@"):  # malformed test declaration
            pending_test = False

    if current_type_id:
        for line_number, line in enumerate(lines, 1):
            import_match = re.match(r"\s*import\s+(ai\.lightyear\.[\w.]+);", line)
            if not import_match:
                continue
            imported = import_match.group(1)
            imported_id = f"modern:java-type:{imported.rsplit('.', 1)[0]}.{imported.rsplit('.', 1)[1]}"
            graph.add_node(imported_id, "java_type", imported)
            graph.add_edge(
                current_type_id,
                "DEPENDS_ON",
                imported_id,
                evidence_items=[evidence(MODERN_SOURCE_ID, relative, line_number)],
            )


def _extract_maven(graph: KnowledgeGraph, path: Path, root: Path) -> None:
    relative = _relative(path, root)
    file_id = _add_file_node(graph, "modern", path, root, MODERN_SOURCE_ID, "maven")
    tree = ET.parse(path)
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
    for dependency in tree.findall(".//m:dependency", namespace):
        group = dependency.findtext("m:groupId", default="", namespaces=namespace)
        artifact = dependency.findtext("m:artifactId", default="", namespaces=namespace)
        if not group or not artifact:
            continue
        dependency_id = f"modern:maven-dependency:{group}:{artifact}"
        graph.add_node(
            dependency_id,
            "software_dependency",
            f"{group}:{artifact}",
            properties={"group": group, "artifact": artifact},
        )
        graph.add_edge(file_id, "DECLARES", dependency_id)
