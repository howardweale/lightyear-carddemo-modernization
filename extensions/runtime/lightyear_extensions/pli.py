from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import source_hashes

from .contracts import ExtensionContractError, canonical_hash


PACK_ID = "lightyear.pli"
PACK_VERSION = "1.1"
SOURCE_ID = "source:lightyear-carddemo"
_EXTENSIONS = {".pli", ".pl1", ".inc"}
_RELATIONS = {
    "CALLS",
    "CONTAINS",
    "DECLARES",
    "ISSUES_SQL",
    "READS",
    "READS_TABLE",
    "USES_INCLUDE",
    "WRITES",
    "WRITES_TABLE",
}


def build_pli_fragment(
    base_graph: Mapping[str, Any], source_root: Path, repository_root: Path
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    source_root = source_root.resolve()
    if repository_root not in source_root.parents and source_root != repository_root:
        raise ExtensionContractError("PL/I source root must be inside the repository root")
    builder = _FragmentBuilder(base_graph, repository_root)
    paths = sorted(
        path for path in source_root.rglob("*")
        if path.is_file() and path.suffix.casefold() in _EXTENSIONS
    )
    if not paths:
        raise ExtensionContractError("PL/I language pack requires at least one source file")
    for path in paths:
        builder.extract(path)
    return builder.fragment(source_root.relative_to(repository_root).as_posix())


def validate_pli_fragment(
    fragment: Mapping[str, Any], base_graph: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    if fragment.get("schema_version") != "1.0":
        errors.append("unsupported PL/I fragment schema_version")
    if fragment.get("fragment_type") != "lightyear-graph-extension":
        errors.append("PL/I fragment_type is invalid")
    pack = fragment.get("language_pack", {})
    if pack.get("id") != PACK_ID or pack.get("version") != PACK_VERSION:
        errors.append("PL/I language pack identity is invalid")
    binding = fragment.get("base_graph", {})
    if binding.get("graph_id") != base_graph.get("graph_id"):
        errors.append("PL/I fragment targets a different graph_id")
    if binding.get("content_sha256") != base_graph.get("content_sha256"):
        errors.append("PL/I fragment targets a different graph content identity")
    if fragment.get("content_sha256") != canonical_hash(fragment, {"content_sha256"}):
        errors.append("PL/I fragment content_sha256 is invalid")

    nodes = fragment.get("nodes", [])
    edges = fragment.get("edges", [])
    node_ids = [item.get("id") for item in nodes]
    if len(node_ids) != len(set(node_ids)):
        errors.append("PL/I fragment contains duplicate node ids")
    edge_ids = [item.get("id") for item in edges]
    if len(edge_ids) != len(set(edge_ids)):
        errors.append("PL/I fragment contains duplicate edge ids")
    local = set(node_ids)
    base_nodes = {item["id"] for item in base_graph.get("nodes", [])}
    external = {
        item.get("entity_id") for item in fragment.get("external_references", [])
        if item.get("entity_kind") == "node"
    }
    for entity_id in external:
        if entity_id not in base_nodes:
            errors.append(f"PL/I fragment external reference is absent from base graph: {entity_id}")
    for edge in edges:
        if edge.get("relation") not in _RELATIONS:
            errors.append(f"PL/I fragment uses unsupported relation: {edge.get('relation')}")
        for endpoint in (edge.get("source"), edge.get("target")):
            if endpoint not in local and endpoint not in external:
                errors.append(f"PL/I fragment edge has undeclared endpoint: {endpoint}")
    stats = fragment.get("statistics", {})
    if stats.get("node_count") != len(nodes) or stats.get("edge_count") != len(edges):
        errors.append("PL/I fragment statistics are stale")
    return errors


class _FragmentBuilder:
    def __init__(self, base_graph: Mapping[str, Any], repository_root: Path) -> None:
        self.base_graph = base_graph
        self.repository_root = repository_root
        self.base_nodes = {item["id"] for item in base_graph["nodes"]}
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.external: set[str] = set()

    def extract(self, path: Path) -> None:
        relative = path.relative_to(self.repository_root).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines() or [""]
        logical_sha, transport_sha = source_hashes(path)
        file_id = f"extension:source-file:{relative}"
        self._node(file_id, "source_file", path.name, {
            "path": relative,
            "language": "PL/I" if path.suffix.casefold() != ".inc" else "PL/I include",
            "content_sha256": logical_sha,
            "transport_content_sha256": transport_sha,
            "hash_basis": "normalized-lf",
            "reference_fixture": True,
        }, self._evidence(relative, 1, len(lines)))
        if path.suffix.casefold() == ".inc":
            include_name = path.stem.upper()
            include_id = f"extension:pli-include:{include_name}"
            self._node(include_id, "pli_include", include_name, {"path": relative}, self._evidence(relative, 1, len(lines)))
            self._edge(file_id, "DECLARES", include_id, self._evidence(relative, 1))
            return
        self._extract_program(file_id, relative, lines)

    def _extract_program(self, file_id: str, relative: str, lines: list[str]) -> None:
        text = "\n".join(lines)
        main = re.search(
            r"(?im)^\s*([A-Z][A-Z0-9_$#@-]*)\s*:\s*PROC(?:EDURE)?\b[^;]*OPTIONS\s*\(\s*MAIN\s*\)",
            text,
        )
        if not main:
            raise ExtensionContractError(f"PL/I source has no OPTIONS(MAIN) procedure: {relative}")
        program = main.group(1).upper()
        program_id = f"extension:pli-program:{program}"
        main_line = text[: main.start()].count("\n") + 1
        self._node(program_id, "pli_program", program, {
            "path": relative,
            "language": "PL/I",
            "reference_fixture": True,
        }, self._evidence(relative, main_line))
        self._edge(file_id, "DECLARES", program_id, self._evidence(relative, main_line))

        procedures: dict[str, tuple[str, int]] = {}
        procedure_pattern = re.compile(
            r"(?im)^\s*([A-Z][A-Z0-9_$#@-]*)\s*:\s*PROC(?:EDURE)?\b"
        )
        for match in procedure_pattern.finditer(text):
            name = match.group(1).upper()
            if name == program:
                continue
            line = text[: match.start()].count("\n") + 1
            procedure_id = f"extension:pli-procedure:{program}:{name}"
            procedures[name] = (procedure_id, line)
            self._node(procedure_id, "pli_procedure", name, {
                "program": program,
                "path": relative,
            }, self._evidence(relative, line))
            self._edge(program_id, "CONTAINS", procedure_id, self._evidence(relative, line))

        scopes = [(main_line, program_id), *[(line, value[0]) for _, value in procedures.items() for line in [value[1]]]]
        scopes.sort()
        for line_number, line in enumerate(lines, 1):
            scope = next((scope_id for start, scope_id in reversed(scopes) if start <= line_number), program_id)
            include = re.search(r"%INCLUDE\s+([A-Z][A-Z0-9_$#@-]*)", line, re.I)
            if include:
                name = include.group(1).upper()
                include_id = f"extension:pli-include:{name}"
                self._node(include_id, "pli_include", name, {})
                self._edge(program_id, "USES_INCLUDE", include_id, self._evidence(relative, line_number))
            for called in re.findall(r"\bCALL\s+([A-Z][A-Z0-9_$#@-]*)", line, re.I):
                called = called.upper()
                if called in procedures:
                    target = procedures[called][0]
                else:
                    target = self._external_program(called)
                self._edge(scope, "CALLS", target, self._evidence(relative, line_number))
            for verb, relation in (("READ", "READS"), ("WRITE", "WRITES")):
                match = re.search(rf"\b{verb}\s+FILE\s*\(\s*([A-Z][A-Z0-9_$#@-]*)\s*\)", line, re.I)
                if match:
                    name = match.group(1).upper()
                    handle = f"extension:pli-file:{program}:{name}"
                    self._node(handle, "pli_file_handle", name, {"program": program})
                    self._edge(scope, relation, handle, self._evidence(relative, line_number))

        for occurrence, match in enumerate(
            re.finditer(r"EXEC\s+SQL\s+(.*?);", text, re.I | re.S), start=1
        ):
            body = re.sub(r"\s+", " ", match.group(1)).strip()
            operation_match = re.match(r"(SELECT|INSERT|UPDATE|DELETE)\b", body, re.I)
            table_match = re.search(
                r"(?:FROM|INTO|UPDATE)\s+(?:([A-Z0-9_]+)\.)?([A-Z0-9_]+)", body, re.I
            )
            if not operation_match or not table_match:
                continue
            operation = operation_match.group(1).upper()
            schema = (table_match.group(1) or "CARDDEMO").upper()
            table = table_match.group(2).upper()
            line_start = text[: match.start()].count("\n") + 1
            line_end = line_start + match.group(0).count("\n")
            scope = next((scope_id for start, scope_id in reversed(scopes) if start <= line_start), program_id)
            statement = f"extension:pli-sql:{program}:{line_start}:{occurrence}"
            self._node(statement, "db2_sql_statement", f"{operation} {schema}.{table}", {
                "language": "PL/I",
                "operation": operation,
                "normalized_sql": body,
                "program": program,
            }, self._evidence(relative, line_start, line_end))
            table_id = f"legacy:db2-table:{schema}.{table}"
            self._external_node(table_id)
            self._edge(scope, "ISSUES_SQL", statement, self._evidence(relative, line_start, line_end))
            relation = "READS_TABLE" if operation == "SELECT" else "WRITES_TABLE"
            self._edge(statement, relation, table_id, self._evidence(relative, line_start, line_end))

    def _external_program(self, name: str) -> str:
        candidates = (
            f"legacy:pli-program:{name}",
            f"legacy:cobol-program:{name}",
            f"legacy:assembler-program:{name}",
        )
        target = next((item for item in candidates if item in self.base_nodes), None)
        if target is None:
            raise ExtensionContractError(f"PL/I CALL target is not present in the base graph: {name}")
        self._external_node(target)
        return target

    def _external_node(self, node_id: str) -> None:
        if node_id not in self.base_nodes:
            raise ExtensionContractError(f"PL/I external reference is absent from base graph: {node_id}")
        self.external.add(node_id)

    def _node(
        self,
        node_id: str,
        kind: str,
        name: str,
        properties: dict[str, Any],
        evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        candidate = {
            "id": node_id,
            "kind": kind,
            "name": name,
            "properties": properties,
            "evidence": evidence or [],
        }
        existing = self.nodes.get(node_id)
        if existing is None:
            self.nodes[node_id] = candidate
        elif existing["kind"] != kind:
            raise ExtensionContractError(f"PL/I node kind conflict: {node_id}")
        else:
            existing["properties"].update(properties)
            for item in evidence or []:
                if item not in existing["evidence"]:
                    existing["evidence"].append(item)

    def _edge(
        self,
        source: str,
        relation: str,
        target: str,
        evidence: list[dict[str, Any]],
    ) -> None:
        identity = json.dumps([source, relation, target], separators=(",", ":"))
        edge_id = "fragment-edge:" + hashlib.sha256(identity.encode()).hexdigest()[:20]
        candidate = {
            "id": edge_id,
            "source": source,
            "relation": relation,
            "target": target,
            "properties": {},
            "evidence": evidence,
        }
        existing = self.edges.get(edge_id)
        if existing is None:
            self.edges[edge_id] = candidate
        else:
            for item in evidence:
                if item not in existing["evidence"]:
                    existing["evidence"].append(item)

    @staticmethod
    def _evidence(path: str, start: int, end: int | None = None) -> list[dict[str, Any]]:
        return [{
            "source_id": SOURCE_ID,
            "path": path,
            "line_start": start,
            "line_end": end if end is not None else start,
            "method": "pli-language-pack-v1",
            "confidence": "observed",
        }]

    def fragment(self, source_root: str) -> dict[str, Any]:
        nodes = sorted(self.nodes.values(), key=lambda item: item["id"])
        edges = sorted(self.edges.values(), key=lambda item: item["id"])
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "fragment_type": "lightyear-graph-extension",
            "fragment_id": "lightyear:pli-reference-v1",
            "base_graph": {
                "graph_id": self.base_graph["graph_id"],
                "schema_version": self.base_graph["schema_version"],
                "content_sha256": self.base_graph["content_sha256"],
            },
            "language_pack": {
                "id": PACK_ID,
                "version": PACK_VERSION,
                "language": "PL/I",
                "extensions": sorted(_EXTENSIONS),
            },
            "source": {
                "source_id": SOURCE_ID,
                "root": source_root,
                "kind": "reference-fixture",
            },
            "nodes": nodes,
            "edges": edges,
            "external_references": [
                {"entity_kind": "node", "entity_id": value}
                for value in sorted(self.external)
            ],
            "statistics": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "nodes_by_kind": dict(sorted(Counter(item["kind"] for item in nodes).items())),
                "edges_by_relation": dict(sorted(Counter(item["relation"] for item in edges).items())),
                "external_reference_count": len(self.external),
            },
            "limitations": [
                "The bundled PL/I source is a reference fixture, not customer production source.",
                "Static PL/I extraction does not prove runtime behavior or compilation equivalence.",
                "The fragment is bound to one exact base graph identity and fails closed after graph drift.",
            ],
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload


def fragment_receipt(fragment: Mapping[str, Any]) -> dict[str, Any]:
    receipt = {
        "schema_version": fragment["schema_version"],
        "receipt_type": "lightyear-graph-extension-build",
        "fragment_id": fragment["fragment_id"],
        "content_sha256": fragment["content_sha256"],
        "base_graph": fragment["base_graph"],
        "language_pack": fragment["language_pack"],
        "statistics": fragment["statistics"],
        "production_ready": False,
    }
    return receipt
