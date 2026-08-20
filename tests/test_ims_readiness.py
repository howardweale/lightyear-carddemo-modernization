from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

from lightyear_factory.ims_private import policy_checks
from lightyear_knowledge_graph.model import load_graph
from lightyear_knowledge_graph.query import shortest_trace
from lightyear_readiness.cics_vsam import canonical_hash
from lightyear_readiness.ims import (
    compare_captures,
    issue_receipt,
    local_capture,
    sign_capture,
    validate_capture,
    validate_receipt,
)


ROOT = Path(__file__).resolve().parents[1]


def candidate() -> object:
    path = ROOT / "factory/benchmarks/ims_expiry_candidate.py"
    spec = importlib.util.spec_from_file_location("test_ims_expiry_candidate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ImsGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_graph(ROOT / "knowledge/graph.snapshot.json.gz")
        cls.nodes = {node["id"]: node for node in cls.graph["nodes"]}

    def test_bounded_bmp_cell_is_connected(self) -> None:
        self.assertIn("workload:carddemo-ims-expired-authorization-purge", self.nodes)
        rules = [
            node for node in self.graph["nodes"]
            if node["kind"] == "business_rule" and node["id"].startswith("rule:ims-expiry:")
        ]
        self.assertEqual(8, len(rules))
        self.assertIsNotNone(
            shortest_trace(
                self.graph,
                "workload:carddemo-ims-expired-authorization-purge",
                "legacy:ims-segment:DBPAUTP0:PAUTDTL1",
            )
        )
        self.assertIsNotNone(
            shortest_trace(
                self.graph,
                "rule:ims-expiry:duplicate-approved-root-test",
                "legacy:cobol-paragraph:CBPAUP0C:6000-DELETE-AUTH-SUMMARY",
            )
        )


class ImsBehaviorTests(unittest.TestCase):
    def test_source_faithful_candidate_passes_private_policy(self) -> None:
        checks = policy_checks(candidate())
        self.assertTrue(all(checks.values()), checks)

    def test_mutated_contracts_are_rejected(self) -> None:
        mutations = {
            "PROGRAM_ID": "PAUDBUNL",
            "PSB_NAME": "PSBPAUTL",
            "DATABASE_NAME": "DBPAUTX0",
            "PCB_NAME": "WRONGPCB",
            "PCB_NUMBER": 1,
            "PROCOPT": "G",
            "ROOT_SEGMENT": "PAUTDTL1",
            "DETAIL_SEGMENT": "PAUTSUM0",
            "SUMMARY_DELETE_POLICY": "approved-and-declined",
        }
        for attribute, bad_value in mutations.items():
            with self.subTest(attribute=attribute):
                changed = candidate()
                setattr(changed, attribute, bad_value)
                self.assertFalse(all(policy_checks(changed).values()))

    def test_input_is_not_mutated_and_boundary_is_inclusive(self) -> None:
        module = candidate()
        summaries = [
            {
                "account_id": "1",
                "approved_count": 2,
                "declined_count": 0,
                "approved_amount": "20.00",
                "declined_amount": "0.00",
                "details": [
                    {"authorization_id": "boundary", "inverted_auth_date": 79823, "response_code": "00", "approved_amount": "5.00", "transaction_amount": "5.00"},
                    {"authorization_id": "newer", "inverted_auth_date": 79822, "response_code": "00", "approved_amount": "5.00", "transaction_amount": "5.00"},
                ],
            }
        ]
        before = copy.deepcopy(summaries)
        result = module.purge_expired_authorizations(summaries, current_yyddd=20181, expiry_days="05")
        self.assertEqual(before, summaries)
        self.assertEqual([{"account_id": "1", "authorization_id": "boundary"}], result["deleted_details"])


class ImsReadinessTests(unittest.TestCase):
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
                "run_id": "authorized-cbpaup0c-live-001",
                "source_system": "customer-zos-test",
                "evidence_class": "zos_observed",
                "artifacts": [
                    {"role": role, "sha256": character * 64}
                    for role, character in (
                        ("jcl", "1"),
                        ("load-module", "2"),
                        ("psb", "3"),
                        ("dbd", "4"),
                        ("synthetic-before-image", "5"),
                        ("synthetic-after-image", "6"),
                        ("job-output", "7"),
                        ("ims-log-or-trace", "8"),
                    )
                ],
                "mainframe_identity": {
                    "system_id": "SYSA",
                    "lpar": "LPAR1",
                    "ims_region": "IMST01",
                    "job_id": "JOB01234",
                    "step_name": "STEP01",
                    "program": "CBPAUP0C",
                    "psb": "PSBPAUTB",
                    "database": "DBPAUTP0",
                    "operator": "authorized-evidence-custodian",
                },
                "operator_attestation": {"authorized": True, "ticket": "TEST-IMS-001"},
            }
        )
        live = sign_capture(live, "ims-attestation-key", "custodian")
        self.assertEqual([], validate_capture(live, "ims-attestation-key"))
        comparison = compare_captures(live, candidate_capture, "ims-attestation-key")
        receipt = issue_receipt(comparison, "ims-equivalence-key", "independent-verifier")
        self.assertTrue(receipt["mainframe_equivalent"])
        self.assertEqual([], validate_receipt(receipt, "ims-equivalence-key"))

    def test_tampering_and_incomplete_live_identity_fail_closed(self) -> None:
        capture = local_capture(ROOT)
        capture["output"]["totals"]["details_deleted"] = 99
        self.assertIn("IMS capture content_sha256 is invalid", validate_capture(capture))
        incomplete = local_capture(ROOT)
        incomplete["evidence_class"] = "zos_observed"
        incomplete["content_sha256"] = canonical_hash(incomplete, {"content_sha256"})
        errors = validate_capture(incomplete)
        self.assertTrue(any("mainframe_identity.ims_region" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
