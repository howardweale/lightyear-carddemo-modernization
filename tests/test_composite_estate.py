from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_knowledge_graph.composite import (
    build_composite_estate,
    validate_composite_estate,
    validate_fragment_binding,
)
from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "knowledge" / "graph.snapshot.json.gz"
COMPOSITE = ROOT / "knowledge" / "composite" / "estate.snapshot.json.gz"
FRAGMENT = ROOT / "extensions" / "pli" / "pli.fragment.json"
ORACLE_FRAGMENT = ROOT / "reference-estates" / "idempiere" / "oracle-customer-large.fragment.json"
CLOUDBANK_FRAGMENT = ROOT / "reference-estates" / "cloudbank" / "cloudbank-reference.fragment.json"
CAPABILITIES = ROOT / "knowledge" / "capabilities" / "mainframe-readiness.json"


class CompositeEstateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = load_graph(BASE)
        cls.composite = load_graph(COMPOSITE)
        cls.fragment = json.loads(FRAGMENT.read_text(encoding="utf-8"))
        cls.oracle_fragment = json.loads(ORACLE_FRAGMENT.read_text(encoding="utf-8"))
        cls.cloudbank_fragment = json.loads(CLOUDBANK_FRAGMENT.read_text(encoding="utf-8"))
        cls.fragments = [cls.fragment, cls.oracle_fragment, cls.cloudbank_fragment]
        cls.capabilities = json.loads(CAPABILITIES.read_text(encoding="utf-8"))

    def test_committed_projection_is_deterministic_and_preserves_truth_boundary(self) -> None:
        built = build_composite_estate(self.base, self.fragments, self.capabilities)
        self.assertEqual(self.composite, built)
        self.assertEqual([], validate_composite_estate(
            self.composite, self.base, self.fragments, self.capabilities
        ))
        self.assertEqual(self.base["content_sha256"], self.composite["base_graph"]["content_sha256"])
        self.assertNotEqual(self.base["content_sha256"], self.composite["content_sha256"])
        self.assertFalse(self.composite["claim_boundary"]["mainframe_equivalent"])
        self.assertFalse(self.composite["claim_boundary"]["production_ready"])

    def test_explorer_navigates_pli_to_cobol_and_db2(self) -> None:
        index = GraphExplorerIndex(self.composite)
        self.assertEqual(17, len(index.perspectives()))
        self.assertEqual(self.base["content_sha256"], index.canonical_content_sha256)
        pli = "extension:pli-program:ACCTPL1"
        cobol = "legacy:cobol-program:CBACT04C"
        table = "legacy:db2-table:CARDDEMO.AUTHFRDS"
        self.assertIsNotNone(index.trace(pli, cobol))
        self.assertIsNotNone(index.trace(pli, table))
        self.assertEqual("pli_program", index.node(pli)["kind"])
        directed = index.trace(pli, table, direction="directed")
        self.assertEqual(["PL/I", "DB2"], directed["platforms"])
        self.assertEqual(["ISSUES_SQL", "READS_TABLE"], [
            edge["relation"] for edge in directed["edges"]
        ])
        self.assertFalse(any(
            node["operator_platform"] in {"Oracle", "SAP ASE"}
            for node in directed["nodes"]
        ))
        self.assertIn(
            "pli-db2-read",
            {item["id"] for item in index.operator_context()["trace"]["examples"]},
        )
        write = index.trace(
            "extension:pli-program:AUTHUPD1", table, direction="directed"
        )
        self.assertEqual(["ISSUES_SQL", "WRITES_TABLE"], [
            edge["relation"] for edge in write["edges"]
        ])
        self.assertEqual("static-reference-fixture", write["evidence_class"])
        self.assertFalse(write["customer_evidence"])
        self.assertIn(
            "pli-db2-write-reference",
            {item["id"] for item in index.operator_context()["trace"]["examples"]},
        )
        self.assertTrue(
            any(
                item["technology"] == "PL/I"
                for item in index.metadata()["capability_projection"]["capabilities"]
            )
        )

    def test_explorer_projects_oracle_customer_large_without_runtime_overclaim(self) -> None:
        index = GraphExplorerIndex(self.composite)
        context = index.operator_context()
        self.assertEqual(
            [
                "CardDemo Reference Estate",
                "Oracle Customer (Large)",
                "CloudBank Reference Estate",
            ],
            [item["name"] for item in context["companies"]],
        )
        oracle = next(item for item in context["platforms"] if item["name"] == "Oracle")
        self.assertEqual("projected", oracle["status"])
        self.assertEqual(47, oracle["node_count"])
        workload = "oracle-reference:workload:order-to-cash"
        scenario = "oracle-reference:scenario:order-to-cash:01"
        trace = index.trace(workload, scenario, direction="directed")
        self.assertEqual(["HAS_SCENARIO"], [edge["relation"] for edge in trace["edges"]])
        self.assertEqual(["Oracle"], trace["platforms"])
        self.assertEqual("upstream-static-reference", trace["evidence_class"])
        self.assertIn("not customer evidence", trace["limitation"])
        self.assertFalse(index.node(workload)["properties"]["runtime_observed"])
        self.assertIn(
            "no customer system or Oracle runtime is attached",
            " ".join(context["trace"]["limitations"]),
        )

    def test_explorer_projects_cloudbank_as_a_third_selectable_estate(self) -> None:
        index = GraphExplorerIndex(self.composite)
        context = index.operator_context()
        cloudbank = next(
            item for item in context["companies"]
            if item["id"] == "cloudbank-reference"
        )
        self.assertEqual("CloudBank Reference Estate", cloudbank["name"])
        problems = {
            item["id"] for item in context["problems"]
            if item["company_id"] == "cloudbank-reference"
        }
        self.assertEqual({
            "cloudbank-customer-account",
            "cloudbank-money-movement",
            "cloudbank-check-processing",
            "cloudbank-identity-access",
            "cloudbank-credit-decision",
        }, problems)
        workload = "cloudbank-reference:workload:money-transfer"
        scenario = "cloudbank-reference:scenario:money-transfer:01"
        trace = index.trace(workload, scenario, direction="directed")
        self.assertEqual(["HAS_SCENARIO"], [edge["relation"] for edge in trace["edges"]])
        self.assertEqual(["Oracle"], trace["platforms"])
        self.assertEqual(
            "upstream-static-modern-oracle-reference", trace["evidence_class"]
        )
        self.assertIn("does not prove PostgreSQL mapping", trace["limitation"])
        properties = index.node(workload)["properties"]
        self.assertFalse(properties["runtime_observed"])
        self.assertFalse(properties["postgresql_mapping_complete"])
        self.assertFalse(properties["target_equivalent"])

    def test_runtime_and_audit_remain_bound_to_canonical_identity(self) -> None:
        index = GraphExplorerIndex(self.composite)
        server = ExplorerServer(("127.0.0.1", 0), index, ROOT / "knowledge" / "viewer")
        try:
            self.assertEqual(
                self.base["content_sha256"], server.index.canonical_content_sha256
            )
        finally:
            server.server_close()

    def test_fragment_and_projection_tampering_fail_closed(self) -> None:
        fragment = copy.deepcopy(self.fragment)
        fragment["base_graph"]["content_sha256"] = "0" * 64
        errors = validate_fragment_binding(fragment, self.base)
        self.assertIn("fragment targets a different graph content identity", errors)

        projection = copy.deepcopy(self.composite)
        projection["claim_boundary"]["mainframe_equivalent"] = True
        errors = validate_composite_estate(
            projection, self.base, self.fragments, self.capabilities
        )
        self.assertTrue(any("mainframe_equivalent" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
