from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_knowledge_graph.model import load_graph
from lightyear_knowledge_graph.oracle_reference import (
    OPERATOR_ESTATE_NAME,
    build_oracle_reference_fragment,
    validate_oracle_reference_fragment,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "knowledge" / "graph.snapshot.json.gz"
ESTATE = ROOT / "reference-estates" / "idempiere"
FRAGMENT = ESTATE / "oracle-customer-large.fragment.json"


class OracleReferenceProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = load_graph(BASE)
        cls.slices = json.loads((ESTATE / "business-slices.json").read_text(encoding="utf-8"))
        cls.inventory = json.loads((ESTATE / "inventory.json").read_text(encoding="utf-8"))
        cls.pin = json.loads((ESTATE / "source-pin.json").read_text(encoding="utf-8"))
        cls.fragment = json.loads(FRAGMENT.read_text(encoding="utf-8"))

    def test_committed_projection_is_deterministic_and_bounded(self) -> None:
        expected = build_oracle_reference_fragment(
            self.base, self.slices, self.inventory, self.pin
        )
        self.assertEqual(expected, self.fragment)
        self.assertEqual([], validate_oracle_reference_fragment(
            self.fragment, self.base, self.slices, self.inventory, self.pin
        ))
        self.assertEqual(OPERATOR_ESTATE_NAME, self.fragment["source"]["operator_estate_name"])
        self.assertEqual(22, self.fragment["statistics"]["node_count"])
        self.assertEqual(20, self.fragment["statistics"]["edge_count"])

    def test_operator_names_hide_upstream_product_but_provenance_keeps_it(self) -> None:
        self.assertEqual("iDempiere", self.fragment["source"]["upstream_product"])
        self.assertTrue(all(
            "idempiere" not in node["name"].casefold()
            for node in self.fragment["nodes"]
        ))
        workloads = [
            node for node in self.fragment["nodes"]
            if node["kind"] == "modernization_workload"
        ]
        self.assertEqual(["Order to cash", "Procure to pay"], [node["name"] for node in workloads])
        self.assertTrue(all(
            node["properties"]["operator_platform"] == "Oracle"
            and node["properties"]["runtime_observed"] is False
            for node in self.fragment["nodes"]
        ))

    def test_each_curated_flow_edge_becomes_one_static_trace_scenario(self) -> None:
        expected = {
            (slice_item["id"], sequence, tuple(flow))
            for slice_item in self.slices["slices"]
            for sequence, flow in enumerate(slice_item["edges"], start=1)
        }
        actual = {
            (
                node["properties"]["workload_id"].rsplit(":", 1)[-1],
                node["properties"]["sequence"],
                (
                    node["properties"]["source_table"],
                    node["properties"]["expected_relation"],
                    node["properties"]["target_table"],
                ),
            )
            for node in self.fragment["nodes"]
            if node["kind"] == "verification_scenario"
        }
        self.assertEqual(expected, actual)

    def test_tampering_and_runtime_overclaim_fail_closed(self) -> None:
        changed = copy.deepcopy(self.fragment)
        changed["nodes"][0]["properties"]["runtime_observed"] = True
        errors = validate_oracle_reference_fragment(
            changed, self.base, self.slices, self.inventory, self.pin
        )
        self.assertTrue(any("not the deterministic projection" in error for error in errors))
        self.assertTrue(any("overstates runtime observation" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
