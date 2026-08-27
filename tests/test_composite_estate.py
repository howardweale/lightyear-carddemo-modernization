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
CAPABILITIES = ROOT / "knowledge" / "capabilities" / "mainframe-readiness.json"


class CompositeEstateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = load_graph(BASE)
        cls.composite = load_graph(COMPOSITE)
        cls.fragment = json.loads(FRAGMENT.read_text(encoding="utf-8"))
        cls.capabilities = json.loads(CAPABILITIES.read_text(encoding="utf-8"))

    def test_committed_projection_is_deterministic_and_preserves_truth_boundary(self) -> None:
        built = build_composite_estate(self.base, [self.fragment], self.capabilities)
        self.assertEqual(self.composite, built)
        self.assertEqual([], validate_composite_estate(
            self.composite, self.base, [self.fragment], self.capabilities
        ))
        self.assertEqual(self.base["content_sha256"], self.composite["base_graph"]["content_sha256"])
        self.assertNotEqual(self.base["content_sha256"], self.composite["content_sha256"])
        self.assertFalse(self.composite["claim_boundary"]["mainframe_equivalent"])
        self.assertFalse(self.composite["claim_boundary"]["production_ready"])

    def test_explorer_navigates_pli_to_cobol_and_db2(self) -> None:
        index = GraphExplorerIndex(self.composite)
        self.assertEqual(7, len(index.perspectives()))
        self.assertEqual(self.base["content_sha256"], index.canonical_content_sha256)
        pli = "extension:pli-program:ACCTPL1"
        cobol = "legacy:cobol-program:CBACT04C"
        table = "legacy:db2-table:CARDDEMO.AUTHFRDS"
        self.assertIsNotNone(index.trace(pli, cobol))
        self.assertIsNotNone(index.trace(pli, table))
        self.assertEqual("pli_program", index.node(pli)["kind"])
        self.assertTrue(
            any(
                item["technology"] == "PL/I"
                for item in index.metadata()["capability_projection"]["capabilities"]
            )
        )

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
            projection, self.base, [self.fragment], self.capabilities
        )
        self.assertTrue(any("mainframe_equivalent" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
