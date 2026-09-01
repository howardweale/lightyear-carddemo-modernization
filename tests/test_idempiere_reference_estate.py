import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference-estates" / "idempiere"
PINNED_COMMIT = "731515dcdd5278b843db33b9d3109d155b881951"


class IdempiereReferenceEstateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pin = json.loads((REFERENCE / "source-pin.json").read_text(encoding="utf-8"))
        cls.inventory = json.loads((REFERENCE / "inventory.json").read_text(encoding="utf-8"))
        cls.slices = json.loads((REFERENCE / "business-slices.json").read_text(encoding="utf-8"))
        cls.fixtures = json.loads(
            (REFERENCE / "oracle-semantic-fixtures.json").read_text(encoding="utf-8")
        )

    def test_supported_release_is_pinned_without_vendoring_or_execution(self) -> None:
        self.assertEqual(PINNED_COMMIT, self.pin["source"]["commit"])
        self.assertEqual("release-13", self.pin["source"]["branch"])
        self.assertTrue(self.pin["upstream_status"]["supported_release"])
        self.assertEqual("GPL-2.0", self.pin["license"]["declared"])
        self.assertEqual("inventory-only", self.pin["acquisition"]["mode"])
        self.assertFalse(self.pin["acquisition"]["source_vendored"])
        self.assertFalse(self.pin["acquisition"]["upstream_build_executed"])
        self.assertFalse(self.pin["acquisition"]["upstream_runtime_executed"])

    def test_estate_and_static_dependency_graph_are_measured(self) -> None:
        estate = self.inventory["estate"]
        self.assertEqual(12_565, estate["tracked_files"])
        self.assertEqual(4_520, estate["java_source_units"])
        self.assertEqual(1_447_671, estate["java_source_lines"])
        self.assertEqual(36_819, estate["internal_java_dependency_edges"])
        self.assertEqual(214, estate["java_packages"])
        self.assertEqual(5_679, estate["sql_files"])
        self.assertEqual(2_823, estate["oracle_sql_files"])
        self.assertEqual(707, estate["model_interface_source_units"])
        self.assertEqual(706, estate["generated_model_source_units"])
        self.assertEqual(197, estate["process_source_units"])
        self.assertEqual("upstream-static-inventory", self.inventory["claim_class"])

    def test_two_business_slices_keep_their_business_selectors(self) -> None:
        by_id = {item["id"]: item for item in self.slices["slices"]}
        self.assertEqual({"order-to-cash", "procure-to-pay"}, set(by_id))
        for item in by_id.values():
            self.assertEqual(9, item["node_count"])
            self.assertEqual(10, item["edge_count"])
            self.assertEqual(item["edge_count"], len(item["edges"]))
            self.assertEqual(item["node_count"], len(item["tables"]))
        self.assertEqual("Y", by_id["order-to-cash"]["selectors"]["C_Order.IsSOTrx"])
        self.assertEqual("Y", by_id["order-to-cash"]["selectors"]["C_Payment.IsReceipt"])
        self.assertEqual("N", by_id["procure-to-pay"]["selectors"]["C_Order.IsSOTrx"])
        self.assertEqual("N", by_id["procure-to-pay"]["selectors"]["C_Payment.IsReceipt"])

        graphs = self.inventory["slices"]
        self.assertEqual(181, graphs["order-to-cash"]["nodes"])
        self.assertEqual(497, graphs["order-to-cash"]["edges"])
        self.assertEqual(177, graphs["procure-to-pay"]["nodes"])
        self.assertEqual(475, graphs["procure-to-pay"]["edges"])
        self.assertEqual(10, self.inventory["shared_slice_seed_nodes"])

    def test_first_oracle_fixtures_are_identified_but_not_overclaimed(self) -> None:
        fixtures = self.fixtures["fixtures"]
        self.assertEqual(8, len(fixtures))
        self.assertEqual(list(range(1, 9)), [item["priority"] for item in fixtures])
        self.assertTrue(all(item["status"] == "identified" for item in fixtures))
        self.assertTrue(all(item["source_paths"] for item in fixtures))
        self.assertEqual("upstream-static", self.fixtures["evidence_class"])
        self.assertFalse(self.fixtures["native_oracle_executed"])
        self.assertEqual(
            "identified-not-acquired", self.fixtures["corpus_policy"]["status"]
        )
        self.assertEqual(
            "https://github.com/oracle-samples/db-sample-schemas",
            self.fixtures["corpus_policy"]["official_oracle_corpus"],
        )

    def test_inventory_tool_and_record_share_the_same_pin(self) -> None:
        script_path = ROOT / "tools" / "inventory_idempiere_reference.py"
        spec = importlib.util.spec_from_file_location("idempiere_inventory", script_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        self.assertEqual(PINNED_COMMIT, module.PINNED_COMMIT)

    def test_upstream_source_is_not_vendored_and_boundaries_are_explicit(self) -> None:
        self.assertFalse(list(REFERENCE.rglob("*.java")))
        readme = (REFERENCE / "README.md").read_text(encoding="utf-8").lower()
        normalized = " ".join(readme.split())
        self.assertIn("not customer source", readme)
        self.assertIn("oracle runtime evidence", readme)
        self.assertIn("translated code", readme)
        self.assertIn("behavioral equivalence", readme)
        self.assertIn("production readiness", readme)
        self.assertIn("cloudbank remains the intended modern destination", readme)
        self.assertIn("sap ase reference estate remains separately bounded", normalized)


if __name__ == "__main__":
    unittest.main()
