"""Business equivalence alone must never admit AlloyDB platform qualification."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_data.cloudbank_journeys import JourneyFailure
from lightyear_data.cloudbank_ms71 import admit
from lightyear_data.contracts import sign
from test_cloudbank_ms71 import comparison, PROVIDERS, KEY, SIGNER
from test_cloudbank_platform_qualification import profile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alloydb_admission", ROOT / "tools/cloudbank_alloydb_platform.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class AlloyDbAdmissionTests(unittest.TestCase):
    def inputs(self):
        comparisons = [comparison(p) for p in PROVIDERS]
        ms71 = admit(comparisons, KEY, SIGNER, ROOT)
        selected = comparisons[1]
        pp = profile()
        pp["signer"] = SIGNER
        context = sign({"context_type": "lightyear-alloydb-platform-campaign", "production_environment": False,
            "profile": sign(pp, KEY, SIGNER), "managed_profile": selected["profile"],
            "ms71_receipt_sha256": ms71["content_sha256"], "alloydb_comparison_sha256": selected["content_sha256"],
            "managed_target": selected["after"]}, KEY, SIGNER)
        return context, ms71

    def test_each_missing_operational_phase_blocks_acceptance(self):
        context, ms71 = self.inputs()
        for missing in gate.PHASES:
            with self.subTest(missing=missing), self.assertRaisesRegex(JourneyFailure, "all-operational-phases-required"):
                gate.assemble(context, ms71, {p: {} for p in gate.PHASES if p != missing}, {}, KEY)

    def test_ms71_pass_and_qualified_flag_cannot_substitute_for_platform_proofs(self):
        context, ms71 = self.inputs()
        receipt = sign({"context": context, "ms71_receipt": ms71, "phases": {}, "managed_boundaries": {},
                        "alloydb_platform_qualified": True}, KEY, SIGNER)
        with self.assertRaisesRegex(JourneyFailure, "all-operational-phases-required"):
            gate.verify_receipt(receipt, KEY)

    def test_operational_scope_has_the_28_platform_controls_and_explicit_alloydb_failover(self):
        self.assertEqual(29, len(set(gate.SCENARIOS)))
        self.assertEqual(gate.platform_contract()["controls"]["backup_restore"]["maximum_rto_seconds"], 630)
        self.assertIn("regional-alloydb-primary-failover-with-acknowledged-data", gate.SCENARIOS)

    def test_export_rejects_incomplete_qualification_before_creating_output(self):
        context, ms71 = self.inputs()
        receipt = sign({"context": context, "ms71_receipt": ms71, "phases": {}, "managed_boundaries": {},
                        "alloydb_platform_qualified": True}, KEY, SIGNER)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "receipt.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(JourneyFailure, "all-operational-phases-required"):
                gate.export_bundle(root / "missing-inputs.json", root / "receipt.json", root / "export", KEY)
            self.assertFalse((root / "export").exists())

    def test_export_preserves_original_crlf_bytes_and_rejects_source_drift(self):
        from lightyear_data.contracts import verify_signature
        # Admission is tested separately; this test exercises the export boundary.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = sign({"signer": SIGNER}, KEY, SIGNER)
            ms71 = sign({"ms71_complete": True, "alloydb_platform_qualified": False}, KEY, SIGNER)
            phases = {phase: sign({"phase": phase}, KEY, SIGNER) for phase in gate.PHASES}
            boundaries = {phase: sign({"boundary": phase}, KEY, SIGNER) for phase in
                          ("secret-rotation", "log-correlation", "alert-drill", "network-enforcement", "sustained-load")}
            receipt = sign({"campaign_id": "test", "context": context, "ms71_receipt": ms71,
                            "phases": phases, "managed_boundaries": boundaries}, KEY, SIGNER)
            inputs = {"context": "context.json", "ms71_receipt": "ms71.json",
                      "phases": {p: p + ".json" for p in phases},
                      "managed_boundaries": {p: p + "-boundary.json" for p in boundaries}}
            values = {"context.json": context, "ms71.json": ms71, "receipt.json": receipt,
                      **{inputs["phases"][p]: v for p, v in phases.items()},
                      **{inputs["managed_boundaries"][p]: v for p, v in boundaries.items()}}
            for name, value in values.items():
                (root / name).write_bytes((json.dumps(value, indent=2) + "\n").replace("\n", "\r\n").encode())
            (root / "inputs.json").write_text(json.dumps(inputs))
            with patch.object(gate, "verify_receipt", return_value=receipt) as verify:
                result = gate.export_bundle(root / "inputs.json", root / "receipt.json", root / "export", KEY)
                verify.assert_called_once_with(receipt, KEY)
                self.assertEqual(result["file_count"], 19)
                for phase in phases:
                    self.assertEqual((root / "export" / (phase + ".json")).read_bytes(),
                                     (root / inputs["phases"][phase]).read_bytes())
                manifest = json.loads((root / "export/publication-export.json").read_bytes())
                self.assertTrue(verify_signature(manifest, KEY))
                self.assertFalse(manifest["cloud_readback_repeated_at_export"])
                (root / "ha.json").write_text(json.dumps(sign({"phase": "changed"}, KEY, SIGNER)))
                with self.assertRaisesRegex(JourneyFailure, "export-source-drift"):
                    gate.export_bundle(root / "inputs.json", root / "receipt.json", root / "drift-export", KEY)
                self.assertFalse((root / "drift-export").exists())
