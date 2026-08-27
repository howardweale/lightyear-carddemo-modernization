from __future__ import annotations

import importlib.util
import copy
import json
import sys
import unittest
from pathlib import Path

from lightyear_factory.asm_private import policy_checks
from lightyear_knowledge_graph.capability import analyze_capabilities, validate_capability_analysis
from lightyear_knowledge_graph.model import load_graph
from lightyear_knowledge_graph.query import shortest_trace
from lightyear_readiness.asm import (
    compare_captures,
    issue_receipt,
    local_capture,
    sign_capture,
    validate_capture,
    validate_receipt,
)


ROOT = Path(__file__).resolve().parents[1]


def candidate() -> object:
    path = ROOT / "factory/benchmarks/asm_date_candidate.py"
    spec = importlib.util.spec_from_file_location("test_asm_date_candidate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MainframeCapabilityGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_graph(ROOT / "knowledge/graph.snapshot.json.gz")
        cls.nodes = {node["id"]: node for node in cls.graph["nodes"]}

    @staticmethod
    def load_json(relative: str) -> dict:
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def expected_projection(self, **overrides: dict) -> dict:
        evidence = {
            "cics_vsam_receipt": self.load_json("readiness/cics-vsam/readiness-receipt.json"),
            "asm_receipt": self.load_json("readiness/asm-date/readiness-receipt.json"),
            "ims_receipt": self.load_json("readiness/ims-expiry/readiness-receipt.json"),
            "pli_fragment": self.load_json("extensions/pli/pli.fragment.json"),
            "extension_catalog": self.load_json("extensions/catalog.json"),
            "pli_coverage_receipt": self.load_json("extensions/pli/conformance/coverage.receipt.json"),
            "pli_development_receipt": self.load_json("extensions/pli/modernization/development.receipt.json"),
            "postgres_data_receipt": self.load_json("data-modernization/receipts/authfrds.offline.receipt.json"),
            "oracle_data_receipt": self.load_json("data-modernization/receipts/authfrds.oracle-offline.receipt.json"),
            "campaign_receipt": self.load_json("extensions/adapters/campaign/campaign.receipt.json"),
        }
        evidence.update(overrides)
        return analyze_capabilities(self.graph, **evidence)

    def test_hlasm_assets_are_typed_and_connected(self) -> None:
        stats = self.graph["statistics"]["nodes_by_kind"]
        self.assertEqual(2, stats["assembler_program"])
        self.assertGreaterEqual(stats["assembler_instruction"], 40)
        self.assertEqual(1, stats["assembler_dsect"])
        self.assertEqual(5, stats["assembler_field"])
        self.assertEqual(1, stats["assembler_macro"])
        self.assertIsNotNone(
            shortest_trace(
                self.graph,
                "legacy:cobol-paragraph:CBACT01C:1300-POPUL-ACCT-RECORD",
                "legacy:assembler-program:COBDATFT",
            )
        )
        self.assertIsNotNone(
            shortest_trace(
                self.graph,
                "legacy:assembler-program:COBDATFT",
                "legacy:assembler-dsect:COCDATFT",
            )
        )
        self.assertIsNotNone(
            shortest_trace(
                self.graph,
                "legacy:assembler-program:MVSWAIT",
                "legacy:assembler-macro:ASMWAIT",
            )
        )

    def test_ims_assets_are_typed_and_connected(self) -> None:
        stats = self.graph["statistics"]["nodes_by_kind"]
        self.assertEqual(4, stats["ims_database"])
        self.assertEqual(4, stats["ims_psb"])
        self.assertEqual(6, stats["ims_pcb"])
        self.assertGreaterEqual(stats["ims_segment"], 3)
        db = self.nodes["legacy:ims-database:DBPAUTP0"]
        self.assertEqual("HIDAM", db["properties"]["access_method"])
        pcb = self.nodes["legacy:ims-pcb:PSBPAUTB:PAUTBPCB"]
        self.assertEqual("AP", pcb["properties"]["PROCOPT"])
        self.assertIsNotNone(
            shortest_trace(
                self.graph,
                "legacy:cobol-program:CBPAUP0C",
                "legacy:ims-segment:DBPAUTP0:PAUTDTL1",
            )
        )

    def test_capability_projection_is_graph_bound_and_fail_closed(self) -> None:
        analysis = json.loads(
            (ROOT / "knowledge/capabilities/mainframe-readiness.json").read_text(encoding="utf-8")
        )
        expected = self.expected_projection()
        self.assertEqual([], validate_capability_analysis(analysis, self.graph, expected))
        by_name = {item["technology"]: item for item in analysis["capabilities"]}
        self.assertTrue(by_name["CICS"]["development_ready"])
        self.assertTrue(by_name["VSAM"]["development_ready"])
        self.assertTrue(by_name["HLASM"]["development_ready"])
        self.assertTrue(by_name["IMS"]["development_ready"])
        self.assertTrue(by_name["PL/I"]["discovery_ready"])
        self.assertTrue(by_name["PL/I"]["development_ready"])
        self.assertTrue(by_name["Db2/Data"]["development_ready"])
        self.assertTrue(all(not item["mainframe_equivalent"] for item in by_name.values()))
        self.assertEqual("language", by_name["PL/I"]["capability_kind"])
        self.assertEqual("data", by_name["Db2/Data"]["capability_kind"])
        self.assertEqual("blocked", by_name["HLASM"]["gates"][5]["status"])
        self.assertEqual("mechanism_ready", by_name["IMS"]["gates"][6]["status"])
        self.assertEqual("mechanism_ready", by_name["PL/I"]["gates"][6]["status"])
        self.assertEqual(27, by_name["PL/I"]["breadth"]["corpus_case_count"])
        self.assertEqual(22, by_name["PL/I"]["breadth"]["supported_construct_count"])
        self.assertFalse(by_name["PL/I"]["breadth"]["customer_source"])
        self.assertFalse(by_name["PL/I"]["breadth"]["runtime_evidence"])
        campaign = analysis["collection_mechanisms"][0]
        self.assertEqual("simulated_ready", campaign["status"])
        self.assertEqual("simulated", campaign["evidence_class"])
        self.assertFalse(campaign["live_observed"])
        self.assertFalse(campaign["production_ready"])

    def test_invalid_pli_fragment_fails_closed_without_weakening_other_cells(self) -> None:
        fragment = self.load_json("extensions/pli/pli.fragment.json")
        fragment["statistics"]["edges_by_relation"]["CALLS"] = 1
        analysis = self.expected_projection(pli_fragment=fragment)
        by_name = {item["technology"]: item for item in analysis["capabilities"]}
        self.assertFalse(by_name["PL/I"]["discovery_ready"])
        self.assertFalse(by_name["PL/I"]["development_ready"])
        self.assertTrue(by_name["Db2/Data"]["development_ready"])

    def test_tampered_pli_development_receipt_fails_closed(self) -> None:
        receipt = self.load_json("extensions/pli/modernization/development.receipt.json")
        receipt["checks"]["mutation_and_negative_verification"] = False
        analysis = self.expected_projection(pli_development_receipt=receipt)
        pli = next(item for item in analysis["capabilities"] if item["technology"] == "PL/I")
        self.assertTrue(pli["discovery_ready"])
        self.assertFalse(pli["development_ready"])
        self.assertFalse(pli["mainframe_equivalent"])

    def test_missing_or_tampered_pli_coverage_demotes_discovery(self) -> None:
        missing = self.expected_projection(pli_coverage_receipt={})
        pli = next(item for item in missing["capabilities"] if item["technology"] == "PL/I")
        self.assertFalse(pli["discovery_ready"])
        self.assertFalse(pli["development_ready"])
        receipt = self.load_json("extensions/pli/conformance/coverage.receipt.json")
        receipt["corpus"]["case_count"] = 1
        tampered = self.expected_projection(pli_coverage_receipt=receipt)
        pli = next(item for item in tampered["capabilities"] if item["technology"] == "PL/I")
        self.assertFalse(pli["discovery_ready"])

    def test_stale_projection_is_rejected_when_bound_evidence_changes(self) -> None:
        analysis = self.expected_projection()
        changed_campaign = self.load_json("extensions/adapters/campaign/campaign.receipt.json")
        changed_campaign["required_adapters"] = changed_campaign["required_adapters"][:-1]
        expected = self.expected_projection(campaign_receipt=changed_campaign)
        errors = validate_capability_analysis(analysis, self.graph, expected)
        self.assertIn(
            "capability analysis is stale against bound extension, data, or campaign evidence",
            errors,
        )


class AssemblerBehaviorTests(unittest.TestCase):
    def test_source_faithful_candidate_passes_private_policy(self) -> None:
        checks = policy_checks(candidate())
        self.assertTrue(all(checks.values()), checks)

    def test_mutated_contracts_are_rejected(self) -> None:
        mutations = {
            "PROGRAM_ID": "MVSWAIT",
            "INPUT_DATE_LENGTH": 19,
            "OUTPUT_DATE_LENGTH": 21,
            "ERROR_LENGTH": 37,
            "INPUT_COMPACT": "2",
            "INPUT_HYPHENATED": "1",
            "OUTPUT_HYPHENATED": "2",
            "OUTPUT_COMPACT": "1",
            "INVALID_INPUT": "INVALID DATE",
        }
        for attribute, bad_value in mutations.items():
            with self.subTest(attribute=attribute):
                changed = candidate()
                setattr(changed, attribute, bad_value)
                self.assertFalse(all(policy_checks(changed).values()))


class AssemblerReadinessTests(unittest.TestCase):
    def test_local_proof_is_development_ready_and_equivalence_blocked(self) -> None:
        capture = local_capture(ROOT)
        self.assertEqual([], validate_capture(capture))
        comparison = compare_captures(capture, capture)
        receipt = issue_receipt(comparison)
        self.assertTrue(receipt["development_ready"])
        self.assertFalse(receipt["mainframe_equivalent"])
        self.assertEqual("blocked", receipt["status"])
        self.assertEqual([], validate_receipt(receipt))

    def test_independently_signed_live_match_can_pass(self) -> None:
        candidate_capture = local_capture(ROOT)
        live = copy.deepcopy(candidate_capture)
        live.update(
            {
                "run_id": "authorized-cobdatft-live-001",
                "source_system": "customer-zos-test",
                "evidence_class": "zos_observed",
                "artifacts": [
                    {"role": role, "sha256": character * 64}
                    for role, character in (
                        ("assembly-listing", "1"),
                        ("binder-map", "2"),
                        ("load-module", "3"),
                        ("cobol-caller-output", "4"),
                    )
                ],
                "mainframe_identity": {
                    "system_id": "SYSA",
                    "lpar": "LPAR1",
                    "job_id": "JOB01234",
                    "step_name": "RUNASM",
                    "load_module": "COBDATFT",
                    "caller_program": "CBACT01C",
                    "operator": "authorized-evidence-custodian",
                },
                "operator_attestation": {"authorized": True, "ticket": "TEST-ASM-001"},
            }
        )
        live = sign_capture(live, "asm-attestation-key", "custodian")
        self.assertEqual([], validate_capture(live, "asm-attestation-key"))
        comparison = compare_captures(live, candidate_capture, "asm-attestation-key")
        receipt = issue_receipt(comparison, "asm-equivalence-key", "independent-verifier")
        self.assertTrue(receipt["mainframe_equivalent"])
        self.assertEqual([], validate_receipt(receipt, "asm-equivalence-key"))


if __name__ == "__main__":
    unittest.main()
