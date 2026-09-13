"""Business equivalence alone must never admit AlloyDB platform qualification."""
import importlib.util
from pathlib import Path
import unittest

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
