from __future__ import annotations

import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_knowledge_graph.model import graph_hash, load_graph
from lightyear_knowledge_graph.query import neighborhood, shortest_trace
from lightyear_knowledge_graph.validation import rule_gaps, validate_graph


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "knowledge" / "graph.snapshot.json.gz"


class KnowledgeGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_graph(GRAPH)

    def test_snapshot_is_integral_and_policy_complete(self) -> None:
        self.assertEqual([], validate_graph(self.graph))
        self.assertEqual([], rule_gaps(self.graph))
        self.assertEqual(self.graph["content_sha256"], graph_hash(self.graph))

    def test_snapshot_maps_the_estate_and_verified_vertical_slice(self) -> None:
        stats = self.graph["statistics"]
        self.assertGreaterEqual(stats["nodes_by_kind"]["cobol_program"], 40)
        self.assertGreaterEqual(stats["nodes_by_kind"]["jcl_job"], 40)
        self.assertGreaterEqual(stats["nodes_by_kind"]["cobol_field"], 1000)
        self.assertEqual(9, stats["nodes_by_kind"]["business_rule"])
        self.assertIn(
            "modern:file:src/lightyear_factory/orchestrator.py",
            {node["id"] for node in self.graph["nodes"]},
        )

    def test_business_rule_traces_to_implementation_and_test(self) -> None:
        rule = "rule:intcalc:monthly-interest"
        implementation = "modern:java-method:ai.lightyear.carddemo.service.InterestCalculationService#calculate"
        test = "modern:test:ai.lightyear.carddemo.service.InterestCalculationServiceTest#matchesInterestAndDefaultRateRules"
        self.assertIsNotNone(shortest_trace(self.graph, rule, implementation))
        self.assertIsNotNone(shortest_trace(self.graph, rule, test))

    def test_implementer_context_hides_private_holdout(self) -> None:
        root = "workload:carddemo-intcalc"
        implementer = neighborhood(self.graph, root, depth=1, audience="implementer")
        verifier = neighborhood(self.graph, root, depth=1, audience="verifier")
        implementer_ids = {item["id"] for item in implementer["nodes"]}
        verifier_ids = {item["id"] for item in verifier["nodes"]}
        private_id = "scenario:intcalc:private-holdout-boundary"
        self.assertNotIn(private_id, implementer_ids)
        self.assertIn(private_id, verifier_ids)

    def test_validator_detects_rule_mapping_gap_and_tampering(self) -> None:
        changed = copy.deepcopy(self.graph)
        changed["edges"] = [
            edge
            for edge in changed["edges"]
            if not (
                edge["source"] == "rule:intcalc:zero-rate"
                and edge["relation"] == "IMPLEMENTED_BY"
            )
        ]
        gaps = rule_gaps(changed)
        self.assertEqual(["IMPLEMENTED_BY"], gaps[0]["missing_relations"])
        self.assertIn("content_sha256 does not match canonical graph content", validate_graph(changed))

    def test_snapshot_content_is_independent_of_gzip_header_metadata(self) -> None:
        serialized = json.dumps(self.graph, sort_keys=True).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json.gz"
            second = Path(directory) / "second.json.gz"
            first.write_bytes(gzip.compress(serialized, mtime=0))
            second.write_bytes(gzip.compress(serialized, mtime=123456789))
            self.assertNotEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(load_graph(first)["content_sha256"], load_graph(second)["content_sha256"])


if __name__ == "__main__":
    unittest.main()
