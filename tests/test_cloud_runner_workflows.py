import json
from pathlib import Path
import tempfile
import unittest

import yaml

from lightyear_cloud_runner.signing import sha256
from tools.cloud_runner_dispatch_bundle import materialize

ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_phase_one_has_no_cloud_launch_capability(self):
        text = (ROOT / ".github/workflows/cloud-runner-launch.yml").read_text()
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        steps = workflow["jobs"]["plan"]["steps"]
        actions = [step["uses"] for step in steps if "uses" in step]
        self.assertTrue(all(len(action.split("@")[1]) == 40 for action in actions))
        runs = "\n".join(step.get("run", "") for step in steps)
        for forbidden in ("gcloud ", "terraform apply", "packer build", "docker ", "curl "):
            self.assertNotIn(forbidden, runs)
        self.assertNotIn("${{ inputs.", runs)

    def test_metadata_writer_rejects_untrusted_policy_and_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "plan"
            bundle = json.dumps({"request": {}, "go": {}, "witness": {}})
            policy = "{}"
            with self.assertRaises(ValueError):
                materialize(bundle, policy, "0" * 64, out)
            self.assertFalse(out.exists())
            materialize(bundle, policy, sha256(policy.encode()), out)
            self.assertEqual((out / "policy.json").read_text(), policy)
            with self.assertRaises(FileExistsError):
                materialize(bundle, policy, sha256(policy.encode()), out)

    def test_inputs_cannot_choose_an_output_path(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                materialize('{"../../escape":{}}', "{}", sha256(b"{}"), Path(folder) / "plan")


if __name__ == "__main__":
    unittest.main()
