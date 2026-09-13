"""Signed collector observations remain authoritative over display summaries."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_data.cloudbank_journeys import JourneyFailure
from lightyear_data.cloudbank_log_correlation import STATE_FILE, STATE_TYPE
from lightyear_data.contracts import sign

spec = importlib.util.spec_from_file_location("alloydb_control", Path(__file__).resolve().parents[1] / "tools/cloudbank_alloydb_control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)
KEY, SIGNER = "test-key", "test-signer"


class ControlEvidenceTests(unittest.TestCase):
    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_unsigned_display_summary_cannot_shadow_signed_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = {"observation_type": "test", "status": "passed-test"}
            proof = sign(value, KEY, SIGNER)
            self.write(root / "log-correlation.result.json", value)
            self.write(root / "log-correlation.observation.json", proof)
            self.assertEqual(proof, control.signed_observation(root, "log-correlation", KEY))
            self.write(root / "log-correlation.observation.json", value)
            with self.assertRaisesRegex(JourneyFailure, "evidence-content-or-signature-invalid"):
                control.signed_observation(root, "log-correlation", KEY)

    def test_completion_rejects_unfinished_or_different_signed_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            context = {"content_sha256": "context", "environment": {}, "images": {}, "bindings": {}}
            proof = {**{k: context[k] for k in ("environment", "images", "bindings")},
                     "observation_type": "test", "status": "passed-test", "run_id": "original"}
            self.write(root / "log-correlation.observation.json", sign(proof, KEY, SIGNER))
            intent = {"record_type": "lightyear-alloydb-platform-control-intent", "phase": "log-correlation",
                      "action": "run", "context_sha256": "context", "output_root": str(root)}
            self.write(root.with_name(root.name + "-intent.json"), sign(intent, KEY, SIGNER))
            state = {**proof, "state_type": STATE_TYPE, "cleanup_complete": True, "phase": "installed-and-verified"}
            with patch("lightyear_data.cloudbank_log_correlation.verify_observation"):
                self.write(root / STATE_FILE, sign(state, KEY, SIGNER))
                control.completed_log_inputs(root, context, KEY)
                for change in ({"cleanup_complete": False}, {"run_id": "different"}, {"phase": "before-release-installed"}):
                    self.write(root / STATE_FILE, sign({**state, **change}, KEY, SIGNER))
                    with self.assertRaisesRegex(JourneyFailure, "verified-released-state-required"):
                        control.completed_log_inputs(root, context, KEY)


if __name__ == "__main__":
    unittest.main()
