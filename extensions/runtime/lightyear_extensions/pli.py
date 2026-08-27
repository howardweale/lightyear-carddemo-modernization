from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import source_hashes

from .contracts import ExtensionContractError, canonical_hash
from .pli_frontend import parse_pli_source


PACK_ID = "lightyear.pli"
PACK_VERSION = "1.2"
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
    include_names = {path.stem.upper() for path in paths if path.suffix.casefold() == ".inc"}
    for path in paths:
        builder.extract(path, include_names)
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
    coverage = fragment.get("coverage", {})
    if coverage != {
        "frontend": "tokenized-statement-parser",
        "parser_version": PACK_VERSION,
        "blocker_count": 0,
    }:
        errors.append("PL/I fragment supported-subset coverage metadata is invalid")
    for entity in [*nodes, *edges]:
        for evidence in entity.get("evidence", []):
            if evidence.get("method") != "pli-supported-subset-v2":
                errors.append("PL/I fragment contains evidence from an unexpected parser method")
                break
    return errors


class _FragmentBuilder:
    def __init__(self, base_graph: Mapping[str, Any], repository_root: Path) -> None:
        self.base_graph = base_graph
        self.repository_root = repository_root
        self.base_nodes = {item["id"] for item in base_graph["nodes"]}
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.external: set[str] = set()

    def extract(self, path: Path, include_names: set[str]) -> None:
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
        parsed = parse_pli_source("\n".join(lines), relative, include_names=include_names)
        if parsed["status"] != "passed":
            first = parsed["diagnostics"][0]
            raise ExtensionContractError(
                f"PL/I supported-subset blocker at {relative}:{first.get('line', 1)}: "
                f"{first['code']}: {first['message']}"
            )
        if parsed["file_kind"] == "include":
            include_name = next(
                item["name"] for item in parsed["constructs"] if item["kind"] == "include_member"
            )
            include_id = f"extension:pli-include:{include_name}"
            self._node(include_id, "pli_include", include_name, {
                "path": relative,
                "parser": "pli-supported-subset-v2",
            }, self._evidence(relative, 1, len(lines)))
            self._edge(file_id, "DECLARES", include_id, self._evidence(relative, 1))
            return
        self._extract_program(file_id, relative, parsed)

    def _extract_program(self, file_id: str, relative: str, parsed: Mapping[str, Any]) -> None:
        program = str(parsed["program"])
        program_id = f"extension:pli-program:{program}"
        main_construct = next(item for item in parsed["constructs"] if item["kind"] == "program")
        main_line = int(main_construct["line"])
        self._node(program_id, "pli_program", program, {
            "path": relative,
            "language": "PL/I",
            "reference_fixture": True,
            "parser": "pli-supported-subset-v2",
        }, self._evidence(relative, main_line))
        self._edge(file_id, "DECLARES", program_id, self._evidence(relative, main_line))

        procedures: dict[str, tuple[str, int]] = {}
        for construct in parsed["constructs"]:
            if construct["kind"] != "procedure":
                continue
            name = str(construct["name"])
            line = int(construct["line"])
            procedure_id = f"extension:pli-procedure:{program}:{name}"
            procedures[name] = (procedure_id, line)
            self._node(procedure_id, "pli_procedure", name, {
                "program": program,
                "path": relative,
                "parser": "pli-supported-subset-v2",
            }, self._evidence(relative, line))
            self._edge(program_id, "CONTAINS", procedure_id, self._evidence(relative, line))

        for reference in parsed["references"]:
            line_number = int(reference["line"])
            scope_name = reference.get("scope")
            scope = procedures.get(str(scope_name), (program_id, main_line))[0]
            if reference["kind"] == "include":
                name = str(reference["target"])
                include_id = f"extension:pli-include:{name}"
                self._node(include_id, "pli_include", name, {})
                self._edge(program_id, "USES_INCLUDE", include_id, self._evidence(relative, line_number))
            elif reference["kind"] == "call":
                called = str(reference["target"])
                if called in procedures:
                    target = procedures[called][0]
                else:
                    target = self._external_program(called)
                self._edge(scope, "CALLS", target, self._evidence(relative, line_number))
            elif reference["kind"] in {"file_read", "file_write"}:
                name = str(reference["target"])
                handle = f"extension:pli-file:{program}:{name}"
                self._node(handle, "pli_file_handle", name, {"program": program})
                relation = "READS" if reference["kind"] == "file_read" else "WRITES"
                self._edge(scope, relation, handle, self._evidence(relative, line_number))

        sql_references = [item for item in parsed["references"] if item["kind"] == "sql"]
        for occurrence, reference in enumerate(sql_references, start=1):
            operation = str(reference["operation"])
            schema = str(reference["schema"])
            table = str(reference["target"])
            line_start = int(reference["line"])
            scope_name = reference.get("scope")
            scope = procedures.get(str(scope_name), (program_id, main_line))[0]
            statement = f"extension:pli-sql:{program}:{line_start}:{occurrence}"
            self._node(statement, "db2_sql_statement", f"{operation} {schema}.{table}", {
                "language": "PL/I",
                "operation": operation,
                "normalized_sql": reference["normalized_sql"],
                "program": program,
                "parser": "pli-supported-subset-v2",
            }, self._evidence(relative, line_start))
            table_id = f"legacy:db2-table:{schema}.{table}"
            self._external_node(table_id)
            self._edge(scope, "ISSUES_SQL", statement, self._evidence(relative, line_start))
            relation = "READS_TABLE" if operation == "SELECT" else "WRITES_TABLE"
            self._edge(statement, relation, table_id, self._evidence(relative, line_start))

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
            "method": "pli-supported-subset-v2",
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
            "coverage": {
                "frontend": "tokenized-statement-parser",
                "parser_version": PACK_VERSION,
                "blocker_count": 0,
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
