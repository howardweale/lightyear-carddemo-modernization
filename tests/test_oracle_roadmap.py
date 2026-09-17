from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lightyear_common.evidence import evidence_floor
from lightyear_data.contracts import seal, sign
from lightyear_data.coverage_reporting import coverage_statement
from lightyear_data.oracle_number_native import (
    EXPECTED, IDENTITY, MARKER, number_cases, observed_results, parse_observations,
    probes, run, verify_harnesses,
)
from lightyear_data.oracle_native_gate import build_native_case_manifest, validate_native_execution_receipt
from lightyear_data.live import aggregate_receipts
from lightyear_data.idempiere_comparison import compare_pair
from lightyear_runtime.contracts import CaptureBundle
from lightyear_runtime.engine import _projection
from lightyear_workflow.policy import default_policy
from lightyear_workflow.planner import comparison_register, measure_proposals, plan_pair

ROOT = Path(__file__).resolve().parents[1]


class CoverageReportingTests(unittest.TestCase):
    def test_foundation_complete_and_partial_counts_are_scoped(self):
        for bounded, native in ((8, 0), (500, 0), (500, 5)):
            statement = coverage_statement({"catalogued_behavior_count": 500,
                "bounded_model_verified_behavior_count": bounded, "native_oracle_verified_behavior_count": native})
            self.assertIn(f"{bounded}/500 bounded-model verified", statement)
            self.assertIn(f"{native}/500 native-Oracle verified", statement)
            self.assertIn("exclude separate application-level evidence such as CloudBank", statement)

    def test_unknown_counts_are_not_zero_and_overclaims_are_rejected(self):
        base = {"catalogued_behavior_count": 500, "bounded_model_verified_behavior_count": 500,
                "native_oracle_verified_behavior_count": 0}
        for value in (None, True, -1, 501, "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                coverage_statement({**base, "native_oracle_verified_behavior_count": value})
        with self.assertRaises(KeyError):
            coverage_statement({})


class NumberPilotTests(unittest.TestCase):
    def test_harnesses_are_exact_and_not_native_evidence(self):
        verify_harnesses(ROOT)
        manifest = build_native_case_manifest(ROOT)
        self.assertEqual(40, manifest["materialized_harness_count"])
        self.assertEqual(0, manifest["native_executed_case_count"])
        self.assertFalse(manifest["native_oracle_conformance"])

    def stdout(self, version="19.25.0.0.0", banner="Oracle Database 19c"):
        # Deliberately synthetic SQL-client fixture, never saved as observed evidence.
        identity = {"version_full": version, "banner": banner, "dbid": "12345",
                    "container_name": "TESTPDB", "character_set": "AL32UTF8",
                    "national_character_set": "AL16UTF16", "database_timezone": "+00:00",
                    "options": ["test:TRUE"], "session": {
                        "current_schema": "NUMBER_TEST", "current_edition": "ORA$BASE",
                        "session_timezone": "+00:00", "nls_date_format": "YYYY-MM-DD HH24:MI:SS",
                        "nls_timestamp_format": "YYYY-MM-DD HH24:MI:SS.FF6", "nls_numeric_characters": ".,",
                        "nls_sort": "BINARY", "nls_comp": "BINARY", "isolation_level": None}}
        lines = [IDENTITY + json.dumps(identity)]
        for case in number_cases(ROOT):
            lines.append(MARKER + json.dumps({"case_id": case["id"],
                         "observations": {name: EXPECTED[name] for name in probes(case)}}))
        return "\n".join(lines)

    def test_missing_duplicate_and_extra_case_markers_fail_closed(self):
        text = self.stdout()
        for changed in ("\n".join(text.splitlines()[:-1]), text + "\n" + text.splitlines()[-1],
                        text + '\n' + MARKER + '{"case_id":"unknown","observations":{}}'):
            with self.assertRaises(ValueError):
                parse_observations(changed, number_cases(ROOT))

    def test_actual_value_mutation_fails_even_when_model_passes(self):
        _, observations = parse_observations(self.stdout(), number_cases(ROOT))
        observations["ORA-TYPE-001-CASE-01"]["arithmetic"] = "123.99"
        results = observed_results(ROOT, "19c", observations, "2026-09-17T00:00:00Z", "2026-09-17T00:00:01Z")
        self.assertEqual("failed-native", results[0]["status"])
        self.assertEqual(19, sum(row["status"] == "passed-native" for row in results))

    def test_mock_client_end_to_end_and_real_26ai_version_number(self):
        for lane, version, banner in (("19c", "19.25.0.0.0", "Oracle Database 19c"),
                                      ("26ai", "23.26.1.0.0", "Oracle AI Database 26ai")):
            execution = subprocess.CompletedProcess([], 0, self.stdout(version, banner), "")
            with patch("lightyear_data.oracle_number_native.subprocess.run", return_value=execution) as client:
                receipt = run(ROOT, lane, "number_test", "sqlplus", "test-only-key", "test-runner")
            self.assertEqual(20, receipt["native_passed_case_count"])
            self.assertEqual(5, receipt["native_verified_behavior_count"])
            self.assertFalse(receipt["native_oracle_conformance"])
            self.assertFalse(receipt["target_equivalence_observed"])
            self.assertEqual(["sqlplus", "-L", "-S", "/@number_test"], client.call_args.args[0])
            self.assertNotIn("SYS_CONTEXT('USERENV','ISOLATION_LEVEL')", client.call_args.kwargs['input'])
            self.assertIn('ALTER SESSION SET ISOLATION_LEVEL = READ COMMITTED;', client.call_args.kwargs['input'])
            self.assertEqual('READ COMMITTED', receipt['session_settings']['isolation_level'])
            self.assertEqual('explicit ALTER SESSION accepted', receipt['session_settings']['isolation_level_provenance'])
            changed = copy.deepcopy(receipt)
            changed["results"][0]["harness_sql_sha256"] = "a" * 64
            changed = sign(changed, "test-only-key", "test-runner")
            self.assertTrue(any("harness-binding-invalid" in e for e in validate_native_execution_receipt(ROOT, changed, "test-only-key")))
            # A missing case prevents the entire behavior from being verified.
            changed = copy.deepcopy(receipt)
            changed["results"].pop(0)
            changed["native_executed_case_count"] = 19
            changed["native_passed_case_count"] = 19
            changed = sign(changed, "test-only-key", "test-runner")
            self.assertIn("oracle-native-receipt-behavior-count-invalid", validate_native_execution_receipt(ROOT, changed, "test-only-key"))

    def test_no_signing_key_never_starts_a_client(self):
        with patch("lightyear_data.oracle_number_native.subprocess.run") as client, self.assertRaises(ValueError):
            run(ROOT, "19c", "alias", "sqlplus", "", "test")
        client.assert_not_called()


class EvidenceFloorTests(unittest.TestCase):
    def test_floor_is_order_independent_and_missing_is_simulated(self):
        for first in ("simulated", "local_observed", "zos_observed"):
            self.assertEqual(first, evidence_floor(first, "zos_observed"))
            self.assertEqual(first, evidence_floor("zos_observed", first))
            self.assertEqual("simulated", evidence_floor(None, first))
        self.assertEqual("simulated", evidence_floor())
        with self.assertRaises(ValueError):
            evidence_floor("invented-live-class", "zos_observed")

    def test_unlabelled_and_simulated_bundles_cannot_promote_a_child(self):
        payload = {"run_id": "test", "adapter_id": "test", "source_system": "test",
                   "captured_at": "now", "observations": [{"entity_kind": "node", "entity_id": "node:test",
                   "evidence_class": "zos_observed", "details": {}}]}
        self.assertEqual("simulated", CaptureBundle.from_dict(payload).observations[0].evidence_class)
        payload["evidence_class"] = "local_observed"
        self.assertEqual("local_observed", CaptureBundle.from_dict(payload).observations[0].evidence_class)

    def test_mixed_projection_keeps_weaker_confidence(self):
        event = {"assertion": "observed", "run_id": "test", "sequence": 1, "operation": "read",
                 "details": {}, "content_sha256": "a" * 64}
        result = _projection([{**event, "evidence_class": c} for c in ("simulated", "zos_observed")])
        self.assertEqual(0.45, result["confidence"])
        self.assertEqual(["simulated", "zos_observed"], result["evidence_classes"])

    def test_multi_target_aggregation_does_not_manufacture_live_class(self):
        def receipt(target, evidence):
            return seal({"target": target, "status": "passed", "evidence_class": evidence})
        oracle = receipt("oracle-26ai-free", "live-container-target-equivalence")
        for evidence in (None, "simulated", "invented"):
            result = aggregate_receipts([oracle, receipt("postgresql-16", evidence)])
            self.assertEqual("failed", result["status"])
            self.assertEqual("simulated", result["evidence_class"])
        result = aggregate_receipts([oracle, oracle, receipt("postgresql-16", "live-container-target-equivalence")])
        self.assertIn("duplicate-target-receipt", result["errors"])

    def test_readiness_receipt_cannot_inherit_a_stronger_or_missing_class(self):
        from lightyear_readiness import asm, ims, cics_vsam
        for module in (asm, ims, cics_vsam):
            for child in ("local_observed", "simulated", None):
                comparison = {"baseline_evidence_class": "zos_observed", "candidate_evidence_class": child,
                              "evidence_class": "zos_observed", "status": "passed", "behavior_match": True,
                              "mainframe_baseline": True}
                comparison["content_sha256"] = module.canonical_hash(comparison)
                receipt = module.issue_receipt(comparison)
                self.assertEqual(child or "simulated", receipt["evidence_class"])
                if child != "local_observed":
                    self.assertFalse(receipt["development_ready"])
                self.assertFalse(receipt["mainframe_equivalent"])

    def test_rehashed_projection_cannot_raise_its_confidence(self):
        from lightyear_runtime.contracts import canonical_hash
        from lightyear_runtime.engine import RuntimeEvidenceEngine, validate_snapshot
        graph = {"content_sha256": "b" * 64, "nodes": [{"id": "node:test"}], "edges": []}
        bundle = CaptureBundle.from_dict({"run_id": "test", "adapter_id": "test", "source_system": "fixture",
            "captured_at": "now", "evidence_class": "simulated", "required_nodes": ["node:test"],
            "observations": [{"entity_kind": "node", "entity_id": "node:test"}]})
        payload = RuntimeEvidenceEngine(graph).build([bundle])
        payload["projections"]["nodes"]["node:test"]["confidence"] = 0.95
        payload["content_sha256"] = canonical_hash(payload, {"content_sha256"})
        self.assertIn("runtime projections differ from admitted event evidence", validate_snapshot(payload, graph))

    def test_release_promotion_cannot_hide_a_blocked_input(self):
        from lightyear_audit.policy import AuditPolicyEngine
        engine = AuditPolicyEngine.load(ROOT / "audit/policies/promotion.json")
        runtime = [{"id": "dev", "policy_id": "runtime.development_readiness", "status": "passed"},
                   {"id": "mainframe", "policy_id": "runtime.mainframe_equivalence", "status": "passed"}]
        execution = [{"id": "exec", "status": "passed"}]
        def decide(runs, executions):
            return engine.promotion_decision("release:test", runs, "a" * 64, "b" * 64,
                                             "2026-09-17T00:00:00Z", execution_decisions=executions)
        self.assertEqual("passed", decide(runtime, execution)["status"])
        self.assertIn("mainframe-equivalence", decide(runtime + [
            {"id": "blocked-mainframe", "policy_id": "runtime.mainframe_equivalence", "status": "blocked"}], execution)["gaps"])
        self.assertIn("hardened-execution-enforcement", decide(runtime, execution + [
            {"id": "blocked-exec", "status": "blocked"}])["gaps"])

    def test_mainframe_decision_rechecks_observation_classes(self):
        from lightyear_audit.policy import AuditPolicyEngine
        engine = AuditPolicyEngine.load(ROOT / "audit/policies/promotion.json")
        run = {"run_id": "test", "adapter_id": "test", "content_sha256": "a" * 64,
               "events": [{"evidence_class": "simulated"}, {"evidence_class": "zos_observed"}],
               "policies": {"mainframe_equivalence": {"status": "passed", "gaps": []}}}
        self.assertEqual("blocked", engine.runtime_decision(run, "mainframe_equivalence", "2026-09-17T00:00:00Z")["status"])


class PlannerRadiusTests(unittest.TestCase):
    def setUp(self):
        self.record = compare_pair("pair:test", "ALTER TABLE x ADD y DATE;", "ALTER TABLE x ADD y DATE;")
        self.pair = {"pair_id": "pair:test", "oracle": {"path": "o.sql", "logical_sha256": "a" * 64},
                     "postgresql": {"path": "p.sql", "logical_sha256": "b" * 64}}
        self.register = comparison_register([self.record], {"pair:test": self.pair})
        self.results = [plan_pair(self.record, self.pair, default_policy())]

    def proposal(self, pattern):
        return {"entity_id": "pair:test", "kind": "propose-normalization", "pattern": pattern,
                "match_basis": "comparison-reasons-and-construct-kinds", "terms": "Test proposal, no authorization."}

    def test_measured_pair_once_and_both_files_without_signing(self):
        measure_proposals(self.results, [self.proposal("datetime")], self.register)
        action = self.results[0]["actions"][0]
        self.assertEqual(1, action["impact"]["suppressed_comparisons"])
        self.assertEqual(2, action["blast_radius"]["affected_files"])
        self.assertFalse(action["signature_enabled"])
        self.assertEqual(self.record["verdict"], self.results[0]["verdict"])

    def test_invalid_empty_and_zero_reach_are_different(self):
        for pattern, register, state, count in (("[", self.register, "invalid-pattern", None),
                ("datetime", [], "empty-register", None), ("no-match", self.register, "measured", 0)):
            result = copy.deepcopy(self.results)
            measure_proposals(result, [self.proposal(pattern)], register)
            impact = result[0]["actions"][0]["impact"]
            self.assertEqual(state, impact["suppression_estimate"])
            self.assertEqual(count, impact["suppressed_comparisons"])
            self.assertFalse(result[0]["actions"][0]["signature_enabled"])

    def test_raw_register_and_unknown_scope_are_not_accepted(self):
        measure_proposals(self.results, [self.proposal("datetime")], [{"pair_id": "pair:test"}])
        self.assertEqual("invalid-register", self.results[0]["actions"][0]["impact"]["suppression_estimate"])
        with self.assertRaises(ValueError):
            measure_proposals(self.results, [{**self.proposal("datetime"), "entity_id": "unknown"}], self.register)


if __name__ == "__main__":
    unittest.main()
