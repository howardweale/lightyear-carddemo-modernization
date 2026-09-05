from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "factory/cloudbank/platform-qualification/gke/repair-telemetry.sh"

# Real Bash, renderer, jq, and checksum commands; only the cloud boundaries are stubs.
CLOUD_STUB = '''
import json
import os
import sys
from pathlib import Path

tool = Path(sys.argv[0]).name
args = sys.argv[1:]
case = os.environ["TELEMETRY_TEST_CASE"]
with open(os.environ["TELEMETRY_TEST_CALLS"], "a") as handle:
    handle.write(json.dumps([tool, *args]) + "\\n")
if tool == "gcloud":
    if args[:2] == ["projects", "describe"]:
        print("non-production")
    elif args[:3] == ["container", "clusters", "describe"]:
        print("LEGACY_DATAPATH" if case == "non-v2" else "ADVANCED_DATAPATH")
    elif args[:3] == ["container", "clusters", "get-credentials"]:
        pass
    elif args[:2] == ["storage", "cp"]:
        for argument in args[2:]:
            if argument.startswith("/") and not Path(argument).is_file():
                raise RuntimeError("Attempted upload of missing evidence: " + argument)
        if case == "upload-failed":
            sys.exit(5)
    else:
        raise RuntimeError("Unexpected gcloud command: " + repr(args))
elif tool == "kubectl":
    if args[2:3] == ["apply"]:
        pass
    elif "rollout" in args:
        if case == "rollout-failed":
            sys.exit(9)
    elif args[4:7] == ["get", "deployment", "otel-collector"]:
        print(json.dumps({"metadata": {"generation": 2}, "spec": {"replicas": 2},
                          "status": {"observedGeneration": 2, "readyReplicas":
                                     1 if case == "not-ready" else 2,
                                     "updatedReplicas": 2, "availableReplicas": 2}}))
    else:
        raise RuntimeError("Unexpected kubectl command: " + repr(args))
'''


@unittest.skipUnless(os.name == "posix" and all(shutil.which(tool) for tool in (
    "bash", "jq", "sha256sum",
)), "Cloud Shell repair requires POSIX Bash, jq, and sha256sum")
class CloudBankTelemetryRepairTests(unittest.TestCase):
    def test_repair_records_actual_outcome_and_never_applies_application_resources(self) -> None:
        for case in ("ready", "non-v2", "render-failed", "rollout-failed", "not-ready", "upload-failed"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                binaries = root / "bin"
                binaries.mkdir()
                for tool in ("gcloud", "kubectl"):
                    executable = binaries / tool
                    executable.write_text(f"#!{sys.executable}\n" + CLOUD_STUB, encoding="utf-8")
                    executable.chmod(0o755)
                (binaries / "python").symlink_to(sys.executable)
                output = root / "evidence"
                calls_file = root / "calls.jsonl"
                environment = {
                    **os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
                    "TELEMETRY_TEST_CASE": case, "TELEMETRY_TEST_CALLS": str(calls_file),
                    "GCP_PROJECT_ID": "test-project", "GCP_REGION": "europe-west2",
                    "GKE_CLUSTER_NAME": "cloudbank-ms67", "GKE_NAMESPACE": "cloudbank-ms67",
                    "GCP_NETWORK_NAME": "cloudbank-ms67", "GCP_SUBNET_NAME": "cloudbank-ms67",
                    "ARTIFACT_REPOSITORY": "cloudbank-ms67", "CLOUD_SQL_INSTANCE": "test-postgres",
                    "DNS_ZONE_NAME": "test-zone", "DELEGATED_DNS_NAME": "test.example.com",
                    "TLS_HOSTNAME": "cloudbank.test.example.com", "MODEL_EGRESS_CIDR": "192.0.2.1/32",
                    "MODEL_NAMESPACE": "cloudbank-model", "OLLAMA_MODEL_NAME": "qwen2.5:0.5b",
                    "OLLAMA_MODEL_IMAGE": "example.com/model@sha256:" + "1" * 64,
                    "OLLAMA_MODEL_MANIFEST_SHA256": "2" * 64,
                    "GOOGLE_APIS_CIDR": "199.36.153.8/30", "LETSENCRYPT_EMAIL": "owner@example.com",
                    "EXTERNAL_SECRETS_CHART_VERSION": "1.0.0", "CERT_MANAGER_CHART_VERSION": "1.0.0",
                    "INGRESS_NGINX_CHART_VERSION": "1.0.0", "OTEL_JAVA_AGENT_SHA256": "3" * 64,
                    "OTEL_COLLECTOR_IMAGE": "example.com/collector@sha256:" + "4" * 64,
                    "LIGHTYEAR_NON_PRODUCTION_ACK": "I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS",
                }
                if case == "render-failed":
                    environment["LETSENCRYPT_EMAIL"] = 'invalid"input'
                result = subprocess.run(["bash", str(SCRIPT), str(output)], env=environment,
                                        capture_output=True, text=True, timeout=15)
                calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
                uploads = [call for call in calls if call[:3] == ["gcloud", "storage", "cp"]]
                mutations = [call for call in calls if call[0] == "kubectl"]
                self.assertEqual(case == "ready", result.returncode == 0, result.stdout + result.stderr)
                if case == "non-v2":
                    self.assertEqual([], mutations)
                    self.assertEqual([], uploads)
                    continue
                state = json.loads((output / "collector-status.json").read_text())
                self.assertFalse(state["qualification_complete"])
                self.assertEqual("ready" if case in ("ready", "upload-failed") else "failed", state["status"])
                self.assertEqual(1, len(uploads))
                for line in (output / "SHA256SUMS").read_text().splitlines():
                    digest, relative = line.split("  ", 1)
                    self.assertEqual(digest, hashlib.sha256((output / relative).read_bytes()).hexdigest())
                if case == "render-failed":
                    self.assertFalse((output / "collector.yaml").exists())
                    self.assertEqual([], mutations)
                else:
                    rendered = (output / "collector.yaml").read_text()
                    self.assertEqual(7, rendered.count("\nkind: "))
                    self.assertNotIn("kind: ExternalSecret", rendered)
                    self.assertNotIn("name: ollama", rendered)
                    self.assertEqual(1, sum("apply" in call for call in mutations))
                    for call in mutations:
                        self.assertEqual(["--context", "gke_test-project_europe-west2_cloudbank-ms67"], call[1:3])
                self.assertIn("MS67_COLLECTOR=" + ("READY" if case == "ready" else "FAILED"), result.stdout)


if __name__ == "__main__":
    unittest.main()
