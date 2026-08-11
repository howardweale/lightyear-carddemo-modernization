from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .model import KnowledgeGraph, evidence


LEGACY_SOURCE_ID = "source:aws-carddemo"
MODERN_SOURCE_ID = "source:lightyear-carddemo"
LEGACY_EXTENSIONS = {
    ".asm", ".bms", ".cbl", ".cpy", ".csd", ".ctl", ".dbd", ".dcl", ".ddl",
    ".jcl", ".mac", ".prc", ".psb", ".txt",
}


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
    content_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return graph.add_node(
        f"{prefix}:file:{relative}",
        "source_file",
        path.name,
        properties={
            "path": relative,
            "language": language,
            "estate": prefix,
            "content_sha256": content_sha256,
        },
        evidence_items=[evidence(source_id, relative, 1, max(1, len(_lines(path))))],
    )


def extract_legacy(graph: KnowledgeGraph, root: Path) -> None:
    app_root = root / "app"
    for path in sorted(item for item in app_root.rglob("*") if item.is_file()):
        if path.suffix.lower() not in LEGACY_EXTENSIONS and path.suffix:
            continue
        suffix = path.suffix.lower()
        if suffix in {".cbl"}:
            _extract_cobol(graph, path, root)
        elif suffix in {".cpy"}:
            _extract_copybook(graph, path, root)
        elif suffix in {".jcl", ".prc"}:
            _extract_jcl(graph, path, root)
        else:
            _add_file_node(graph, "legacy", path, root, LEGACY_SOURCE_ID, suffix.lstrip(".") or "text")


def _extract_cobol(graph: KnowledgeGraph, path: Path, root: Path) -> None:
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
            program_id = f"legacy:cobol-program:{executable}"
            if program_id in graph.nodes:
                executable_id = program_id
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


def extract_modern(graph: KnowledgeGraph, root: Path) -> None:
    java_root = root / "candidate-java"
    for path in sorted(java_root.rglob("*.java")):
        _extract_java(graph, path, root)
    pom = java_root / "pom.xml"
    if pom.exists():
        _extract_maven(graph, pom, root)
    python_paths = {
        *root.joinpath("src").rglob("*.py"),
        *root.joinpath("tests").rglob("*.py"),
        *root.joinpath("factory").rglob("*.py"),
    }
    for path in sorted(python_paths):
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
