from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lightyear_knowledge_graph.explorer import (
    ExplorerServer,
    GraphExplorerIndex,
    is_loopback_host,
    validate_bind_host,
)
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
        self.assertEqual(9, len(perspectives))
        self.assertIn("authfrds-data-lineage", {item["id"] for item in perspectives})
        self.assertIn("ims-expired-authorization-purge", {item["id"] for item in perspectives})
        self.assertTrue(all(item["root"] in self.index.node_by_id for item in perspectives))

    def test_operator_context_separates_scope_lens_and_graph_coverage(self) -> None:
        context = self.index.metadata()["operator_context"]
        self.assertEqual("CardDemo Reference Estate", context["customers"][0]["name"])
        self.assertEqual(context["customers"], context["companies"])
        self.assertEqual(
            {
                "account-and-card-servicing",
                "authorization-and-fraud",
                "shared-platform-services",
            },
            {item["id"] for item in context["problems"]},
        )
        self.assertEqual(5, len(context["workloads"]))
        self.assertTrue(all(item["root"] in self.index.node_by_id for item in context["workloads"]))
        self.assertTrue(all(item["perspective_id"] for item in context["workloads"]))
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

    def test_non_loopback_bind_requires_an_explicit_risk_flag(self) -> None:
        for host in ("127.0.0.1", "127.7.4.2", "::1", "localhost"):
            self.assertTrue(is_loopback_host(host))
            validate_bind_host(host)
        for host in ("0.0.0.0", "192.168.1.20", "control-tower.internal"):
            self.assertFalse(is_loopback_host(host))
            with self.assertRaisesRegex(ValueError, "Refusing non-loopback bind"):
                validate_bind_host(host)
            validate_bind_host(host, allow_unauthenticated_network=True)

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
            self.assertIn("Knowledge Graph", body)
            self.assertIn("graph-binding-hash", body)
            self.assertIn("live-endpoint", body)
            self.assertIn("Discovery view · not live equivalence", body)
            self.assertNotIn("fonts.googleapis.com", body)
            self.assertIn('id="estate-trigger"', body)
            self.assertIn('for="problem-context"', body)
            self.assertIn('for="workload-context"', body)
            self.assertIn('id="density-guard"', body)
            self.assertIn("Open proof run for this workload", body)
            self.assertIn('id="verifier-dialog"', body)
            self.assertIn("Search selected estate", body)
            self.assertIn("assets/lightyear-primary.svg", body)
            self.assertIn("Technology scope", body)
            self.assertIn("CROSS-PLATFORM EVIDENCE TRACE", body)
            with urlopen(f"{base}/app.js", timeout=3) as response:
                script = response.read().decode("utf-8")
            self.assertIn("Attach a graph fragment and customer integration edges first", script)
            self.assertIn("workload.target_status", script)
            self.assertIn('direction: $("trace-direction").value', script)
            self.assertIn("graph: refreshGraphProjection", script)
            self.assertIn("Live graph stream connected", script)
            self.assertIn("startLiveStatusPolling", script)
            self.assertIn("/api/operations/status", script)
            self.assertIn("activateSelectedWorkload", script)
            self.assertIn("READABLE_NODE_LIMIT", script)
            self.assertIn("collapseImplementationPackages", script)
            self.assertIn("labelPlacements", script)
            self.assertIn('group.setAttribute("tabindex"', script)
            self.assertIn("handleGraphNodeKeydown", script)
            self.assertIn("focusInitialGraphNode", script)
            self.assertIn('$("density-collapse").addEventListener', script)
            self.assertIn('$("density-rules").addEventListener', script)
            self.assertIn('$("density-bridges").addEventListener', script)
            self.assertIn('$("density-render-all").addEventListener', script)
            self.assertIn('$("density-guard").hidden = true', script)
            self.assertIn("role", script)
            self.assertIn("No matching entities in the selected estate", script)
            self.assertIn("Static file mode cannot connect to the live graph", script)
            with urlopen(f"{base}/styles.css", timeout=3) as response:
                styles = response.read().decode("utf-8")
            for graph_color in (
                "#f7f6fc", "#fefefe", "#15184d", "#7d57ea", "#a7702c",
                "#315bb5", "#207565", "#a74336", "#a93680",
            ):
                self.assertIn(graph_color, styles)
            self.assertIn("LIGHTYEAR Brand Kit v1.0", styles)
            self.assertIn(".graph-binding.invalidated", styles)
            self.assertIn('"IBM Plex Sans"', styles)
            self.assertIn("@font-face", styles)
            self.assertIn(".combobox-trigger", styles)
            self.assertIn(".density-guard", styles)
            self.assertIn(".density-guard[hidden], #graph[hidden] { display: none; }", styles)
            self.assertIn(".node:focus-visible", styles)
            self.assertIn("font: 500 12px/1.05 var(--mono)", styles)
            self.assertIn(".node text { stroke: none; font-size: 11px", styles)
            with urlopen(f"{base}/fonts/IBMPlexSans-Regular-Latin1.woff2", timeout=3) as response:
                self.assertGreater(len(response.read()), 1000)

            protected = f"{base}/api/search?q=private+legacy&audience=verifier"
            with self.assertRaises(HTTPError) as denied:
                urlopen(protected, timeout=3)
            self.assertEqual(401, denied.exception.code)
            request = Request(
                protected,
                headers={"Authorization": f"Bearer {server.verifier_token}"},
            )
            with urlopen(request, timeout=3) as response:
                verifier_results = json.load(response)
            self.assertEqual(1, len(verifier_results["results"]))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_graph_label_placement_is_collision_free(self) -> None:
        script = r"""
const { boxesIntersect, labelPlacements } = require(process.argv[1]);
const nodes = [
  { id: "root", name: "CardDemo interest calculation" },
  { id: "near", name: "Pinned upstream ASCII difference" },
  { id: "east", name: "Calculate monthly interest" },
  { id: "south", name: "Preserve source final account" },
];
const edges = [
  { source: "root", target: "near" },
  { source: "root", target: "east" },
  { source: "root", target: "south" },
];
const positions = new Map([
  ["root", { x: 280, y: 180 }],
  ["near", { x: 305, y: 180 }],
  ["east", { x: 470, y: 180 }],
  ["south", { x: 280, y: 310 }],
]);
const result = labelPlacements(nodes, edges, positions, 700, 480, "root");
const boxes = [];
for (const node of nodes) {
  const placement = result.get(node.id);
  if (!placement) continue;
  const point = positions.get(node.id);
  const box = { x: point.x + placement.x, y: point.y + placement.y, width: placement.width, height: placement.height };
  if (boxes.some((other) => boxesIntersect(box, other))) throw new Error(`overlap:${node.id}`);
  boxes.push(box);
}
if (boxes.length < 3) throw new Error(`too-many-hidden:${boxes.length}`);
console.log(JSON.stringify({ visible: boxes.length }));
"""
        result = subprocess.run(
            ["node", "-e", script, str(ROOT / "knowledge" / "viewer" / "app.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)["visible"], 3)

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
