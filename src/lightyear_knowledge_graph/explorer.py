from __future__ import annotations

import json
import mimetypes
import queue
import threading
import webbrowser
from collections import defaultdict, deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .chat import ChatError, GraphChatService
from .evidence_pack import EvidenceStore, load_evidence_pack
from .model import load_graph
from .ontology import load_ontology
from .validation import rule_gaps
from lightyear_factory.memory import SemanticMemoryStore
from lightyear_factory.store import DurableStore, EvaluationStore, FactoryRunStore, PortfolioStore
from lightyear_runtime.engine import load_snapshot as load_runtime_snapshot
from lightyear_runtime.store import RuntimeEvidenceStore
from lightyear_audit.ledger import load_snapshot as load_audit_snapshot
from lightyear_audit.store import AuditStore
from lightyear_control_tower.operational import (
    OperationalControlTower,
    OperationalEventStore,
    OperationalMonitor,
    OperationalSource,
)


DEFAULT_PERSPECTIVES = [
    {
        "id": "intcalc-workload",
        "name": "INTCALC workload",
        "description": "Legacy entry point, modern candidate, rules, scenarios, and scheduler.",
        "root": "workload:carddemo-intcalc",
        "depth": 2,
    },
    {
        "id": "monthly-interest",
        "name": "Monthly-interest rule",
        "description": "Source evidence, implementation, and independent verification.",
        "root": "rule:intcalc:monthly-interest",
        "depth": 2,
    },
    {
        "id": "intcalc-job",
        "name": "INTCALC job lineage",
        "description": "JCL job, execution step, program, DD allocations, and datasets.",
        "root": "legacy:jcl-job:INTCALC",
        "depth": 3,
    },
    {
        "id": "account-copybook",
        "name": "Account data contract",
        "description": "Account copybook fields and the programs that depend on the layout.",
        "root": "legacy:copybook:CVACT01Y",
        "depth": 2,
    },
    {
        "id": "final-account-behavior",
        "name": "Final-account behavior",
        "description": "The discovered EOF behavior and its implementation and tests.",
        "root": "rule:intcalc:source-final-account",
        "depth": 2,
    },
    {
        "id": "authfrds-data-lineage",
        "name": "AUTHFRDS data lineage",
        "description": "Db2 table, columns, DCL, embedded SQL, business rules, and PostgreSQL proof.",
        "root": "workload:carddemo-db2-authfrds",
        "depth": 3,
    },
]


@dataclass(frozen=True)
class GraphSelection:
    root: str
    depth: int
    audience: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "depth": self.depth,
            "audience": self.audience,
            "truncated": self.truncated,
            "nodes": self.nodes,
            "edges": self.edges,
        }


class GraphExplorerIndex:
    """Read-optimized index for bounded, audience-aware visual exploration."""

    def __init__(
        self,
        payload: dict[str, Any],
        max_nodes: int = 300,
        ontology: dict[str, Any] | None = None,
        runtime_store: RuntimeEvidenceStore | None = None,
    ) -> None:
        self.payload = payload
        self.max_nodes = max_nodes
        self.ontology = ontology or load_ontology()
        self.relation_definitions = self.ontology["relations"]
        self.runtime_store = runtime_store
        self.node_by_id = {node["id"]: node for node in payload["nodes"]}
        self.edge_by_id = {edge["id"]: edge for edge in payload["edges"]}
        self.adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for edge in payload["edges"]:
            self.adjacency[edge["source"]].append((edge["id"], edge["target"]))
            self.adjacency[edge["target"]].append((edge["id"], edge["source"]))
        for values in self.adjacency.values():
            values.sort(key=lambda item: (self.edge_by_id[item[0]]["relation"], item[1]))

    @classmethod
    def from_path(cls, graph_path: Path, max_nodes: int = 300) -> "GraphExplorerIndex":
        return cls(load_graph(graph_path), max_nodes=max_nodes)

    def metadata(self) -> dict[str, Any]:
        return {
            "graph_id": self.payload["graph_id"],
            "schema_version": self.payload["schema_version"],
            "content_sha256": self.payload["content_sha256"],
            "statistics": self.payload["statistics"],
            "relationship_ontology": self.payload["relationship_ontology"],
            "perspectives": self.perspectives(),
        }

    def perspectives(self) -> list[dict[str, Any]]:
        return [item for item in DEFAULT_PERSPECTIVES if item["root"] in self.node_by_id]

    def search(
        self,
        query: str,
        kind: str = "",
        limit: int = 25,
        audience: str = "implementer",
    ) -> list[dict[str, Any]]:
        audience = self._audience(audience)
        normalized = query.strip().casefold()
        if not normalized:
            return []
        matches = []
        for node in self.node_by_id.values():
            if self._hidden(node, audience):
                continue
            if kind and node["kind"] != kind:
                continue
            haystack = " ".join(
                [node["id"], node["name"], str(node.get("properties", {}).get("statement", ""))]
            ).casefold()
            if normalized not in haystack:
                continue
            score = 0 if node["name"].casefold().startswith(normalized) else 1
            matches.append((score, node["kind"], node["name"], node))
        matches.sort(key=lambda item: (item[0], item[1], item[2], item[3]["id"]))
        return [self._summary(item[3]) for item in matches[: max(1, min(limit, 100))]]

    def node(self, node_id: str, audience: str = "implementer") -> dict[str, Any]:
        audience = self._audience(audience)
        node = self.node_by_id[node_id]
        if self._hidden(node, audience):
            raise KeyError(node_id)
        incoming = []
        outgoing = []
        for edge_id, _ in self.adjacency.get(node_id, []):
            edge = self.edge_by_id[edge_id]
            if self._edge_hidden(edge, audience):
                continue
            other_id = edge["source"] if edge["target"] == node_id else edge["target"]
            if self._hidden(self.node_by_id[other_id], audience):
                continue
            target = incoming if edge["target"] == node_id else outgoing
            target.append(
                {
                    "id": edge["id"],
                    "relation": edge["relation"],
                    "source": edge["source"],
                    "target": edge["target"],
                }
            )
        result = dict(node)
        result["incoming"] = sorted(incoming, key=lambda item: (item["relation"], item["source"]))
        result["outgoing"] = sorted(outgoing, key=lambda item: (item["relation"], item["target"]))
        result["runtime"] = self.runtime_projection("node", node_id)
        return result

    def edge(self, edge_id: str, audience: str = "implementer") -> dict[str, Any]:
        audience = self._audience(audience)
        edge = self.edge_by_id[edge_id]
        source = self.node_by_id[edge["source"]]
        target = self.node_by_id[edge["target"]]
        if (
            self._edge_hidden(edge, audience)
            or self._hidden(source, audience)
            or self._hidden(target, audience)
        ):
            raise KeyError(edge_id)
        result = dict(edge)
        result["source_node"] = self._summary(source)
        result["target_node"] = self._summary(target)
        result["definition"] = self.relation_definitions[edge["relation"]]
        result["runtime"] = self.runtime_projection("edge", edge_id)
        supporting_evidence = []
        seen_evidence: set[tuple[Any, ...]] = set()
        for owner_type, owner, role in (
            ("edge", edge, "relationship"),
            ("node", source, "source endpoint"),
            ("node", target, "target endpoint"),
        ):
            for evidence_index, item in enumerate(owner.get("evidence", [])):
                identity = (
                    item.get("source_id"), item.get("path"), item.get("line_start"),
                    item.get("line_end"), item.get("method"), item.get("confidence"),
                )
                if identity in seen_evidence:
                    continue
                seen_evidence.add(identity)
                supporting_evidence.append(
                    {
                        "evidence": item,
                        "evidence_index": evidence_index,
                        "owner_id": owner["id"],
                        "owner_type": owner_type,
                        "role": role,
                    }
                )
                if len(supporting_evidence) >= 24:
                    break
            if len(supporting_evidence) >= 24:
                break
        result["supporting_evidence"] = supporting_evidence
        return result

    def runtime_projection(self, entity_kind: str, entity_id: str) -> dict[str, Any]:
        if self.runtime_store is None:
            return {
                "state": "static_only",
                "confidence": 0.35,
                "evidence_classes": [],
                "observation_count": 0,
                "runs": [],
                "operations": [],
                "events": [],
            }
        return self.runtime_store.projection(entity_kind, entity_id)

    def decorate_runtime(self, entity_kind: str, item: dict[str, Any]) -> dict[str, Any]:
        result = dict(item)
        result["runtime"] = self.runtime_projection(entity_kind, item["id"])
        return result

    def neighborhood(
        self,
        node_id: str,
        depth: int = 2,
        audience: str = "implementer",
        limit: int | None = None,
    ) -> GraphSelection:
        if node_id not in self.node_by_id:
            raise KeyError(node_id)
        audience = self._audience(audience)
        if self._hidden(self.node_by_id[node_id], audience):
            raise KeyError(node_id)
        depth = max(0, min(depth, 5))
        node_limit = max(10, min(limit or self.max_nodes, 1000))
        seen = {node_id}
        selected_edges: set[str] = set()
        queue = deque([(node_id, 0)])
        truncated = False
        while queue:
            current, distance = queue.popleft()
            if distance >= depth:
                continue
            for edge_id, neighbor in self.adjacency.get(current, []):
                if self._edge_hidden(self.edge_by_id[edge_id], audience):
                    continue
                neighbor_node = self.node_by_id[neighbor]
                if self._hidden(neighbor_node, audience):
                    continue
                if neighbor not in seen and len(seen) >= node_limit:
                    truncated = True
                    continue
                selected_edges.add(edge_id)
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, distance + 1))
        nodes = [self.node_by_id[item] for item in sorted(seen)]
        edges = [
            self.edge_by_id[item]
            for item in sorted(selected_edges)
            if self.edge_by_id[item]["source"] in seen and self.edge_by_id[item]["target"] in seen
        ]
        return GraphSelection(node_id, depth, audience, nodes, edges, truncated)

    def trace(
        self,
        source: str,
        target: str,
        audience: str = "implementer",
    ) -> dict[str, Any] | None:
        audience = self._audience(audience)
        for node_id in (source, target):
            if node_id not in self.node_by_id or self._hidden(self.node_by_id[node_id], audience):
                raise KeyError(node_id)
        queue = deque([source])
        previous: dict[str, tuple[str, str]] = {}
        seen = {source}
        while queue:
            current = queue.popleft()
            if current == target:
                break
            for edge_id, neighbor in self.adjacency.get(current, []):
                if (
                    neighbor in seen
                    or self._edge_hidden(self.edge_by_id[edge_id], audience)
                    or self._hidden(self.node_by_id[neighbor], audience)
                ):
                    continue
                seen.add(neighbor)
                previous[neighbor] = (current, edge_id)
                queue.append(neighbor)
        if target not in seen:
            return None
        node_ids = [target]
        edge_ids = []
        while node_ids[-1] != source:
            parent, edge_id = previous[node_ids[-1]]
            node_ids.append(parent)
            edge_ids.append(edge_id)
        node_ids.reverse()
        edge_ids.reverse()
        return {
            "node_ids": node_ids,
            "nodes": [self.node_by_id[node_id] for node_id in node_ids],
            "edges": [self.edge_by_id[edge_id] for edge_id in edge_ids],
        }

    def gaps(self) -> list[dict[str, Any]]:
        return rule_gaps(self.payload)

    @staticmethod
    def _hidden(node: dict[str, Any], audience: str) -> bool:
        return (
            audience == "implementer"
            and node.get("properties", {}).get("visibility") == "inspector_private"
        )

    @staticmethod
    def _edge_hidden(edge: dict[str, Any], audience: str) -> bool:
        return (
            audience == "implementer"
            and edge.get("properties", {}).get("visibility") == "inspector_private"
        )

    @staticmethod
    def _audience(value: str) -> str:
        if value not in {"implementer", "verifier"}:
            raise ValueError("audience must be implementer or verifier")
        return value

    @staticmethod
    def _summary(node: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": node["id"],
            "kind": node["kind"],
            "name": node["name"],
            "statement": node.get("properties", {}).get("statement", ""),
        }


class ExplorerServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        index: GraphExplorerIndex,
        viewer_root: Path,
        chat_service: GraphChatService | None = None,
        evidence_store: EvidenceStore | None = None,
        factory_store: FactoryRunStore | None = None,
        evaluation_store: EvaluationStore | None = None,
        portfolio_store: PortfolioStore | None = None,
        durable_store: DurableStore | None = None,
        memory_store: SemanticMemoryStore | None = None,
        runtime_store: RuntimeEvidenceStore | None = None,
        audit_store: AuditStore | None = None,
        operational_store: OperationalEventStore | None = None,
    ) -> None:
        super().__init__(address, ExplorerRequestHandler)
        self.index = index
        self.viewer_root = viewer_root.resolve()
        self.project_root = self.viewer_root.parents[1]
        self.chat_service = chat_service or GraphChatService.from_environment(index)
        if evidence_store is None:
            default_pack = self.viewer_root.parent / "evidence" / "source.pack.json.gz"
            evidence_store = EvidenceStore(load_evidence_pack(default_pack)) if default_pack.is_file() else None
        self.evidence_store = evidence_store
        self.factory_store = factory_store or FactoryRunStore(
            self.viewer_root.parents[1] / "work"
        )
        self.evaluation_store = evaluation_store or EvaluationStore(
            self.viewer_root.parents[1] / "work"
        )
        self.portfolio_store = portfolio_store or PortfolioStore(
            self.viewer_root.parents[1] / "factory" / "portfolio" / "carddemo-plan.snapshot.json",
            self.viewer_root.parents[1] / "work" / "portfolio",
        )
        self.durable_store = durable_store or DurableStore(
            self.viewer_root.parents[1] / "work" / "durable" / "control.sqlite3"
        )
        self.memory_store = memory_store or SemanticMemoryStore(
            self.viewer_root.parents[1] / "factory" / "memory" / "store"
        )
        self.runtime_path = self.viewer_root.parent / "runtime" / "runtime.snapshot.json.gz"
        if runtime_store is None:
            default_runtime = self.runtime_path
            runtime_store = (
                RuntimeEvidenceStore(load_runtime_snapshot(default_runtime))
                if default_runtime.is_file()
                else None
            )
        self.runtime_store = runtime_store
        if (
            self.runtime_store is not None
            and self.runtime_store.snapshot.get("graph_content_sha256")
            != self.index.payload.get("content_sha256")
        ):
            raise ValueError("Runtime evidence snapshot targets a different graph identity")
        self.index.runtime_store = self.runtime_store
        self.audit_path = self.project_root / "audit" / "audit.snapshot.json.gz"
        if audit_store is None:
            default_audit = self.audit_path
            audit_store = AuditStore(load_audit_snapshot(default_audit)) if default_audit.is_file() else None
        self.audit_store = audit_store
        if (
            self.audit_store is not None
            and self.audit_store.snapshot.get("graph_content_sha256")
            != self.index.payload.get("content_sha256")
        ):
            raise ValueError("Audit snapshot targets a different graph identity")
        self._runtime_file_state = self._file_state(self.runtime_path)
        self._audit_file_state = self._file_state(self.audit_path)
        self.operational_store = operational_store or OperationalEventStore(
            self.project_root / "work" / "control-tower" / "events.sqlite3"
        )
        sources = (
            OperationalSource(
                "factory", (self.factory_store.root,), "controller-receipt", 2,
                lambda: {"runs": self.factory_store.list_runs(200)},
            ),
            OperationalSource(
                "portfolio", (self.portfolio_store.plan_path, self.portfolio_store.runs_root),
                "approved-plan", 5, self.portfolio_store.summary,
            ),
            OperationalSource(
                "recovery", (self.durable_store.path,), "transactional-ledger", 2,
                self.durable_store.summary,
            ),
            OperationalSource(
                "quality", (self.evaluation_store.root,), "evaluation-receipt", 10,
                lambda: {"evaluations": self.evaluation_store.list_evaluations(200)},
            ),
            OperationalSource(
                "memory", (self.memory_store.root,), "verified-semantic-memory", 15,
                self.memory_store.summary,
            ),
            OperationalSource(
                "data", (self.project_root / "data-modernization",), "data-equivalence-receipt", 15,
                self.data_summary,
            ),
            OperationalSource(
                "runtime", (self.runtime_path,), "runtime-observation", 30,
                self.runtime_summary,
            ),
            OperationalSource(
                "audit", (self.audit_path,), "hash-chained-audit", 5,
                self.audit_summary,
            ),
        )
        self.control_tower = OperationalControlTower(self.operational_store, sources)
        self.operational_monitor = OperationalMonitor(self.control_tower)

    @staticmethod
    def _file_state(path: Path) -> tuple[int, int] | None:
        if not path.is_file():
            return None
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def refresh_live_projections(self) -> None:
        runtime_state = self._file_state(self.runtime_path)
        if runtime_state != self._runtime_file_state:
            self.runtime_store = (
                RuntimeEvidenceStore(load_runtime_snapshot(self.runtime_path))
                if runtime_state is not None else None
            )
            self.index.runtime_store = self.runtime_store
            self._runtime_file_state = runtime_state
        audit_state = self._file_state(self.audit_path)
        if audit_state != self._audit_file_state:
            self.audit_store = (
                AuditStore(load_audit_snapshot(self.audit_path))
                if audit_state is not None else None
            )
            self._audit_file_state = audit_state

    def runtime_summary(self) -> dict[str, Any]:
        self.refresh_live_projections()
        if self.runtime_store is None:
            return {"runs": [], "statistics": {"run_count": 0, "event_count": 0}}
        return self.runtime_store.summary()

    def audit_summary(self) -> dict[str, Any]:
        self.refresh_live_projections()
        if self.audit_store is None:
            return {
                "statistics": {"event_count": 0, "decisions": {}, "active_exceptions": 0},
                "promotion_decisions": [],
                "trust_posture": {
                    "promotion_status": "not_evaluated", "unresolved_gaps": []
                },
            }
        return self.audit_store.summary()

    def data_summary(self) -> dict[str, Any]:
        root = self.project_root / "data-modernization"

        def load(relative: str) -> dict[str, Any]:
            path = root / relative
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

        model = load("canonical/authfrds.model.json")
        mapping = load("mappings/authfrds-postgresql.json")
        oracle_mapping = load("mappings/authfrds-oracle.json")
        receipt = load("receipts/authfrds.offline.receipt.json")
        oracle_offline = load("receipts/authfrds.oracle-offline.receipt.json")
        live_root = self.project_root / "work/data-modernization"
        def load_live(name: str) -> dict[str, Any]:
            path = live_root / name
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        targets = []
        for target_mapping, offline, filename in (
            (mapping, receipt, "live-postgresql.receipt.json"),
            (oracle_mapping, oracle_offline, "live-oracle.receipt.json"),
        ):
            live = load_live(filename)
            active = live or offline
            targets.append({
                "dialect": target_mapping.get("target_dialect", "not_available"),
                "target_table": target_mapping.get("target_table", ""),
                "adapter": target_mapping.get("adapter", {}),
                "evidence": "live-container" if live else "offline-development",
                "status": active.get("status", "not_available"),
                "production_ready": active.get("production_ready", False),
                "checks": active.get("checks", {}),
                "gaps": active.get("gaps", []),
                "content_sha256": active.get("content_sha256"),
                "image_identity": live.get("image_identity"),
            })
        return {
            "workload": receipt.get("workload", "carddemo-authorization-authfrds"),
            "status": receipt.get("status", "not_available"),
            "production_ready": receipt.get("production_ready", False),
            "evidence_class": receipt.get("evidence_class", "not_available"),
            "source_table": f"{model.get('schema', '')}.{model.get('name', '')}".strip("."),
            "target_table": mapping.get("target_table", ""),
            "targets": targets,
            "statistics": {
                "columns": len(model.get("columns", [])),
                "constraints": len(model.get("constraints", [])),
                "indexes": len(model.get("indexes", [])),
                "fixture_rows": receipt.get("statistics", {}).get("rows", 0),
            },
            "checks": receipt.get("checks", {}),
            "gaps": receipt.get("gaps", []),
            "content_sha256": receipt.get("content_sha256"),
            "signature": receipt.get("signature"),
        }


class ExplorerRequestHandler(BaseHTTPRequestHandler):
    server: ExplorerServer

    def do_GET(self) -> None:  # noqa: N802 - standard-library handler API
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/"):
                self._api(parsed.path, parse_qs(parsed.query))
            else:
                self._static(parsed.path)
        except KeyError as exc:
            self._json(
                {"error": f"Unknown or hidden graph entity: {exc.args[0]}"},
                HTTPStatus.NOT_FOUND,
            )
        except (TypeError, ValueError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._json({"error": f"Explorer request failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802 - standard-library handler API
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/chat":
                self._json(self.server.chat_service.answer(self._request_json()))
                return
            self._json({"error": f"Unknown API route: {parsed.path}"}, HTTPStatus.NOT_FOUND)
        except KeyError as exc:
            self._json(
                {"error": f"Unknown or hidden graph entity: {exc.args[0]}"},
                HTTPStatus.NOT_FOUND,
            )
        except (ChatError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._json({"error": f"Chat request failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _api(self, path: str, query: dict[str, list[str]]) -> None:
        index = self.server.index
        if path == "/api/operations/stream":
            self._event_stream(query)
            return
        if path == "/api/operations/status":
            self.server.control_tower.scan()
            self._json(self.server.control_tower.status())
            return
        if path == "/api/operations/events":
            self._json({
                "events": self.server.operational_store.events(
                    self._integer(query, "after", 0), self._integer(query, "limit", 200)
                ),
                "read_only": True,
            })
            return
        if path == "/api/meta":
            metadata = index.metadata()
            metadata["runtime"] = self.server.runtime_summary()["statistics"]
            metadata["audit"] = self.server.audit_summary()["statistics"]
            metadata["operations"] = self.server.control_tower.status()
            metadata["memory"] = self.server.memory_store.summary()["statistics"]
            portfolio = self.server.portfolio_store.summary()
            metadata["portfolio"] = {
                "status": portfolio.get("status"),
                "orders": len(portfolio.get("orders", [])),
                "waves": len(portfolio.get("waves", [])),
            }
            metadata["durable"] = self.server.durable_store.summary()["statistics"]
            metadata["data"] = self.server.data_summary()["statistics"]
            self._json(metadata)
            return
        if path == "/api/chat/status":
            self._json(self.server.chat_service.status())
            return
        if path == "/api/factory/runs":
            self._json(
                {
                    "runs": self.server.factory_store.list_runs(
                        self._integer(query, "limit", 50)
                    )
                }
            )
            return
        if path == "/api/factory/run":
            audience = self._value(query, "audience") or "implementer"
            if audience not in {"implementer", "verifier"}:
                raise ValueError("audience must be implementer or verifier")
            self._json(
                self.server.factory_store.run(
                    self._value(query, "id", required=True),
                    include_private=audience == "verifier",
                )
            )
            return
        if path == "/api/portfolio/summary":
            self._json(self.server.portfolio_store.summary())
            return
        if path == "/api/durable/summary":
            self._json(self.server.durable_store.summary())
            return
        if path == "/api/evaluations":
            self._json({
                "evaluations": self.server.evaluation_store.list_evaluations(
                    self._integer(query, "limit", 50)
                )
            })
            return
        if path == "/api/evaluation":
            self._json(self.server.evaluation_store.evaluation(
                self._value(query, "id", required=True)
            ))
            return
        if path == "/api/memory/summary":
            self._json(self.server.memory_store.summary())
            return
        if path == "/api/memory/experience":
            self._json(self.server.memory_store.experience(
                self._value(query, "id", required=True)
            ))
            return
        if path == "/api/runtime/summary":
            self._json(self.server.runtime_summary())
            return
        if path == "/api/data/summary":
            self._json(self.server.data_summary())
            return
        if path == "/api/runtime/run":
            self.server.refresh_live_projections()
            if self.server.runtime_store is None:
                raise KeyError(self._value(query, "id", required=True))
            self._json(self.server.runtime_store.run(self._value(query, "id", required=True)))
            return
        if path == "/api/audit/summary":
            self._json(self.server.audit_summary())
            return
        if path == "/api/audit/events":
            self.server.refresh_live_projections()
            if self.server.audit_store is None:
                self._json({"events": [], "total": 0})
            else:
                self._json(self.server.audit_store.events(
                    self._value(query, "audience") or "implementer",
                    self._integer(query, "limit", 100),
                ))
            return
        if path == "/api/audit/decision":
            self.server.refresh_live_projections()
            if self.server.audit_store is None:
                raise KeyError(self._value(query, "id", required=True))
            self._json(self.server.audit_store.decision(self._value(query, "id", required=True)))
            return
        if path == "/api/audit/dossier":
            self.server.refresh_live_projections()
            if self.server.audit_store is None:
                raise KeyError(self._value(query, "release", required=True))
            self._json(self.server.audit_store.dossier(
                self._value(query, "release", required=True)
            ))
            return
        if path == "/api/edge":
            edge_id = self._value(query, "id", required=True)
            result = index.edge(
                edge_id,
                self._value(query, "audience") or "implementer",
            )
            result["runtime"] = self._runtime_projection("edge", edge_id)
            self._json(result)
            return
        if path == "/api/evidence":
            self._json(self._evidence(index, query))
            return
        if path == "/api/search":
            self._json(
                {
                    "results": index.search(
                        self._value(query, "q"),
                        self._value(query, "kind"),
                        self._integer(query, "limit", 25),
                        self._value(query, "audience") or "implementer",
                    )
                }
            )
            return
        if path == "/api/node":
            node_id = self._value(query, "id", required=True)
            result = index.node(
                node_id,
                self._value(query, "audience") or "implementer",
            )
            result["runtime"] = self._runtime_projection("node", node_id)
            self._json(result)
            return
        if path == "/api/neighborhood":
            selection = index.neighborhood(
                self._value(query, "node", required=True),
                self._integer(query, "depth", 2),
                self._value(query, "audience") or "implementer",
                self._integer(query, "limit", index.max_nodes),
            )
            self._json(selection.to_dict())
            return
        if path == "/api/trace":
            result = index.trace(
                self._value(query, "from", required=True),
                self._value(query, "to", required=True),
                self._value(query, "audience") or "implementer",
            )
            self._json({"status": "found" if result else "not_found", "trace": result})
            return
        if path == "/api/gaps":
            gaps = index.gaps()
            self._json({"status": "passed" if not gaps else "failed", "gaps": gaps})
            return
        self._json({"error": f"Unknown API route: {path}"}, HTTPStatus.NOT_FOUND)

    def _event_stream(self, query: dict[str, list[str]]) -> None:
        after = self._integer(query, "after", 0)
        header_sequence = self.headers.get("Last-Event-ID", "")
        if header_sequence.isdigit():
            after = max(after, int(header_sequence))
        channel = self.server.operational_store.subscribe(after)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 2000\nevent: ready\ndata: {\"status\":\"live\"}\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = channel.get(timeout=15)
                    body = json.dumps(event, sort_keys=True, separators=(",", ":"))
                    packet = (
                        f"id: {event['sequence']}\nevent: operational-event\ndata: {body}\n\n"
                    ).encode("utf-8")
                except queue.Empty:
                    packet = b": heartbeat\n\n"
                self.wfile.write(packet)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            self.server.operational_store.unsubscribe(channel)

    def _runtime_projection(self, entity_kind: str, entity_id: str) -> dict[str, Any]:
        return self.server.index.runtime_projection(entity_kind, entity_id)

    def _evidence(
        self, index: GraphExplorerIndex, query: dict[str, list[str]]
    ) -> dict[str, Any]:
        if self.server.evidence_store is None:
            raise ValueError("Source evidence pack is not available.")
        owner_type = self._value(query, "owner_type", required=True)
        owner_id = self._value(query, "owner_id", required=True)
        evidence_index = self._integer(query, "evidence_index", -1)
        audience = self._value(query, "audience") or "implementer"
        if owner_type == "node":
            owner = index.node(owner_id, audience)
        elif owner_type == "edge":
            owner = index.edge(owner_id, audience)
        else:
            raise ValueError("owner_type must be node or edge")
        evidence_items = owner.get("evidence", [])
        if evidence_index < 0 or evidence_index >= len(evidence_items):
            raise ValueError("evidence_index is outside the selected owner")
        try:
            excerpt = self.server.evidence_store.excerpt(
                owner_type, owner_id, evidence_index
            )
        except KeyError as exc:
            raise ValueError("No source capsule exists for this evidence item") from exc
        return {
            **excerpt,
            "graph_content_sha256": index.payload["content_sha256"],
            "owner_id": owner_id,
            "owner_type": owner_type,
        }

    def _static(self, raw_path: str) -> None:
        requested = "index.html" if raw_path in {"", "/"} else unquote(raw_path.lstrip("/"))
        candidate = (self.server.viewer_root / requested).resolve()
        if self.server.viewer_root not in candidate.parents and candidate != self.server.viewer_root:
            self._json({"error": "Invalid static path"}, HTTPStatus.BAD_REQUEST)
            return
        if not candidate.is_file():
            self._json({"error": "Static asset not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type, _ = mimetypes.guess_type(candidate.name)
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _request_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ChatError("Request body is required.")
        if content_length > 65536:
            raise ChatError("Request body exceeds the 64 KiB limit.")
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            raise ChatError("Content-Type must be application/json.")
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ChatError("Request body must be a JSON object.")
        return payload

    @staticmethod
    def _value(query: dict[str, list[str]], key: str, required: bool = False) -> str:
        value = query.get(key, [""])[0]
        if required and not value:
            raise ValueError(f"Missing required query parameter: {key}")
        return value

    @classmethod
    def _integer(cls, query: dict[str, list[str]], key: str, default: int) -> int:
        value = cls._value(query, key)
        return int(value) if value else default


def serve(
    graph_path: Path,
    viewer_root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    ontology_path: Path | None = None,
    evidence_pack_path: Path | None = None,
    factory_runs_path: Path | None = None,
    runtime_snapshot_path: Path | None = None,
    audit_snapshot_path: Path | None = None,
) -> None:
    ontology = load_ontology(ontology_path) if ontology_path else load_ontology()
    index = GraphExplorerIndex(load_graph(graph_path), ontology=ontology)
    pack_path = evidence_pack_path or graph_path.parent / "evidence" / "source.pack.json.gz"
    evidence_store = EvidenceStore(load_evidence_pack(pack_path))
    factory_store = FactoryRunStore(
        factory_runs_path or viewer_root.resolve().parents[1] / "work"
    )
    runtime_path = runtime_snapshot_path or graph_path.parent / "runtime" / "runtime.snapshot.json.gz"
    runtime_store = (
        RuntimeEvidenceStore(load_runtime_snapshot(runtime_path))
        if runtime_path.is_file()
        else None
    )
    audit_path = audit_snapshot_path or viewer_root.resolve().parents[1] / "audit" / "audit.snapshot.json.gz"
    audit_store = AuditStore(load_audit_snapshot(audit_path)) if audit_path.is_file() else None
    server = ExplorerServer(
        (host, port), index, viewer_root, evidence_store=evidence_store,
        factory_store=factory_store,
        evaluation_store=EvaluationStore(factory_runs_path or viewer_root.resolve().parents[1] / "work"),
        runtime_store=runtime_store, audit_store=audit_store,
    )
    url = f"http://{host}:{server.server_port}/"
    print(f"LIGHTYEAR Graph Explorer: {url}")
    print("Live Evidence Plane: connected (read-only command posture)")
    print("Press Ctrl-C to stop.")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.operational_monitor.start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.operational_monitor.stop()
        server.server_close()
