from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from lightyear_knowledge_graph.model import load_graph
from lightyear_pilot.analysis import build_source_analysis, validate_source_analysis
from lightyear_pilot.pilot import (
    PilotError,
    build_dossier,
    build_intake_manifest,
    build_preflight,
    canonical_hash,
    load_json,
    render_dossier_markdown,
    validate_compatibility_policy,
    validate_dossier,
    validate_intake_manifest,
    validate_preflight,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_json(ROOT / "pilot/pilot.profile.json")
COMPATIBILITY = load_json(ROOT / "pilot/compatibility.policy.json")
SOURCE = ROOT / "pilot/reference-intake"
CANONICAL = ROOT / "pilot/reference-output"


class SourceOnlyPilotTests(unittest.TestCase):
    def build(self) -> tuple[dict, dict, dict, dict, dict]:
        intake = build_intake_manifest(
            SOURCE,
            PROFILE,
            approval_id="repository-reference-fixture",
            source_label="CardDemo bounded reference intake",
        )
        analysis_graph, analysis = build_source_analysis(
            SOURCE,
            intake,
            PROFILE,
            ROOT / "pilot/analysis-relationships.json",
        )
        preflight = build_preflight(ROOT, intake, PROFILE)
        dossier = build_dossier(
            ROOT,
            intake,
            preflight,
            analysis,
            analysis_graph,
            PROFILE,
            COMPATIBILITY,
        )
        return intake, analysis_graph, analysis, preflight, dossier

    def test_reference_release_is_deterministic_and_valid(self) -> None:
        intake, analysis_graph, analysis, preflight, dossier = self.build()
        self.assertEqual([], validate_intake_manifest(intake, PROFILE, SOURCE))
        self.assertEqual(
            [],
            validate_source_analysis(
                analysis_graph,
                analysis,
                intake,
                PROFILE,
                ROOT / "pilot/analysis-relationships.json",
            ),
        )
        self.assertEqual([], validate_preflight(preflight, intake))
        self.assertEqual(
            [],
            validate_dossier(
                dossier,
                intake,
                preflight,
                analysis,
                analysis_graph,
                ROOT,
                PROFILE,
            ),
        )
        self.assertEqual(intake, load_json(CANONICAL / "intake.manifest.json"))
        self.assertEqual(analysis, load_json(CANONICAL / "source-analysis.receipt.json"))
        self.assertEqual(
            analysis_graph,
            load_graph(CANONICAL / "source-estate.snapshot.json.gz"),
        )
        self.assertEqual(preflight, load_json(CANONICAL / "mainframe.preflight.json"))
        self.assertEqual(dossier, load_json(CANONICAL / "pilot.dossier.json"))
        self.assertEqual(
            render_dossier_markdown(dossier),
            (CANONICAL / "pilot.dossier.md").read_text(encoding="utf-8"),
        )

    def test_reference_intake_covers_all_nine_source_classes(self) -> None:
        intake, _, analysis, _, _ = self.build()
        self.assertEqual(10, intake["statistics"]["files"])
        self.assertEqual(
            {"cobol", "copybook", "db2-ddl", "hlasm", "ims", "jcl", "pli", "system-configuration", "vsam"},
            set(intake["statistics"]["by_kind"]),
        )
        self.assertTrue(intake["scope"]["source_only"])
        self.assertFalse(intake["scope"]["live_system_contact"])
        self.assertTrue(analysis["analysis_ready"])
        self.assertEqual(10, sum(item["typed_files"] for item in analysis["coverage"]))

    def test_customer_estate_connects_mixed_source_without_claiming_behavior(self) -> None:
        _, graph, analysis, _, dossier = self.build()
        edges = {(item["source"], item["relation"], item["target"]) for item in graph["edges"]}
        nodes = {item["id"]: item for item in graph["nodes"]}
        call_names = {
            (nodes[source]["name"], nodes[target]["name"])
            for source, relation, target in edges
            if relation == "CALLS"
        }
        self.assertIn(("ACCOUNTV", "ACCTPL1"), call_names)
        self.assertTrue(any(relation == "EXECUTES" and nodes[target]["name"] == "ACCTPL1" for _, relation, target in edges))
        self.assertTrue(any(relation == "READS_TABLE" and nodes[target]["name"] == "CARDDEMO.AUTHFRDS" for _, relation, target in edges))
        self.assertTrue(any(relation == "BRANCHES_TO" for _, relation, _ in edges))
        self.assertTrue(any(relation == "USES_DBD" for _, relation, _ in edges))
        self.assertTrue(any(relation == "SENSITIVE_TO" for _, relation, _ in edges))
        self.assertTrue(any(relation == "HAS_COMPONENT" for _, relation, _ in edges))
        self.assertTrue(any(relation == "TARGETS" for _, relation, _ in edges))
        self.assertTrue(any(relation == "EXECUTES" and nodes[target]["name"] == "DATEFMT" for _, relation, target in edges))
        self.assertFalse(analysis["behavior_proven"])
        self.assertFalse(analysis["mainframe_equivalent"])
        self.assertEqual("customer-source-analysis", dossier["estate"]["kind"])
        self.assertEqual(analysis["graph_content_sha256"], dossier["estate"]["graph_sha256"])

    def test_customer_intake_may_use_an_applicable_subset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ONLYCOBOL.cbl").write_text(
                "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. ONLYCOBOL.\n",
                encoding="utf-8",
            )
            intake = build_intake_manifest(
                root,
                PROFILE,
                approval_id="customer-pilot-approval-123",
                source_label="COBOL-only approved pilot",
            )
        self.assertEqual({"cobol": 1}, intake["statistics"]["by_kind"])
        self.assertEqual([], validate_intake_manifest(intake, PROFILE))

    def test_dossier_is_pilot_ready_without_live_or_model_overclaims(self) -> None:
        _, _, _, preflight, dossier = self.build()
        self.assertTrue(dossier["pilot_ready"])
        self.assertFalse(dossier["proofs"]["model_qualification"]["qualified"])
        self.assertEqual(8, dossier["proofs"]["model_qualification"]["required_independently_sealed_evaluations"])
        self.assertFalse(dossier["proofs"]["model_qualification"]["approved_successful_portfolio_run"])
        self.assertFalse(dossier["mainframe_equivalent"])
        self.assertFalse(dossier["production_ready"])
        self.assertEqual("blocked", preflight["gates"]["6_authorized_original_execution"])
        self.assertEqual("blocked", preflight["gates"]["8_signed_equivalence"])

    def test_credential_shaped_material_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in SOURCE.rglob("*"):
                if item.is_file():
                    target = root / item.relative_to(SOURCE)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(item.read_bytes())
            (root / "config/credential.txt").write_text(
                "authorization: Bearer this-is-not-an-allowed-token\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(PilotError, "credential-shaped-material-detected"):
                build_intake_manifest(
                    root, PROFILE, approval_id="approved-reference", source_label="tamper"
                )

    def test_binary_hidden_unsupported_and_symbolic_link_inputs_fail(self) -> None:
        cases = {
            "binary": ("config/binary.txt", b"ok\x00bad"),
            "hidden": (".hidden/config.json", b"{}\n"),
            "unsupported": ("config/archive.zip", b"not a zip\n"),
        }
        for label, (name, content) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                with self.assertRaises(PilotError):
                    build_intake_manifest(
                        root, PROFILE, approval_id="approved-reference", source_label=label
                    )
        if hasattr(os, "symlink"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / "target.cbl"
                target.write_text("IDENTIFICATION DIVISION.\n", encoding="utf-8")
                os.symlink(target, root / "linked.cbl")
                with self.assertRaisesRegex(PilotError, "symbolic-links-are-not-accepted"):
                    build_intake_manifest(
                        root, PROFILE, approval_id="approved-reference", source_label="link"
                    )

    def test_intake_tamper_fails_even_when_source_tree_hash_is_recomputed(self) -> None:
        intake, _, _, _, _ = self.build()
        changed = copy.deepcopy(intake)
        changed["files"][0]["kind"] = "jcl"
        changed["source_tree_sha256"] = canonical_hash({"files": changed["files"]})
        changed["content_sha256"] = canonical_hash(changed, {"content_sha256"})
        errors = validate_intake_manifest(changed, PROFILE, SOURCE)
        self.assertTrue(errors)
        self.assertNotIn("intake-content-hash-invalid", errors)
        self.assertIn("intake-required-source-class-missing", errors)

    def test_preflight_cannot_promote_gates_six_or_eight(self) -> None:
        intake, _, _, preflight, _ = self.build()
        changed = copy.deepcopy(preflight)
        changed["gates"]["6_authorized_original_execution"] = "passed"
        changed["ready_for_gates_6_8"] = True
        changed["content_sha256"] = canonical_hash(changed, {"content_sha256"})
        errors = validate_preflight(changed, intake)
        self.assertIn("preflight-live-gate-posture-invalid", errors)
        self.assertIn("preflight-promotes-unproven-readiness", errors)

    def test_dossier_cannot_relabel_model_or_production_readiness(self) -> None:
        intake, analysis_graph, analysis, preflight, dossier = self.build()
        changed = copy.deepcopy(dossier)
        changed["proofs"]["model_qualification"]["qualified"] = True
        changed["production_ready"] = True
        changed["content_sha256"] = canonical_hash(changed, {"content_sha256"})
        errors = validate_dossier(changed, intake, preflight, analysis, analysis_graph)
        self.assertIn("dossier-overclaims-live-readiness", errors)
        self.assertIn("dossier-overclaims-model-qualification", errors)

    def test_bound_artifact_drift_invalidates_dossier(self) -> None:
        intake, analysis_graph, analysis, preflight, dossier = self.build()
        changed = copy.deepcopy(dossier)
        artifact = next(
            item for item in changed["evidence_artifacts"] if item["id"] == "canonical-graph"
        )
        artifact["sha256"] = "0" * 64
        changed["content_sha256"] = canonical_hash(changed, {"content_sha256"})
        errors = validate_dossier(
            changed,
            intake,
            preflight,
            analysis,
            analysis_graph,
            ROOT,
            PROFILE,
        )
        self.assertIn("dossier-artifact-drift:canonical-graph", errors)

    def test_release_profile_pins_every_evidence_artifact(self) -> None:
        intake, analysis_graph, analysis, preflight, _ = self.build()
        changed = copy.deepcopy(PROFILE)
        artifact = next(
            item for item in changed["evidence_artifacts"] if item["id"] == "canonical-graph"
        )
        artifact["sha256"] = "0" * 64
        changed["content_sha256"] = canonical_hash(changed, {"content_sha256"})
        with self.assertRaisesRegex(PilotError, "pilot-evidence-release-drift"):
            build_dossier(
                ROOT,
                intake,
                preflight,
                analysis,
                analysis_graph,
                changed,
                COMPATIBILITY,
            )

    def test_analysis_tamper_and_source_drift_fail_closed(self) -> None:
        intake, graph, analysis, _, _ = self.build()
        changed = copy.deepcopy(analysis)
        changed["behavior_proven"] = True
        changed["content_sha256"] = canonical_hash(changed, {"content_sha256"})
        errors = validate_source_analysis(
            graph,
            changed,
            intake,
            PROFILE,
            ROOT / "pilot/analysis-relationships.json",
        )
        self.assertIn("analysis-overclaims-source-only-evidence", errors)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in SOURCE.rglob("*"):
                if item.is_file():
                    target = root / item.relative_to(SOURCE)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(item.read_bytes())
            (root / "cobol/ACCOUNTV.cbl").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "analysis-(raw|logical)-source-drift"):
                build_source_analysis(
                    root,
                    intake,
                    PROFILE,
                    ROOT / "pilot/analysis-relationships.json",
                )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in SOURCE.rglob("*"):
                if item.is_file():
                    target = root / item.relative_to(SOURCE)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(item.read_bytes())
            (root / "cobol/UNLISTED.cbl").write_text(
                "       PROGRAM-ID. UNLISTED.\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "analysis-source-inventory-drift"):
                build_source_analysis(
                    root,
                    intake,
                    PROFILE,
                    ROOT / "pilot/analysis-relationships.json",
                )

    def test_compatibility_policy_rejects_major_drift_and_overclaim(self) -> None:
        self.assertEqual([], validate_compatibility_policy(COMPATIBILITY))
        changed = copy.deepcopy(COMPATIBILITY)
        changed["schema_version"] = "2.0"
        changed["production_ready"] = True
        changed["content_sha256"] = canonical_hash(changed, {"content_sha256"})
        errors = validate_compatibility_policy(changed)
        self.assertIn("compatibility-policy-identity-invalid", errors)
        self.assertIn("compatibility-policy-overclaims-production-readiness", errors)

    def test_pilot_contract_schemas_are_frozen_and_parseable(self) -> None:
        schemas = sorted((ROOT / "pilot/schema").glob("*.schema.json"))
        self.assertEqual(5, len(schemas))
        for path in schemas:
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", payload["$schema"])
                self.assertFalse(payload["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
