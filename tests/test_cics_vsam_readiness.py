from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

from lightyear_factory.cics_vsam_private import policy_checks
from lightyear_knowledge_graph.model import load_graph
from lightyear_knowledge_graph.query import shortest_trace
from lightyear_readiness.cics_vsam import (
    canonical_hash,
    compare_captures,
    issue_receipt,
    local_capture,
    sign_capture,
    validate_capture,
    validate_receipt,
)


ROOT = Path(__file__).resolve().parents[1]


def candidate() -> object:
    path = ROOT / "factory/benchmarks/cics_vsam_account_candidate.py"
    spec = importlib.util.spec_from_file_location("test_cics_vsam_candidate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CicsVsamGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_graph(ROOT / "knowledge/graph.snapshot.json.gz")
        cls.nodes = {node["id"]: node for node in cls.graph["nodes"]}

    def test_native_assets_are_typed_and_connected(self) -> None:
        self.assertEqual("cics_transaction", self.nodes["legacy:cics-transaction:CAVW"]["kind"])
        self.assertEqual("bms_map", self.nodes["legacy:bms-map:CACTVWA"]["kind"])
        field = self.nodes["legacy:bms-field:CACTVWA:ACCTSID:84"]
        self.assertEqual("11", field["properties"]["LENGTH"])
        self.assertEqual("(5,38)", field["properties"]["POS"])
        cluster = self.nodes["legacy:vsam-cluster:AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS"]
        self.assertEqual("KSDS", cluster["properties"]["organization"])
        self.assertEqual(11, cluster["properties"]["key_length"])
        self.assertEqual(
            "ESDS",
            self.nodes["legacy:vsam-cluster:AWS.M2.CARDDEMO.USRSEC.VSAM.ESDS"]["properties"]["organization"],
        )
        self.assertEqual(
            "RRDS",
            self.nodes["legacy:vsam-cluster:AWS.M2.CARDDEMO.USRSEC.VSAM.RRDS"]["properties"]["organization"],
        )
        self.assertIsNotNone(
            shortest_trace(
                self.graph,
                "legacy:cics-transaction:CAVW",
                "legacy:cobol-program:COACTVWC",
            )
        )
        self.assertIsNotNone(
            shortest_trace(
                self.graph,
                "legacy:cics-command:COACTVWC:727:6",
                "legacy:vsam-cluster:AWS.M2.CARDDEMO.CARDXREF.VSAM.KSDS",
            )
        )

    def test_curated_vertical_slice_is_policy_complete(self) -> None:
        self.assertEqual(34, self.graph["statistics"]["nodes_by_kind"]["business_rule"])
        self.assertIn("workload:carddemo-cics-vsam-account-view", self.nodes)
        rules = [
            node for node in self.graph["nodes"]
            if node["kind"] == "business_rule" and node["id"].startswith("rule:cics-vsam:")
        ]
        self.assertEqual(8, len(rules))


class CicsVsamBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = candidate()

    def test_private_gate_and_negative_paths(self) -> None:
        self.assertTrue(all(policy_checks(self.candidate)))
        invalid = self.candidate.account_view(
            "BAD",
            self.candidate.KeyedStore("CXACAIX", {}),
            self.candidate.KeyedStore("ACCTDAT", {}),
            self.candidate.KeyedStore("CUSTDAT", {}),
        )
        self.assertEqual("INVALID_ACCOUNT", invalid["status"])
        self.assertEqual([], invalid["mutations"])

    def test_mutation_matrix_is_rejected(self) -> None:
        mutations = {
            "TRANSACTION_ID": "CAUP",
            "PROGRAM_ID": "COACTUPC",
            "MAPSET": "COACTUP",
            "MAP": "CACTUPA",
            "ACCOUNT_INPUT_LENGTH": 10,
            "XREF_ACCOUNT_KEY_LENGTH": 10,
            "XREF_ACCOUNT_KEY_OFFSET": 24,
            "ACCOUNT_KEY_LENGTH": 10,
            "CUSTOMER_KEY_LENGTH": 8,
            "READ_ONLY": False,
        }
        for attribute, bad_value in mutations.items():
            with self.subTest(attribute=attribute):
                changed = candidate()
                setattr(changed, attribute, bad_value)
                self.assertFalse(all(policy_checks(changed)))


class CicsVsamReceiptTests(unittest.TestCase):
    def test_local_proof_is_ready_but_not_mainframe_equivalent(self) -> None:
        capture = local_capture(ROOT)
        self.assertEqual([], validate_capture(capture))
        comparison = compare_captures(capture, capture)
        receipt = issue_receipt(comparison)
        self.assertTrue(receipt["development_ready"])
        self.assertFalse(receipt["mainframe_equivalent"])
        self.assertEqual("blocked", receipt["status"])
        self.assertEqual([], validate_receipt(receipt))

    def test_signed_live_match_can_issue_equivalence(self) -> None:
        candidate_capture = local_capture(ROOT)
        live = copy.deepcopy(candidate_capture)
        live.update(
            {
                "run_id": "authorized-cavw-live-001",
                "source_system": "customer-zos-test",
                "evidence_class": "zos_observed",
                "mainframe_identity": {
                    "system_id": "SYSA",
                    "lpar": "LPAR1",
                    "cics_region": "CICST01",
                    "task_id": "0048123",
                    "operator": "authorized-evidence-custodian",
                },
                "operator_attestation": {"authorized": True, "ticket": "TEST-001"},
            }
        )
        live = sign_capture(live, "unit-test-attestation-key", "test-custodian")
        self.assertEqual([], validate_capture(live, "unit-test-attestation-key"))
        comparison = compare_captures(live, candidate_capture, "unit-test-attestation-key")
        receipt = issue_receipt(comparison, signing_key="unit-test-external-key", signing_key_id="test-key")
        self.assertTrue(receipt["mainframe_equivalent"])
        self.assertEqual("passed", receipt["status"])
        self.assertEqual([], validate_receipt(receipt, "unit-test-external-key"))

    def test_tampering_and_incomplete_live_identity_fail_closed(self) -> None:
        capture = local_capture(ROOT)
        capture["output"]["view"]["credit_limit"] = "999999.00"
        self.assertIn("capture content_sha256 is invalid", validate_capture(capture))
        incomplete = local_capture(ROOT)
        incomplete["evidence_class"] = "zos_observed"
        incomplete["content_sha256"] = canonical_hash(incomplete, {"content_sha256"})
        errors = validate_capture(incomplete)
        self.assertTrue(any("mainframe_identity.cics_region" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
