from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import unittest
from pathlib import Path

from lightyear_knowledge_graph.cloudbank_reference import (
    OPERATOR_ESTATE_NAME,
    build_cloudbank_reference_fragment,
    validate_cloudbank_reference_fragment,
)
from lightyear_knowledge_graph.model import load_graph


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "knowledge" / "graph.snapshot.json.gz"
ESTATE = ROOT / "reference-estates" / "cloudbank"
FRAGMENT = ESTATE / "cloudbank-reference.fragment.json"
PINNED_COMMIT = "4f41b16d00c45503f691836fee8138010c969e86"


class CloudBankReferenceEstateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = load_graph(BASE)
        cls.workloads = json.loads((ESTATE / "workloads.json").read_text(encoding="utf-8"))
        cls.inventory = json.loads((ESTATE / "inventory.json").read_text(encoding="utf-8"))
        cls.pin = json.loads((ESTATE / "source-pin.json").read_text(encoding="utf-8"))
        cls.fragment = json.loads(FRAGMENT.read_text(encoding="utf-8"))

    def test_official_source_is_pinned_without_vendoring_or_execution(self) -> None:
        self.assertEqual(PINNED_COMMIT, self.pin["source"]["commit"])
        self.assertEqual("cloudbank-v5", self.pin["source"]["subtree"])
        self.assertEqual("UPL-1.0", self.pin["license"]["declared"])
        self.assertTrue(self.pin["upstream_status"]["official_reference_application"])
        self.assertEqual("inventory-only", self.pin["acquisition"]["mode"])
        self.assertFalse(self.pin["acquisition"]["source_vendored"])
        self.assertFalse(self.pin["acquisition"]["upstream_build_executed"])
        self.assertFalse(self.pin["acquisition"]["upstream_runtime_executed"])
        self.assertFalse(list(ESTATE.rglob("*.java")))

    def test_modern_oracle_estate_and_coupling_are_measured(self) -> None:
        estate = self.inventory["estate"]
        self.assertEqual(189, estate["tracked_files"])
        self.assertEqual(70, estate["java_source_units"])
        self.assertEqual(52, estate["main_java_source_units"])
        self.assertEqual(18, estate["test_java_source_units"])
        self.assertEqual(6_711, estate["java_source_lines"])
        self.assertEqual(10, estate["maven_module_count"])
        self.assertEqual(8, estate["runtime_service_module_count"])
        self.assertEqual(10, estate["deployable_unit_count"])
        self.assertEqual(9, estate["sql_files"])
        self.assertEqual(53, self.inventory["api_surface"]["spring_endpoint_annotations"])
        self.assertEqual(9, self.inventory["api_surface"]["jaxrs_endpoint_annotations"])
        self.assertGreater(self.inventory["coupling_signals"]["oracle_coupling"]["files"], 0)
        self.assertGreater(
            self.inventory["coupling_signals"]["lra_distributed_transactions"]["files"], 0
        )
        self.assertGreater(self.inventory["coupling_signals"]["messaging"]["files"], 0)
        self.assertIn("ACCOUNT.ACCOUNTS", self.inventory["database_surface"]["ddl_objects"]["table"])
        self.assertIn(
            '"USER_REPO"."AUDIT_TRG"',
            self.inventory["database_surface"]["ddl_objects"]["trigger"],
        )

    def test_five_selectable_workloads_define_twenty_migration_risks(self) -> None:
        expected = {
            "customer-account-management",
            "money-transfer",
            "check-deposit-clearance",
            "identity-service-authorization",
            "credit-score-service",
        }
        self.assertEqual(expected, {item["id"] for item in self.workloads["workloads"]})
        self.assertTrue(all(len(item["migration_risks"]) == 4 for item in self.workloads["workloads"]))
        self.assertEqual(
            20,
            sum(len(item["migration_risks"]) for item in self.workloads["workloads"]),
        )
        self.assertTrue(all(
            path.startswith("cloudbank-v5/")
            for item in self.workloads["workloads"]
            for path in item["source_paths"]
        ))
        boundary = self.workloads["claim_boundary"]
        self.assertTrue(all(value is False for value in boundary.values()))
        self.assertIn("PostgreSQL", self.workloads["target_posture"]["candidate_lanes"])
        self.assertIsNone(self.workloads["target_posture"]["selected_target"])

    def test_committed_projection_is_deterministic_and_bounded(self) -> None:
        expected = build_cloudbank_reference_fragment(
            self.base, self.workloads, self.inventory, self.pin
        )
        self.assertEqual(expected, self.fragment)
        self.assertEqual([], validate_cloudbank_reference_fragment(
            self.fragment, self.base, self.workloads, self.inventory, self.pin
        ))
        self.assertEqual(OPERATOR_ESTATE_NAME, self.fragment["source"]["operator_estate_name"])
        self.assertEqual(25, self.fragment["statistics"]["node_count"])
        self.assertEqual(20, self.fragment["statistics"]["edge_count"])

    def test_each_curated_risk_becomes_one_static_scenario(self) -> None:
        expected = {
            (workload["id"], sequence, risk["id"])
            for workload in self.workloads["workloads"]
            for sequence, risk in enumerate(workload["migration_risks"], start=1)
        }
        actual = {
            (
                node["properties"]["workload_id"].split(":workload:", 1)[1],
                node["properties"]["sequence"],
                node["properties"]["migration_risk_id"],
            )
            for node in self.fragment["nodes"]
            if node["kind"] == "verification_scenario"
        }
        self.assertEqual(expected, actual)
        for node in self.fragment["nodes"]:
            properties = node["properties"]
            self.assertFalse(properties["runtime_observed"])
            self.assertFalse(properties["postgresql_mapping_complete"])
            self.assertFalse(properties["target_equivalent"])
            self.assertFalse(properties["migration_complete"])
            self.assertFalse(properties["production_ready"])

    def test_full_structural_inventory_is_projected_without_a_committed_graph(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        paths = sorted({
            path.removeprefix("cloudbank-v5/")
            for workload in self.workloads["workloads"]
            for path in workload["source_paths"]
        })
        java_paths = [path for path in paths if path.endswith(".java")]
        self.assertGreaterEqual(len(java_paths), 2)
        inventory["database_surface"]["ddl_declarations"] = []
        inventory["structural_graph"] = {
            "source_files": [
                {
                    "category": "java" if path.endswith(".java") else "other",
                    "extension": Path(path).suffix or "[none]",
                    "module": path.split("/", 1)[0] if "/" in path else "root",
                    "path": path,
                }
                for path in paths
            ],
            "java_types": [
                {
                    "coupling_categories": [],
                    "endpoint_annotations": {"jaxrs": 0, "spring": 0},
                    "module": java_paths[index].split("/", 1)[0],
                    "node": f"example.Type{index}",
                    "package": "example",
                    "path": java_paths[index],
                    "source_set": "main",
                }
                for index in range(2)
            ],
            "dependency_edges": [
                {"source": "example.Type0", "target": "example.Type1"}
            ],
        }

        fragment = build_cloudbank_reference_fragment(
            self.base, self.workloads, inventory, self.pin
        )
        self.assertEqual(
            "Copyright (c) 2021, 2023 Oracle and/or its affiliates.",
            fragment["source"]["license"]["copyright"],
        )
        self.assertEqual(
            "LICENSES/UPL-1.0.txt",
            fragment["source"]["license"]["bundled_license_file"],
        )
        self.assertEqual(len(paths), fragment["statistics"]["nodes_by_kind"]["source_file"])
        self.assertEqual(2, fragment["statistics"]["nodes_by_kind"]["java_type"])
        self.assertEqual(2, fragment["statistics"]["edges_by_relation"]["DECLARES"])
        self.assertEqual(1, fragment["statistics"]["edges_by_relation"]["DEPENDS_ON"])
        self.assertEqual(
            sum(len(item["source_paths"]) for item in self.workloads["workloads"]),
            fragment["statistics"]["edges_by_relation"]["MODERN_ENTRYPOINT"],
        )
        self.assertIn(
            "not distributed in this repository",
            " ".join(fragment["limitations"]),
        )

    def test_inventory_tool_and_record_share_the_same_pin(self) -> None:
        script_path = ROOT / "tools" / "inventory_cloudbank_reference.py"
        spec = importlib.util.spec_from_file_location("cloudbank_inventory", script_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        self.assertEqual(PINNED_COMMIT, module.PINNED_COMMIT)
        self.assertEqual("main", module.PINNED_BRANCH)
        self.assertFalse(
            inspect.signature(module.build_inventory)
            .parameters["include_structural_graph"]
            .default
        )
        self.assertNotIn("structural_graph", self.inventory)

    def test_tampering_and_target_overclaim_fail_closed(self) -> None:
        changed = copy.deepcopy(self.fragment)
        changed["nodes"][0]["properties"]["postgresql_mapping_complete"] = True
        errors = validate_cloudbank_reference_fragment(
            changed, self.base, self.workloads, self.inventory, self.pin
        )
        self.assertTrue(any("not the deterministic projection" in error for error in errors))
        self.assertTrue(any("overstates postgresql_mapping_complete" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
