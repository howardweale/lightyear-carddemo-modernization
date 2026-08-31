from __future__ import annotations

import csv
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph
from lightyear_knowledge_graph.neo4j_export import export_neo4j


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "knowledge" / "graph.snapshot.json.gz"
PRIVATE_NODE = "scenario:intcalc:private-holdout-boundary"
WORKLOAD = "workload:carddemo-intcalc"
DB2_WRITER = "legacy:cobol-program:COPAUS2C"
DB2_TABLE = "legacy:db2-table:CARDDEMO.AUTHFRDS"
IMS_DELETE = "legacy:cobol-paragraph:CBPAUP0C:5000-DELETE-AUTH-DTL"
IMS_SEGMENT = "legacy:ims-segment:DBPAUTP0:PAUTDTL1"


class GraphExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_graph(GRAPH)
        cls.index = GraphExplorerIndex(cls.payload, max_nodes=80)

    def test_curated_perspectives_resolve_to_graph_nodes(self) -> None:
        perspectives = self.index.perspectives()
        self.assertEqual(6, len(perspectives))
        self.assertIn("authfrds-data-lineage", {item["id"] for item in perspectives})
        self.assertTrue(all(item["root"] in self.index.node_by_id for item in perspectives))

    def test_operator_context_separates_scope_lens_and_graph_coverage(self) -> None:
        context = self.index.metadata()["operator_context"]
        self.assertEqual("CardDemo Reference Estate", context["customers"][0]["name"])
        self.assertEqual(
            {"all-estate", "mainframe", "database", "sap-estate"},
            {item["id"] for item in context["scopes"]},
        )
        security = next(item for item in context["lenses"] if item["id"] == "security")
        self.assertTrue(security["planned"])
        by_platform = {item["name"]: item for item in context["platforms"]}
        self.assertEqual("projected", by_platform["DB2"]["status"])
        self.assertGreater(by_platform["DB2"]["node_count"], 0)
        self.assertEqual("qualification-not-projected", by_platform["Oracle"]["status"])
        self.assertEqual("qualification-not-projected", by_platform["SAP ASE"]["status"])
        examples = {item["id"] for item in context["trace"]["examples"]}
        self.assertEqual(
            {"cobol-db2-update", "cobol-ims-dependency", "cobol-ims-delete"}, examples
        )

    def test_cobol_ims_delete_is_a_source_backed_static_write_path(self) -> None:
        trace = self.index.trace(IMS_DELETE, IMS_SEGMENT, direction="directed")
        self.assertIsNotNone(trace)
        self.assertEqual(["ISSUES_DLI", "WRITES_SEGMENT"], [
            edge["relation"] for edge in trace["edges"]
        ])
        self.assertEqual("static-source", trace["evidence_class"])
        self.assertFalse(trace["runtime_observed"])
        self.assertFalse(trace["customer_evidence"])

    def test_directed_trace_does_not_reverse_relationship_semantics(self) -> None:
        directed = self.index.trace(DB2_WRITER, DB2_TABLE, direction="directed")
        self.assertIsNotNone(directed)
        self.assertEqual("directed", directed["direction"])
        self.assertEqual(["COBOL", "DB2"], directed["platforms"])
        self.assertFalse(directed["runtime_observed"])
        self.assertIsNone(self.index.trace(DB2_TABLE, DB2_WRITER, direction="directed"))
        self.assertIsNotNone(self.index.trace(DB2_TABLE, DB2_WRITER, direction="any"))
        with self.assertRaises(ValueError):
            self.index.trace(DB2_WRITER, DB2_TABLE, direction="invented")

    def test_every_explorer_route_respects_private_visibility(self) -> None:
        self.assertEqual([], self.index.search("private legacy", audience="implementer"))
        self.assertEqual(1, len(self.index.search("private legacy", audience="verifier")))
        with self.assertRaises(KeyError):
            self.index.node(PRIVATE_NODE, audience="implementer")
        with self.assertRaises(KeyError):
            self.index.neighborhood(PRIVATE_NODE, audience="implementer")
        with self.assertRaises(KeyError):
            self.index.trace(WORKLOAD, PRIVATE_NODE, audience="implementer")
        self.assertIsNotNone(self.index.trace(WORKLOAD, PRIVATE_NODE, audience="verifier"))

    def test_neighborhood_is_bounded_and_reports_truncation(self) -> None:
        selection = self.index.neighborhood(
            "legacy:copybook:CVACT01Y",
            depth=4,
            audience="implementer",
            limit=20,
        )
        self.assertLessEqual(len(selection.nodes), 20)
        self.assertTrue(selection.truncated)
        self.assertTrue(
            all(
                edge["source"] in {node["id"] for node in selection.nodes}
                and edge["target"] in {node["id"] for node in selection.nodes}
                for edge in selection.edges
            )
        )

    def test_http_server_serves_metadata_and_viewer(self) -> None:
        server = ExplorerServer(("127.0.0.1", 0), self.index, ROOT / "knowledge" / "viewer")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(f"{base}/api/meta", timeout=3) as response:
                metadata = json.load(response)
            self.assertEqual(self.payload["content_sha256"], metadata["content_sha256"])
            self.assertEqual(26, metadata["data"]["columns"])
            with urlopen(f"{base}/api/data/summary", timeout=3) as response:
                data = json.load(response)
            self.assertEqual("passed", data["status"])
            self.assertFalse(data["production_ready"])
            with urlopen(f"{base}/", timeout=3) as response:
                body = response.read().decode("utf-8")
            self.assertIn("LIGHTYEAR Control Tower", body)
            self.assertIn("Technology scope", body)
            self.assertIn("CROSS-PLATFORM EVIDENCE TRACE", body)
            with urlopen(f"{base}/app.js", timeout=3) as response:
                script = response.read().decode("utf-8")
            self.assertIn("Attach a graph fragment and customer integration edges first", script)
            self.assertIn('direction: $("trace-direction").value', script)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_neo4j_projection_preserves_graph_counts_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            receipt = export_neo4j(self.payload, output)
            with (output / "nodes.csv").open(newline="", encoding="utf-8") as handle:
                nodes = list(csv.DictReader(handle))
            with (output / "relationships.csv").open(newline="", encoding="utf-8") as handle:
                relationships = list(csv.DictReader(handle))
            self.assertEqual(len(self.payload["nodes"]), len(nodes))
            self.assertEqual(len(self.payload["edges"]), len(relationships))
            self.assertEqual(self.payload["content_sha256"], receipt["graph_content_sha256"])
            self.assertEqual("Entity;BusinessRule", next(
                row[":LABEL"] for row in nodes if row["nodeId:ID"] == "rule:intcalc:monthly-interest"
            ))
            self.assertTrue((output / "constraints.cypher").is_file())


if __name__ == "__main__":
    unittest.main()
