from __future__ import annotations

import copy
import json
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from lightyear_knowledge_graph.chat import GraphChatService
from lightyear_knowledge_graph.evidence_pack import (
    EvidenceStore,
    load_evidence_pack,
    validate_evidence_pack,
)
from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph
from lightyear_knowledge_graph.ontology import (
    load_ontology,
    validate_graph_relationships,
    validate_ontology,
)


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "knowledge" / "graph.snapshot.json.gz"
EVIDENCE_PACK = ROOT / "knowledge" / "evidence" / "source.pack.json.gz"
PRIVATE_NODE = "scenario:intcalc:private-holdout-boundary"
WORKLOAD = "workload:carddemo-intcalc"


class EdgeIntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_graph(GRAPH)
        cls.ontology = load_ontology()
        cls.pack = load_evidence_pack(EVIDENCE_PACK)
        cls.index = GraphExplorerIndex(cls.graph, ontology=cls.ontology)
        cls.derived_edge = next(
            edge
            for edge in cls.graph["edges"]
            if edge["source"] == "rule:intcalc:monthly-interest"
            and edge["relation"] == "DERIVED_FROM"
            and edge["evidence"]
        )
        cls.private_edge = next(
            edge
            for edge in cls.graph["edges"]
            if edge["source"] == WORKLOAD and edge["target"] == PRIVATE_NODE
        )

    def test_relationship_ontology_covers_every_edge_and_pair(self) -> None:
        self.assertEqual([], validate_ontology(self.ontology))
        self.assertEqual([], validate_graph_relationships(self.graph, self.ontology))
        self.assertEqual(
            set(self.graph["statistics"]["edges_by_relation"]),
            set(self.ontology["relations"]),
        )
        changed = copy.deepcopy(self.graph)
        changed["edges"][0]["relation"] = "INVENTED_RELATIONSHIP"
        self.assertTrue(
            any("undefined relationship" in item for item in validate_graph_relationships(changed, self.ontology))
        )

    def test_evidence_pack_is_complete_content_addressed_and_path_safe(self) -> None:
        self.assertEqual([], validate_evidence_pack(self.graph, self.pack))
        self.assertGreater(self.pack["statistics"]["capsule_count"], 10_000)
        self.assertTrue(
            all(
                not Path(capsule["path"]).is_absolute()
                and ".." not in Path(capsule["path"]).parts
                for capsule in self.pack["capsules"]
            )
        )
        changed = copy.deepcopy(self.pack)
        changed["capsules"][0]["lines"][0]["text"] = "tampered"
        errors = validate_evidence_pack(self.graph, changed)
        self.assertTrue(any("excerpt hash does not match" in item for item in errors))

    def test_edge_inspector_exposes_semantics_and_respects_private_endpoints(self) -> None:
        edge = self.index.edge(self.derived_edge["id"], "implementer")
        self.assertEqual("derived from", edge["definition"]["label"])
        self.assertIn("legacy source evidence", edge["definition"]["purpose"])
        self.assertEqual("Calculate monthly interest", edge["source_node"]["name"])
        with self.assertRaises(KeyError):
            self.index.edge(self.private_edge["id"], "implementer")
        self.assertEqual(
            "HAS_SCENARIO", self.index.edge(self.private_edge["id"], "verifier")["relation"]
        )

    def test_structural_edge_inherits_clickable_endpoint_source_evidence(self) -> None:
        structural_edge = next(
            edge
            for edge in self.graph["edges"]
            if not edge.get("evidence")
            and edge.get("visibility", "shared") == "shared"
            and (
                self.index.node_by_id[edge["source"]].get("evidence")
                or self.index.node_by_id[edge["target"]].get("evidence")
            )
        )
        inspected = self.index.edge(structural_edge["id"], "implementer")
        support = inspected["supporting_evidence"][0]
        self.assertIn(support["role"], {"source endpoint", "target endpoint"})
        excerpt = EvidenceStore(self.pack).excerpt(
            support["owner_type"], support["owner_id"], support["evidence_index"]
        )
        self.assertEqual(support["evidence"]["path"], excerpt["path"])
        self.assertTrue(any(line["highlighted"] for line in excerpt["lines"]))

    def test_chat_can_focus_on_one_relationship(self) -> None:
        answer = GraphChatService(self.index).answer(
            {
                "question": "Why does this relationship exist?",
                "focus_edge_id": self.derived_edge["id"],
                "audience": "implementer",
                "provider": "local",
            }
        )
        self.assertEqual(self.derived_edge["id"], answer["grounding"]["focus_edge_id"])
        self.assertIn("DERIVED_FROM", answer["answer"])
        self.assertIn(self.derived_edge["id"], answer["grounding"]["edge_ids"])

    def test_http_edge_and_evidence_routes_never_accept_a_source_path(self) -> None:
        server = ExplorerServer(
            ("127.0.0.1", 0),
            self.index,
            ROOT / "knowledge" / "viewer",
            evidence_store=EvidenceStore(self.pack),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            edge_query = urlencode(
                {"id": self.derived_edge["id"], "audience": "implementer"}
            )
            with urlopen(f"{base}/api/edge?{edge_query}", timeout=3) as response:
                edge = json.load(response)
            self.assertEqual("DERIVED_FROM", edge["relation"])
            evidence_query = urlencode(
                {
                    "audience": "implementer",
                    "evidence_index": 0,
                    "owner_id": self.derived_edge["id"],
                    "owner_type": "edge",
                    "path": "../../etc/passwd",
                }
            )
            with urlopen(f"{base}/api/evidence?{evidence_query}", timeout=3) as response:
                excerpt = json.load(response)
            self.assertEqual(self.derived_edge["evidence"][0]["path"], excerpt["path"])
            self.assertNotIn(str(ROOT), json.dumps(excerpt))
            self.assertTrue(any(line["highlighted"] for line in excerpt["lines"]))

            private_query = urlencode(
                {
                    "audience": "implementer",
                    "evidence_index": 0,
                    "owner_id": self.private_edge["id"],
                    "owner_type": "edge",
                }
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(f"{base}/api/evidence?{private_query}", timeout=3)
            self.assertEqual(404, caught.exception.code)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_viewer_contains_clickable_edge_and_source_surfaces(self) -> None:
        app = (ROOT / "knowledge" / "viewer" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "knowledge" / "viewer" / "index.html").read_text(encoding="utf-8")
        self.assertIn('hit.classList.add("edge-hit")', app)
        self.assertIn('api("/api/evidence"', app)
        self.assertIn('id="edge-inspector"', html)
        self.assertIn('id="source-drawer"', html)


if __name__ == "__main__":
    unittest.main()
