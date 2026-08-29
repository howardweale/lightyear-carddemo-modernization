from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import normalize_logical_source
from lightyear_knowledge_graph.model import KnowledgeGraph, evidence, graph_hash
from lightyear_knowledge_graph.ontology import load_ontology, ontology_identity
from lightyear_knowledge_graph.validation import validate_graph


ANALYSIS_SCHEMA_VERSION = "1.0"
ANALYSIS_TYPE = "lightyear-customer-source-analysis"
SOURCE_ID = "source:pilot-intake"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROGRAM_NAME = r"[A-Z0-9_$#@-]+"
_HLASM_DIRECTIVES = {
    "AMODE", "CSECT", "COPY", "DC", "DROP", "DS", "DSECT", "END", "ENTRY",
    "EQU", "LTORG", "MACRO", "MEND", "ORG", "PRINT", "RMODE", "SPACE", "START",
    "TITLE", "USING",
}
_HLASM_BRANCHES = {
    "B", "BAL", "BALR", "BAS", "BASR", "BC", "BCR", "BE", "BH", "BL", "BM",
    "BNE", "BNH", "BNL", "BNM", "BNO", "BNP", "BNZ", "BO", "BP", "BR", "BZ",
    "J", "JE", "JH", "JL", "JNE", "JNH", "JNL", "JNM", "JNO", "JNP", "JNZ",
    "JO", "JP", "JZ",
}


class AnalysisError(ValueError):
    """Raised when customer-source analysis cannot preserve its evidence boundary."""


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _path_token(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]


def _line(text: str, offset: int) -> int:
    return text[:offset].count("\n") + 1


def _safe_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative:
        raise AnalysisError(f"analysis-source-path-invalid:{relative}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise AnalysisError(f"analysis-source-path-escapes-root:{relative}") from error
    if not resolved.is_file() or resolved.is_symlink():
        raise AnalysisError(f"analysis-source-file-missing-or-linked:{relative}")
    return resolved


def _read_verified(root: Path, item: Mapping[str, Any]) -> tuple[str, bytes]:
    relative = str(item.get("path", ""))
    path = _safe_path(root, relative)
    raw = path.read_bytes()
    logical = normalize_logical_source(raw)
    if hashlib.sha256(raw).hexdigest() != item.get("raw_sha256"):
        raise AnalysisError(f"analysis-raw-source-drift:{relative}")
    if hashlib.sha256(logical).hexdigest() != item.get("logical_sha256"):
        raise AnalysisError(f"analysis-logical-source-drift:{relative}")
    if len(raw) != item.get("bytes"):
        raise AnalysisError(f"analysis-source-size-drift:{relative}")
    try:
        text = logical.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AnalysisError(f"analysis-source-is-not-utf8:{relative}") from error
    if len(text.splitlines()) != item.get("lines"):
        raise AnalysisError(f"analysis-source-line-count-drift:{relative}")
    return text, raw


def _ev(relative: str, line_start: int, line_end: int | None = None) -> list[dict[str, Any]]:
    return [
        evidence(
            SOURCE_ID,
            relative,
            line_start,
            line_end,
            method="bounded-static-analysis",
            confidence="observed",
        )
    ]


def _add_source_file(
    graph: KnowledgeGraph, item: Mapping[str, Any], text: str
) -> str:
    relative = str(item["path"])
    file_id = f"pilot:source-file:{_path_token(relative)}"
    graph.add_node(
        file_id,
        "source_file",
        Path(relative).name,
        properties={
            "path": relative,
            "intake_kind": str(item["kind"]),
            "content_sha256": str(item["logical_sha256"]),
            "transport_content_sha256": str(item["raw_sha256"]),
            "hash_basis": "normalized-lf",
        },
        evidence_items=_ev(relative, 1, max(1, len(text.splitlines()))),
    )
    return file_id


def _program_declaration(
    graph: KnowledgeGraph,
    file_id: str,
    relative: str,
    kind: str,
    name: str,
    line_number: int,
) -> str:
    node_kind = "cobol_program" if kind == "cobol" else "pli_program"
    node_id = f"pilot:{kind}-program:{name}:{_path_token(relative)}"
    ev = _ev(relative, line_number)
    graph.add_node(
        node_id,
        node_kind,
        name,
        properties={"path": relative, "language": "COBOL" if kind == "cobol" else "PL/I"},
        evidence_items=ev,
    )
    graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)
    return node_id


def _resolve(
    declarations: Mapping[tuple[str, str], list[str]], kind: str, name: str
) -> tuple[str | None, str]:
    matches = declarations.get((kind, name.upper()), [])
    if len(matches) == 1:
        return matches[0], "resolved"
    return None, "ambiguous" if matches else "target-not-in-intake"


def _sql_blocks(text: str) -> list[tuple[int, int, str]]:
    return [
        (_line(text, match.start()), _line(text, match.end()), re.sub(r"\s+", " ", match.group(1)).strip())
        for match in re.finditer(r"EXEC\s+SQL\s+(.*?)(?:\s+END-EXEC|;)", text, re.I | re.S)
    ]


def _sql_table(body: str) -> tuple[str, str, str] | None:
    operation_match = re.match(r"(SELECT|INSERT|UPDATE|DELETE)\b", body, re.I)
    table_match = re.search(
        r"(?:FROM|INTO|UPDATE)\s+(?:([A-Z0-9_$#@]+)\.)?([A-Z0-9_$#@]+)",
        body,
        re.I,
    )
    if not operation_match or not table_match:
        return None
    return (
        operation_match.group(1).upper(),
        (table_match.group(1) or "CARDDEMO").upper(),
        table_match.group(2).upper(),
    )


def _hlasm_parts(line: str) -> tuple[str, str, str] | None:
    """Return label, operation, and operands for one bounded HLASM source line."""
    if not line.strip() or line.lstrip().startswith("*"):
        return None
    body = line[:71].rstrip()
    tokens = body.split(None, 2)
    if not tokens:
        return None
    if body and not body[0].isspace():
        return (
            tokens[0].upper(),
            tokens[1].upper() if len(tokens) > 1 else "",
            tokens[2].strip() if len(tokens) > 2 else "",
        )
    operands = tokens[1].strip() if len(tokens) > 1 else ""
    if len(tokens) > 2:
        operands = f"{operands} {tokens[2]}".strip()
    return "", tokens[0].upper(), operands


def _ims_statements(text: str, operations: set[str]) -> list[tuple[int, str, str, str]]:
    statements: list[tuple[int, str, str, str]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        parts = _hlasm_parts(line)
        if parts and parts[1] in operations:
            statements.append((line_number, *parts))
    return statements


def _ims_attrs(text: str) -> dict[str, str]:
    return {
        key.upper(): value.strip().strip("'")
        for key, value in re.findall(
            r"\b([A-Z][A-Z0-9]+)\s*=\s*(\([^)]*\)|'[^']*'|[^,\s]+)",
            text,
            re.I,
        )
    }


def _idcams_blocks(text: str) -> list[tuple[int, int, str, str]]:
    lines = text.splitlines()
    normalized = [line.rstrip().removesuffix("-").strip() for line in lines]
    starts: list[tuple[int, str]] = []
    for line_number, line in enumerate(normalized, 1):
        match = re.match(r"^DEFINE\s+(CLUSTER|ALTERNATEINDEX|PATH)\b", line, re.I)
        if match:
            starts.append((line_number, match.group(1).upper()))
    blocks: list[tuple[int, int, str, str]] = []
    for index, (line_start, definition) in enumerate(starts):
        line_end = starts[index + 1][0] - 1 if index + 1 < len(starts) else len(lines)
        block = " ".join(normalized[line_start - 1 : line_end])
        blocks.append((line_start, line_end, definition, block))
    return blocks


def build_source_analysis(
    source_root: Path,
    intake: Mapping[str, Any],
    profile: Mapping[str, Any],
    ontology_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_root = source_root.resolve()
    ontology = load_ontology(ontology_path)
    files = intake.get("files")
    if not isinstance(files, list) or not files:
        raise AnalysisError("analysis-intake-files-missing")
    if intake.get("pilot_id") != profile.get("pilot_id"):
        raise AnalysisError("analysis-intake-profile-mismatch")
    expected_paths = {str(item.get("path", "")) for item in files if isinstance(item, dict)}
    actual_paths: set[str] = set()
    for path in source_root.rglob("*"):
        if path.is_symlink():
            raise AnalysisError(
                f"analysis-source-file-missing-or-linked:{path.relative_to(source_root).as_posix()}"
            )
        if path.is_file():
            actual_paths.add(path.relative_to(source_root).as_posix())
    if actual_paths != expected_paths:
        raise AnalysisError("analysis-source-inventory-drift")

    graph = KnowledgeGraph(
        f"lightyear:pilot-estate:{str(intake.get('content_sha256', ''))[:24]}",
        [
            {
                "id": SOURCE_ID,
                "kind": "approved_source_directory",
                "intake_sha256": str(intake.get("content_sha256", "")),
                "source_tree_sha256": str(intake.get("source_tree_sha256", "")),
                "source_label": str(intake.get("source_label", "")),
            }
        ],
        ontology_identity(ontology),
    )
    texts: dict[str, str] = {}
    file_nodes: dict[str, str] = {}
    declarations: dict[tuple[str, str], list[str]] = {}
    typed_files: Counter[str] = Counter()
    declared_by_kind: Counter[str] = Counter()
    unresolved: list[dict[str, Any]] = []

    for item in files:
        if not isinstance(item, dict):
            raise AnalysisError("analysis-intake-file-record-invalid")
        relative = str(item.get("path", ""))
        text, _ = _read_verified(source_root, item)
        texts[relative] = text
        file_nodes[relative] = _add_source_file(graph, item, text)
        typed_files[str(item.get("kind", ""))] += 1

    # First pass: declarations that later references may resolve against.
    for item in files:
        relative = str(item["path"])
        kind = str(item["kind"])
        text = texts[relative]
        file_id = file_nodes[relative]
        if kind == "cobol":
            match = re.search(rf"\bPROGRAM-ID\.\s+({_PROGRAM_NAME})", text, re.I)
            if match:
                name = match.group(1).upper().rstrip(".")
                node_id = _program_declaration(graph, file_id, relative, kind, name, _line(text, match.start()))
                declarations.setdefault((kind, name), []).append(node_id)
                declared_by_kind["cobol_program"] += 1
        elif kind == "pli":
            match = re.search(rf"^\s*({_PROGRAM_NAME})\s*:\s*PROC\b", text, re.I | re.M)
            if match:
                name = match.group(1).upper()
                node_id = _program_declaration(graph, file_id, relative, kind, name, _line(text, match.start()))
                declarations.setdefault((kind, name), []).append(node_id)
                declared_by_kind["pli_program"] += 1
        elif kind == "copybook":
            name = Path(relative).stem.upper()
            node_id = f"pilot:copybook:{name}:{_path_token(relative)}"
            graph.add_node(
                node_id,
                "copybook",
                name,
                properties={"path": relative},
                evidence_items=_ev(relative, 1, max(1, len(text.splitlines()))),
            )
            graph.add_edge(file_id, "DECLARES", node_id)
            declarations.setdefault((kind, name), []).append(node_id)
            declared_by_kind["copybook"] += 1
        elif kind == "db2-ddl":
            for match in re.finditer(
                r"CREATE\s+TABLE\s+([A-Z0-9_$#@]+)\.([A-Z0-9_$#@]+)\s*\((.*?)\)\s*;",
                text,
                re.I | re.S,
            ):
                schema, table, body = match.groups()
                qualified = f"{schema.upper()}.{table.upper()}"
                table_id = f"pilot:db2-table:{qualified}:{_path_token(relative)}"
                table_line = _line(text, match.start())
                ev = _ev(relative, table_line, _line(text, match.end()))
                graph.add_node(table_id, "db2_table", qualified, properties={"schema": schema.upper(), "table": table.upper(), "definition_present": True}, evidence_items=ev)
                graph.add_edge(file_id, "DECLARES", table_id, evidence_items=ev)
                declarations.setdefault((kind, qualified), []).append(table_id)
                declared_by_kind["db2_table"] += 1
                ordinal = 0
                for column in re.finditer(r"^\s*([A-Z][A-Z0-9_$#@]*)\s+(CHAR|VARCHAR|DECIMAL|SMALLINT|INTEGER|DATE|TIMESTAMP)\s*(?:\(([^)]*)\))?([^,\n]*)", body, re.I | re.M):
                    ordinal += 1
                    column_name, source_type, arguments, tail = column.groups()
                    column_id = f"pilot:db2-column:{qualified}.{column_name.upper()}:{_path_token(relative)}"
                    line_number = table_line + body[: column.start()].count("\n") + 1
                    column_ev = _ev(relative, line_number)
                    graph.add_node(column_id, "db2_column", column_name.upper(), properties={"ordinal": ordinal, "source_type": source_type.upper(), "arguments": arguments or "", "nullable": not bool(re.search(r"NOT\s+NULL", tail, re.I))}, evidence_items=column_ev)
                    graph.add_edge(table_id, "HAS_COLUMN", column_id, evidence_items=column_ev)
                    declared_by_kind["db2_column"] += 1
                primary = re.search(r"PRIMARY\s+KEY\s*\(([^)]*)\)", body, re.I)
                if primary:
                    constraint_id = f"pilot:db2-constraint:{qualified}:PRIMARY_KEY:{_path_token(relative)}"
                    constraint_ev = _ev(relative, table_line + body[: primary.start()].count("\n") + 1)
                    graph.add_node(constraint_id, "db2_constraint", f"{qualified} primary key", properties={"kind": "primary_key", "columns": [value.strip().upper() for value in primary.group(1).split(",")]}, evidence_items=constraint_ev)
                    graph.add_edge(table_id, "HAS_CONSTRAINT", constraint_id, evidence_items=constraint_ev)
                    declared_by_kind["db2_constraint"] += 1
            for match in re.finditer(r"CREATE\s+(UNIQUE\s+)?INDEX\s+([A-Z0-9_$#@]+)\.([A-Z0-9_$#@]+)\s+ON\s+([A-Z0-9_$#@]+)\.([A-Z0-9_$#@]+)\s*\(([^)]*)\)", text, re.I | re.S):
                unique, index_schema, index_name, table_schema, table_name, columns = match.groups()
                qualified_index = f"{index_schema.upper()}.{index_name.upper()}"
                index_id = f"pilot:db2-index:{qualified_index}:{_path_token(relative)}"
                ev = _ev(relative, _line(text, match.start()), _line(text, match.end()))
                graph.add_node(index_id, "db2_index", qualified_index, properties={"unique": bool(unique), "columns": [value.strip().upper() for value in columns.split(",")]}, evidence_items=ev)
                graph.add_edge(file_id, "DECLARES", index_id, evidence_items=ev)
                table_key = f"{table_schema.upper()}.{table_name.upper()}"
                table_id, reason = _resolve(declarations, "db2-ddl", table_key)
                if table_id:
                    graph.add_edge(index_id, "INDEXES", table_id, evidence_items=ev)
                else:
                    unresolved.append({"kind": "db2-index-target", "name": table_key, "path": relative, "line": _line(text, match.start()), "reason": reason})
                declared_by_kind["db2_index"] += 1
        elif kind == "jcl":
            job = re.search(rf"^//({_PROGRAM_NAME})\s+JOB\b", text, re.I | re.M)
            proc = re.search(rf"^//({_PROGRAM_NAME})\s+PROC\b", text, re.I | re.M)
            declaration = job or proc
            if declaration:
                name = declaration.group(1).upper()
                node_kind = "jcl_job" if job else "jcl_procedure"
                node_id = f"pilot:{node_kind.replace('_', '-')}:{name}:{_path_token(relative)}"
                ev = _ev(relative, _line(text, declaration.start()))
                graph.add_node(node_id, node_kind, name, properties={"path": relative}, evidence_items=ev)
                graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)
                declarations.setdefault((kind, name), []).append(node_id)
                declared_by_kind[node_kind] += 1
        elif kind == "hlasm":
            parsed = [
                (line_number, parts)
                for line_number, line in enumerate(text.splitlines(), 1)
                if (parts := _hlasm_parts(line))
            ]
            entry = next(
                (
                    (line_number, label, operation)
                    for line_number, (label, operation, _) in parsed
                    if label and operation in {"CSECT", "START"}
                ),
                (1, Path(relative).stem.upper(), "UNKNOWN"),
            )
            entry_line, name, directive = entry
            program_id = f"pilot:assembler-program:{name}:{_path_token(relative)}"
            ev = _ev(relative, entry_line)
            graph.add_node(
                program_id,
                "assembler_program",
                name,
                properties={"path": relative, "language": "HLASM", "entry_directive": directive},
                evidence_items=ev,
            )
            graph.add_edge(file_id, "DECLARES", program_id, evidence_items=ev)
            declarations.setdefault((kind, name), []).append(program_id)
            declared_by_kind["assembler_program"] += 1

            symbols: dict[str, str] = {}
            instructions: list[tuple[int, str, str, str]] = []
            for sequence, (line_number, (label, operation, operands)) in enumerate(parsed, 1):
                line_ev = _ev(relative, line_number)
                if operation == "DSECT" and label:
                    dsect_id = f"pilot:assembler-dsect:{label}:{_path_token(relative)}"
                    graph.add_node(dsect_id, "assembler_dsect", label, properties={"path": relative}, evidence_items=line_ev)
                    graph.add_edge(file_id, "DECLARES", dsect_id, evidence_items=line_ev)
                    declarations.setdefault(("assembler-dsect", label), []).append(dsect_id)
                    declared_by_kind["assembler_dsect"] += 1
                if label and operation not in {"CSECT", "START", "DSECT"}:
                    symbol_id = f"pilot:assembler-symbol:{name}:{label}:{_path_token(relative)}"
                    symbols[label] = symbol_id
                    graph.add_node(symbol_id, "assembler_symbol", label, properties={"operation": operation, "program": name}, evidence_items=line_ev)
                    graph.add_edge(program_id, "CONTAINS", symbol_id, evidence_items=line_ev)
                    declared_by_kind["assembler_symbol"] += 1
                if operation and operation not in _HLASM_DIRECTIVES:
                    instruction_id = f"pilot:assembler-instruction:{name}:{line_number}:{sequence}:{_path_token(relative)}"
                    graph.add_node(instruction_id, "assembler_instruction", operation, properties={"operands": operands, "program": name}, evidence_items=line_ev)
                    graph.add_edge(program_id, "CONTAINS", instruction_id, evidence_items=line_ev)
                    instructions.append((line_number, operation, operands, instruction_id))
                    declared_by_kind["assembler_instruction"] += 1
            for line_number, operation, operands, instruction_id in instructions:
                if operation not in _HLASM_BRANCHES or not operands:
                    continue
                target_name = operands.split(",")[-1].split()[0].strip().upper()
                target_id = symbols.get(target_name)
                if target_id:
                    graph.add_edge(instruction_id, "BRANCHES_TO", target_id, evidence_items=_ev(relative, line_number))
                elif re.fullmatch(r"[A-Z$#@][A-Z0-9$#@]*", target_name):
                    unresolved.append({"kind": "hlasm-branch", "name": target_name, "path": relative, "line": line_number, "reason": "target-not-in-intake"})
        elif kind == "ims":
            dbd_statements = _ims_statements(text, {"DBD", "DATASET", "SEGM", "FIELD"})
            dbd = next((item for item in dbd_statements if item[2] == "DBD"), None)
            if dbd:
                line_number, _, _, operands = dbd
                attrs = _ims_attrs(operands)
                dbd_name = attrs.get("NAME", Path(relative).stem).strip("()").upper()
                dbd_id = f"pilot:ims-database:{dbd_name}:{_path_token(relative)}"
                ev = _ev(relative, line_number)
                graph.add_node(dbd_id, "ims_database", dbd_name, properties={"path": relative, **attrs}, evidence_items=ev)
                graph.add_edge(file_id, "DECLARES", dbd_id, evidence_items=ev)
                declarations.setdefault(("ims-database", dbd_name), []).append(dbd_id)
                declared_by_kind["ims_database"] += 1
                current_segment: str | None = None
                segments: dict[str, str] = {}
                for statement_line, label, operation, statement_operands in dbd_statements:
                    statement_attrs = _ims_attrs(statement_operands)
                    statement_ev = _ev(relative, statement_line)
                    if operation == "DATASET":
                        group_name = (label or f"GROUP-{statement_line}").upper()
                        group_id = f"pilot:ims-dataset-group:{dbd_name}:{group_name}:{_path_token(relative)}"
                        graph.add_node(group_id, "ims_dataset_group", group_name, properties=statement_attrs, evidence_items=statement_ev)
                        graph.add_edge(dbd_id, "HAS_DATASET_GROUP", group_id, evidence_items=statement_ev)
                        declared_by_kind["ims_dataset_group"] += 1
                    elif operation == "SEGM":
                        segment_name = statement_attrs.get("NAME", label).strip("()").upper()
                        current_segment = f"pilot:ims-segment:{dbd_name}:{segment_name}:{_path_token(relative)}"
                        segments[segment_name] = current_segment
                        graph.add_node(current_segment, "ims_segment", segment_name, properties={"database": dbd_name, **statement_attrs}, evidence_items=statement_ev)
                        graph.add_edge(dbd_id, "CONTAINS", current_segment, evidence_items=statement_ev)
                        parent_name = statement_attrs.get("PARENT", "").strip("()").split(",")[0].upper()
                        if parent_name and parent_name != "0":
                            parent_id = segments.get(parent_name)
                            if parent_id:
                                graph.add_edge(parent_id, "PARENT_OF", current_segment, evidence_items=statement_ev)
                            else:
                                unresolved.append({"kind": "ims-parent-segment", "name": parent_name, "path": relative, "line": statement_line, "reason": "target-not-in-intake"})
                        declared_by_kind["ims_segment"] += 1
                    elif operation == "FIELD" and current_segment:
                        field_name = statement_attrs.get("NAME", label).strip("()").split(",")[0].upper()
                        field_id = f"pilot:ims-field:{dbd_name}:{field_name}:{_path_token(relative)}"
                        graph.add_node(field_id, "ims_field", field_name, properties={"database": dbd_name, **statement_attrs}, evidence_items=statement_ev)
                        graph.add_edge(current_segment, "HAS_FIELD", field_id, evidence_items=statement_ev)
                        declared_by_kind["ims_field"] += 1

            psb_statements = _ims_statements(text, {"PCB", "SENSEG", "PSBGEN"})
            psb = next((item for item in psb_statements if item[2] == "PSBGEN"), None)
            if psb:
                line_number, _, _, operands = psb
                attrs = _ims_attrs(operands)
                psb_name = attrs.get("PSBNAME", Path(relative).stem).strip("()").upper()
                psb_id = f"pilot:ims-psb:{psb_name}:{_path_token(relative)}"
                ev = _ev(relative, line_number)
                graph.add_node(psb_id, "ims_psb", psb_name, properties={"path": relative, **attrs}, evidence_items=ev)
                graph.add_edge(file_id, "DECLARES", psb_id, evidence_items=ev)
                declarations.setdefault(("ims-psb", psb_name), []).append(psb_id)
                declared_by_kind["ims_psb"] += 1
                current_pcb: str | None = None
                current_database = ""
                for statement_line, label, operation, statement_operands in psb_statements:
                    statement_attrs = _ims_attrs(statement_operands)
                    statement_ev = _ev(relative, statement_line)
                    if operation == "PCB":
                        pcb_name = (label or f"PCB-{statement_line}").upper()
                        current_database = statement_attrs.get("DBDNAME", "").strip("()").upper()
                        current_pcb = f"pilot:ims-pcb:{psb_name}:{pcb_name}:{_path_token(relative)}"
                        graph.add_node(current_pcb, "ims_pcb", pcb_name, properties=statement_attrs, evidence_items=statement_ev)
                        graph.add_edge(psb_id, "CONTAINS", current_pcb, evidence_items=statement_ev)
                        target, reason = _resolve(declarations, "ims-database", current_database)
                        if target:
                            graph.add_edge(current_pcb, "USES_DBD", target, evidence_items=statement_ev)
                        else:
                            unresolved.append({"kind": "ims-database", "name": current_database, "path": relative, "line": statement_line, "reason": reason})
                        declared_by_kind["ims_pcb"] += 1
                    elif operation == "SENSEG" and current_pcb and current_database:
                        segment_name = statement_attrs.get("NAME", label).strip("()").upper()
                        matches = [node for node in graph.nodes.values() if node["kind"] == "ims_segment" and node["name"] == segment_name and node["properties"].get("database") == current_database]
                        if len(matches) == 1:
                            graph.add_edge(current_pcb, "SENSITIVE_TO", matches[0]["id"], evidence_items=statement_ev)
                        else:
                            unresolved.append({"kind": "ims-segment", "name": f"{current_database}.{segment_name}", "path": relative, "line": statement_line, "reason": "ambiguous" if matches else "target-not-in-intake"})
        elif kind == "vsam":
            for line_start, line_end, definition, block in _idcams_blocks(text):
                names = re.findall(r"\bNAME\s*\(\s*([A-Z0-9.$#@-]+)\s*\)", block, re.I)
                if not names:
                    unresolved.append({"kind": "vsam-definition", "name": definition, "path": relative, "line": line_start, "reason": "name-missing"})
                    continue
                name = names[0].upper()
                ev = _ev(relative, line_start, line_end)
                if definition == "CLUSTER":
                    node_kind, id_kind = "vsam_cluster", "vsam-cluster"
                    properties = {"organization": "KSDS" if re.search(r"\bINDEXED\b", block, re.I) else "ESDS" if re.search(r"\bNONINDEXED\b", block, re.I) else "UNKNOWN"}
                elif definition == "ALTERNATEINDEX":
                    node_kind, id_kind, properties = "vsam_alternate_index", "vsam-alternate-index", {}
                else:
                    node_kind, id_kind, properties = "vsam_path", "vsam-path", {}
                node_id = f"pilot:{id_kind}:{name}:{_path_token(relative)}"
                graph.add_node(node_id, node_kind, name, properties=properties, evidence_items=ev)
                graph.add_edge(file_id, "DECLARES", node_id, evidence_items=ev)
                declarations.setdefault((id_kind, name), []).append(node_id)
                declared_by_kind[node_kind] += 1
                if definition == "CLUSTER":
                    for component_name in (value.upper() for value in names[1:]):
                        component_id = f"pilot:vsam-component:{component_name}:{_path_token(relative)}"
                        graph.add_node(component_id, "vsam_component", component_name, properties={"component_type": "INDEX" if component_name.endswith(".INDEX") else "DATA"}, evidence_items=ev)
                        graph.add_edge(node_id, "HAS_COMPONENT", component_id, evidence_items=ev)
                        declared_by_kind["vsam_component"] += 1
                elif definition == "ALTERNATEINDEX":
                    relate = re.search(r"\bRELATE\s*\(\s*([A-Z0-9.$#@-]+)\s*\)", block, re.I)
                    if relate:
                        target_name = relate.group(1).upper()
                        target, reason = _resolve(declarations, "vsam-cluster", target_name)
                        if target:
                            graph.add_edge(node_id, "TARGETS", target, evidence_items=ev)
                        else:
                            unresolved.append({"kind": "vsam-cluster", "name": target_name, "path": relative, "line": line_start, "reason": reason})
                else:
                    entry = re.search(r"\bPATHENTRY\s*\(\s*([A-Z0-9.$#@-]+)\s*\)", block, re.I)
                    if entry:
                        target_name = entry.group(1).upper()
                        target, reason = _resolve(declarations, "vsam-alternate-index", target_name)
                        if target:
                            graph.add_edge(node_id, "TARGETS", target, evidence_items=ev)
                        else:
                            unresolved.append({"kind": "vsam-alternate-index", "name": target_name, "path": relative, "line": line_start, "reason": reason})

    # Second pass: cross-file calls, scheduling, SQL, and configuration lineage.
    for item in files:
        relative = str(item["path"])
        kind = str(item["kind"])
        text = texts[relative]
        file_id = file_nodes[relative]
        owner: str | None = None
        owner_kind: str | None = None
        if kind in {"cobol", "pli"}:
            name_match = re.search(rf"\bPROGRAM-ID\.\s+({_PROGRAM_NAME})", text, re.I) if kind == "cobol" else re.search(rf"^\s*({_PROGRAM_NAME})\s*:\s*PROC\b", text, re.I | re.M)
            if name_match:
                owner, _ = _resolve(declarations, kind, name_match.group(1).upper().rstrip("."))
                owner_kind = kind
        if owner and owner_kind == "cobol":
            for match in re.finditer(rf"\bCOPY\s+({_PROGRAM_NAME})", text, re.I):
                name = match.group(1).upper().rstrip(".")
                target, reason = _resolve(declarations, "copybook", name)
                if target:
                    graph.add_edge(owner, "USES_COPYBOOK", target, evidence_items=_ev(relative, _line(text, match.start())))
                else:
                    unresolved.append({"kind": "copybook", "name": name, "path": relative, "line": _line(text, match.start()), "reason": reason})
        if owner:
            call_pattern = r"\bCALL\s+['\"](" + _PROGRAM_NAME + r")[\"']" if owner_kind == "cobol" else r"\bCALL\s+(" + _PROGRAM_NAME + r")\s*\("
            for match in re.finditer(call_pattern, text, re.I):
                name = match.group(1).upper()
                candidates = [
                    (candidate_kind, declarations.get((candidate_kind, name), []))
                    for candidate_kind in ("cobol", "pli")
                ]
                matches = [(candidate_kind, node) for candidate_kind, nodes in candidates for node in nodes]
                if len(matches) == 1:
                    graph.add_edge(owner, "CALLS", matches[0][1], evidence_items=_ev(relative, _line(text, match.start())))
                else:
                    unresolved.append({"kind": "program-call", "name": name, "path": relative, "line": _line(text, match.start()), "reason": "ambiguous" if matches else "target-not-in-intake"})
            for occurrence, (line_start, line_end, body) in enumerate(_sql_blocks(text), 1):
                parsed = _sql_table(body)
                if not parsed:
                    unresolved.append({"kind": "embedded-sql", "name": "unparsed", "path": relative, "line": line_start, "reason": "unsupported-sql-shape"})
                    continue
                operation, schema, table = parsed
                qualified = f"{schema}.{table}"
                statement_id = f"pilot:db2-sql:{_path_token(relative)}:{line_start}:{occurrence}"
                ev = _ev(relative, line_start, line_end)
                graph.add_node(
                    statement_id,
                    "db2_sql_statement",
                    f"{operation} {qualified}",
                    properties={"operation": operation, "table": qualified},
                    evidence_items=ev,
                )
                graph.add_edge(owner, "ISSUES_SQL", statement_id, evidence_items=ev)
                table_id, reason = _resolve(declarations, "db2-ddl", qualified)
                if table_id is None:
                    table_id = f"pilot:db2-table-reference:{qualified}"
                    graph.add_node(table_id, "db2_table", qualified, properties={"schema": schema, "table": table, "definition_present": False})
                    unresolved.append({"kind": "db2-table-definition", "name": qualified, "path": relative, "line": line_start, "reason": reason})
                graph.add_edge(statement_id, "READS_TABLE" if operation == "SELECT" else "WRITES_TABLE", table_id, evidence_items=ev)
                declared_by_kind["db2_sql_statement"] += 1
        elif kind == "jcl":
            container_match = re.search(rf"^//({_PROGRAM_NAME})\s+(?:JOB|PROC)\b", text, re.I | re.M)
            container = None
            if container_match:
                container, _ = _resolve(declarations, "jcl", container_match.group(1).upper())
            if container:
                for match in re.finditer(rf"^//({_PROGRAM_NAME})\s+EXEC\s+(?:PGM=)?({_PROGRAM_NAME})", text, re.I | re.M):
                    step_name, program_name = (value.upper() for value in match.groups())
                    step_id = f"pilot:jcl-step:{container_match.group(1).upper()}:{step_name}:{_path_token(relative)}"
                    ev = _ev(relative, _line(text, match.start()))
                    graph.add_node(step_id, "jcl_step", step_name, properties={"program": program_name}, evidence_items=ev)
                    graph.add_edge(container, "CONTAINS", step_id, evidence_items=ev)
                    program_matches = [node for language in ("cobol", "pli", "hlasm") for node in declarations.get((language, program_name), [])]
                    if len(program_matches) == 1:
                        graph.add_edge(step_id, "EXECUTES", program_matches[0], evidence_items=ev)
                    elif len(program_matches) > 1:
                        unresolved.append({"kind": "jcl-exec", "name": program_name, "path": relative, "line": _line(text, match.start()), "reason": "ambiguous"})
                    else:
                        executable_id = f"pilot:external-executable:{program_name}"
                        graph.add_node(executable_id, "executable", program_name, properties={"definition_present": False})
                        graph.add_edge(step_id, "EXECUTES", executable_id, evidence_items=ev)
                        unresolved.append({"kind": "jcl-exec", "name": program_name, "path": relative, "line": _line(text, match.start()), "reason": "target-not-in-intake"})
                    declared_by_kind["jcl_step"] += 1
        elif kind == "system-configuration" and Path(relative).suffix.lower() == ".json":
            try:
                configuration = json.loads(text)
            except json.JSONDecodeError:
                configuration = None
            transactions = configuration.get("transactions") if isinstance(configuration, dict) else None
            if isinstance(transactions, list):
                for index, transaction in enumerate(transactions, 1):
                    if not isinstance(transaction, dict):
                        continue
                    transaction_name = str(transaction.get("transaction", "")).upper()
                    program_name = str(transaction.get("program", "")).upper()
                    if not transaction_name or not program_name:
                        continue
                    transaction_id = f"pilot:cics-transaction:{transaction_name}:{_path_token(relative)}"
                    resource_id = f"pilot:cics-program-resource:{program_name}:{_path_token(relative)}"
                    ev = _ev(relative, 1, max(1, len(text.splitlines())))
                    graph.add_node(transaction_id, "cics_transaction", transaction_name, properties={"enabled": bool(transaction.get("enabled", False))}, evidence_items=ev)
                    graph.add_node(resource_id, "cics_program_resource", program_name, properties={"configured_program": program_name}, evidence_items=ev)
                    graph.add_edge(file_id, "DECLARES", transaction_id, evidence_items=ev)
                    graph.add_edge(file_id, "DECLARES", resource_id, evidence_items=ev)
                    graph.add_edge(transaction_id, "STARTS_PROGRAM", resource_id, evidence_items=ev)
                    program_matches = [node for language in ("cobol", "pli") for node in declarations.get((language, program_name), [])]
                    if len(program_matches) == 1:
                        graph.add_edge(resource_id, "RESOLVES_TO", program_matches[0], evidence_items=ev)
                    else:
                        unresolved.append({"kind": "cics-program", "name": program_name, "path": relative, "line": 1, "reason": "ambiguous" if program_matches else "target-not-in-intake"})
                    declared_by_kind["cics_transaction"] += 1
                    declared_by_kind["cics_program_resource"] += 1

    graph_payload = graph.to_dict()
    graph_errors = validate_graph(graph_payload, ontology)
    analysis_policy = profile.get("analysis")
    if not isinstance(analysis_policy, dict):
        raise AnalysisError("pilot-analysis-policy-missing")
    if hashlib.sha256(ontology_path.read_bytes()).hexdigest() != analysis_policy.get(
        "relationship_ontology_sha256"
    ):
        raise AnalysisError("pilot-analysis-ontology-release-drift")
    max_nodes = int(analysis_policy.get("max_nodes", 0))
    max_edges = int(analysis_policy.get("max_edges", 0))
    limits_respected = 0 < graph_payload["statistics"]["node_count"] <= max_nodes and 0 <= graph_payload["statistics"]["edge_count"] <= max_edges
    by_kind = Counter(str(item.get("kind", "")) for item in files)
    coverage = [
        {
            "file_kind": kind,
            "files": by_kind[kind],
            "typed_files": typed_files[kind],
            "analysis_mode": {
                "cobol": "bounded-static",
                "copybook": "typed-declaration",
                "pli": "bounded-static",
                "jcl": "bounded-static",
                "db2-ddl": "bounded-static",
                "system-configuration": "typed-json-or-inventory",
                "hlasm": "bounded-static",
                "ims": "bounded-static",
                "vsam": "bounded-static",
            }[kind],
        }
        for kind in sorted(by_kind)
    ]
    quality_gates = {
        "intake_identity_bound": bool(_SHA256.fullmatch(str(intake.get("content_sha256", "")))),
        "all_source_bytes_reverified": len(texts) == len(files),
        "every_intake_file_typed": sum(typed_files.values()) == len(files),
        "relationship_ontology_bound": graph_payload.get("relationship_ontology") == ontology_identity(ontology),
        "graph_integrity_valid": not graph_errors,
        "analysis_limits_respected": limits_respected,
        "no_live_system_contact": True,
        "raw_source_not_embedded": True,
        "behavior_and_equivalence_not_claimed": True,
    }
    unresolved = sorted(unresolved, key=lambda item: (item["path"], item["line"], item["kind"], item["name"]))
    receipt: dict[str, Any] = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_type": ANALYSIS_TYPE,
        "pilot_id": str(profile.get("pilot_id", "")),
        "intake_sha256": str(intake.get("content_sha256", "")),
        "source_tree_sha256": str(intake.get("source_tree_sha256", "")),
        "graph_id": graph_payload["graph_id"],
        "graph_schema_version": graph_payload["schema_version"],
        "graph_content_sha256": graph_payload["content_sha256"],
        "relationship_ontology": graph_payload["relationship_ontology"],
        "statistics": graph_payload["statistics"],
        "coverage": coverage,
        "declared_entities_by_kind": dict(sorted(declared_by_kind.items())),
        "unresolved_references": unresolved,
        "unresolved_reference_count": len(unresolved),
        "quality_gates": quality_gates,
        "analysis_ready": all(quality_gates.values()),
        "analysis_scope": "bounded-source-static-analysis",
        "behavior_proven": False,
        "live_system_contact": False,
        "mainframe_equivalent": False,
        "production_ready": False,
        "limitations": [
            "Static source analysis does not prove compilation, runtime behavior, or production equivalence.",
            "Unresolved and ambiguous references remain visible and require customer context or live evidence.",
            "Configuration formats without a bounded semantic parser remain inventory-only.",
            "HLASM macro expansion, IMS runtime access, and live VSAM catalog state are not observed by this bounded source parser.",
        ],
    }
    receipt["content_sha256"] = _canonical_hash(receipt)
    if graph_errors:
        raise AnalysisError(f"analysis-graph-invalid:{graph_errors[0]}")
    if not receipt["analysis_ready"]:
        raise AnalysisError("analysis-quality-gate-failed")
    return graph_payload, receipt


def validate_source_analysis(
    graph_payload: Mapping[str, Any],
    receipt: Mapping[str, Any],
    intake: Mapping[str, Any],
    profile: Mapping[str, Any],
    ontology_path: Path,
) -> list[str]:
    errors: list[str] = []
    ontology = load_ontology(ontology_path)
    graph = dict(graph_payload)
    if receipt.get("schema_version") != ANALYSIS_SCHEMA_VERSION or receipt.get("analysis_type") != ANALYSIS_TYPE:
        errors.append("analysis-contract-identity-invalid")
    if receipt.get("pilot_id") != profile.get("pilot_id") or receipt.get("intake_sha256") != intake.get("content_sha256") or receipt.get("source_tree_sha256") != intake.get("source_tree_sha256"):
        errors.append("analysis-input-binding-invalid")
    if receipt.get("content_sha256") != _canonical_hash(receipt):
        errors.append("analysis-content-hash-invalid")
    if graph.get("content_sha256") != graph_hash(graph) or receipt.get("graph_content_sha256") != graph.get("content_sha256") or receipt.get("graph_id") != graph.get("graph_id"):
        errors.append("analysis-graph-binding-invalid")
    graph_errors = validate_graph(graph, ontology)
    if graph_errors:
        errors.append(f"analysis-graph-invalid:{graph_errors[0]}")
    if receipt.get("relationship_ontology") != ontology_identity(ontology):
        errors.append("analysis-ontology-binding-invalid")
    if receipt.get("statistics") != graph.get("statistics"):
        errors.append("analysis-statistics-stale")
    gates = receipt.get("quality_gates")
    if not isinstance(gates, dict) or not gates or not all(value is True for value in gates.values()):
        errors.append("analysis-quality-gates-invalid")
    if receipt.get("analysis_ready") is not True:
        errors.append("analysis-readiness-invalid")
    if receipt.get("behavior_proven") is not False or receipt.get("live_system_contact") is not False or receipt.get("mainframe_equivalent") is not False or receipt.get("production_ready") is not False:
        errors.append("analysis-overclaims-source-only-evidence")
    return sorted(set(errors))


def write_analysis_graph(payload: Mapping[str, Any], path: Path) -> None:
    import gzip
    import io

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.suffix != ".gz":
        path.write_bytes(serialized)
        return
    compressed = io.BytesIO()
    with gzip.GzipFile(
        filename="",
        mode="wb",
        fileobj=compressed,
        compresslevel=9,
        mtime=0,
    ) as handle:
        handle.write(serialized)
    path.write_bytes(compressed.getvalue())
