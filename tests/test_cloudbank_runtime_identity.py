import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lightyear_data.cloudbank_journeys import JourneyFailure, SERVICES, hashed
from lightyear_data.cloudbank_runtime_identity import (
    IDENTITY, IdentityRollout, container, deployment_patch, instrument_bundle,
    pod_observation, target, verify_observation,
)
from lightyear_data.contracts import sign

NAMESPACE = "cloudbank-test"
IMAGES = {s: "registry.example/cloudbank/" + s + "@sha256:" + "a" * 64 for s in SERVICES}
ENVIRONMENT = {"project": "test-project", "region": "us-west1", "cluster": "test-cluster", "namespace": NAMESPACE}
BINDINGS = {k: "b" * 64 for k in ("image_lock_sha256", "ms64_receipt_sha256", "platform_profile_sha256")}
KEY = "unit-test-key-not-a-live-credential"


def deployment(service):
    return {"apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": service, "namespace": NAMESPACE, "uid": "deployment-" + service, "resourceVersion": "1"},
            "spec": {"replicas": 2, "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0}},
                     "template": {"spec": {"automountServiceAccountToken": False,
                         "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                         "containers": [{"name": service, "image": IMAGES[service],
                             "envFrom": [{"secretRef": {"name": "existing-external"}}],
                             "env": [{"name": "UNCHANGED", "value": "must-not-enter-patch"}],
                             "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                                 "capabilities": {"drop": ["ALL"]}}}],
                         "volumes": [{"name": "tmp", "emptyDir": {}}]}}}}


def apply(value, operations):
    result = copy.deepcopy(value)
    for op in operations:
        parts = op["path"].split("/")[1:]
        parent = result
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        if op["op"] == "test":
            if parent[parts[-1]] != op["value"]:
                raise JourneyFailure("test-json-patch-conflict")
        else:
            parent[parts[-1]] = op["value"]
    result["metadata"]["resourceVersion"] = str(int(result["metadata"]["resourceVersion"]) + 1)
    return result


class Runtime:
    namespace, images = NAMESPACE, IMAGES

    def __init__(self):
        self.deployments = {s: deployment(s) for s in SERVICES}
        self.patches, self.readiness_checks = [], []
        self.bad_preflight, self.bad_after_patch, self.drift_after_patch = None, None, None

    def deployment(self, service):
        return copy.deepcopy(self.deployments[service])

    def service_ready(self, service):
        self.readiness_checks.append(service)
        if service == self.bad_preflight:
            raise JourneyFailure("test-not-ready")

    def wait_ready(self, service):
        self.service_ready(service)

    def close_forward(self, service):
        pass

    def send(self, *args):
        class Response:
            status = 200

            def json(self):
                return {"status": "UP"}
        return Response()

    def pods(self, service):
        main = self.deployments[service]["spec"]["template"]["spec"]["containers"]
        group = main[0]["securityContext"].get("runAsGroup", 0)
        if service == self.bad_after_patch:
            group = 0
        return [{"metadata": {"namespace": NAMESPACE, "uid": service + "-" + str(group) + "-" + str(i)},
                 "spec": {"containers": copy.deepcopy(main)},
                 "status": {"containerStatuses": [{"name": service, "imageID": IMAGES[service], "ready": True,
                             "state": {"running": {}}, "user": {"linux": {"uid": 65532, "gid": group}}}]}} for i in range(2)]

    def kubectl(self, *args):
        service = args[1].split("/")[1]
        self.patches.append((service, json.loads(args[-1])))
        self.deployments[service] = apply(self.deployments[service], self.patches[-1][1])
        if self.drift_after_patch:
            self.deployments[self.drift_after_patch]["spec"]["template"]["spec"]["containers"][0]["env"] = []


class Journal:
    def __init__(self):
        self.writes, self.fail = [], False

    def write(self, state):
        if self.fail:
            raise JourneyFailure("test-upload-failed")
        self.writes.append(copy.deepcopy(state))


def engine():
    runtime, journal = Runtime(), Journal()
    state = {"run_id": "ms67-identity-" + "1" * 32, "environment": ENVIRONMENT, "bindings": BINDINGS}
    return IdentityRollout(runtime, journal, state), runtime, journal


class OverlayTests(unittest.TestCase):
    def test_exact_overlay_preserves_baseline_and_other_resources(self):
        bundle = {"kind": "List", "items": [deployment(s) for s in SERVICES] + [{"kind": "Service", "spec": {"x": "unchanged"}}]}
        original = copy.deepcopy(bundle)
        rendered = instrument_bundle(bundle, NAMESPACE)
        self.assertEqual(bundle, original)
        self.assertEqual(instrument_bundle(rendered, NAMESPACE), rendered)
        for row in rendered["items"][:-1]:
            security = row["spec"]["template"]["spec"]["containers"][0]["securityContext"]
            for k, v in IDENTITY.items():
                self.assertEqual(security.pop(k), v)
        self.assertEqual(rendered, original)

    def test_missing_duplicate_foreign_and_model_deployment_rejected(self):
        rows = [deployment(s) for s in SERVICES]
        model = {"kind": "Deployment", "metadata": {"name": "ollama"}}
        for altered in (rows[:-1], rows + [rows[0]], rows + [model]):
            with self.subTest(altered=altered[-1]["metadata"]["name"]), self.assertRaises(JourneyFailure):
                instrument_bundle({"kind": "List", "items": altered}, NAMESPACE)
        with self.assertRaises(JourneyFailure):
            instrument_bundle({"kind": "List", "items": rows}, "wrong-namespace")

    def test_unsafe_rollout_sandbox_sidecar_and_mutable_image_rejected(self):
        for field in ("strategy", "capability", "sidecar", "init", "image", "privilege", "nonroot"):
            row = deployment("account")
            pod = row["spec"]["template"]["spec"]
            if field == "strategy":
                row["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] = 1
            elif field == "capability":
                pod["containers"][0]["securityContext"]["capabilities"]["add"] = ["SETGID"]
            elif field == "sidecar":
                pod["containers"].append({"name": "extra"})
            elif field == "init":
                pod["initContainers"] = [{"name": "extra"}]
            elif field == "image":
                pod["containers"][0]["image"] = "registry/app:latest"
            elif field == "privilege":
                pod["containers"][0]["securityContext"]["privileged"] = True
            else:
                pod["securityContext"]["runAsNonRoot"] = False
            with self.subTest(field=field), self.assertRaises(JourneyFailure):
                container(row, "account", NAMESPACE)

    def test_patch_is_atomic_and_contains_only_ids(self):
        row = deployment("account")
        baseline = {"deployment_uid": row["metadata"]["uid"], "before_spec_sha256": hashed(row["spec"])}
        patch = deployment_patch(row, "account", NAMESPACE, IMAGES["account"], baseline)
        self.assertNotIn("must-not-enter-patch", json.dumps(patch))
        self.assertEqual(len(patch), 4)
        self.assertEqual(apply(row, patch)["spec"], target(row, "account", NAMESPACE)["spec"])
        for field in ("uid", "resourceVersion"):
            changed = copy.deepcopy(row)
            changed["metadata"][field] = "other"
            with self.subTest(field=field), self.assertRaises(JourneyFailure):
                apply(changed, patch)
        row["spec"]["replicas"] = 3
        with self.assertRaises(JourneyFailure):
            deployment_patch(row, "account", NAMESPACE, IMAGES["account"], baseline)


class RolloutTests(unittest.TestCase):
    def test_all_eight_are_checked_before_first_patch_then_independently_verified(self):
        rollout, runtime, journal = engine()
        original = runtime.kubectl

        def checked_patch(*args):
            self.assertEqual(set(runtime.readiness_checks), set(SERVICES))
            self.assertTrue(journal.writes[-1]["phase"].startswith("before-patch-"))
            return original(*args)
        runtime.kubectl = checked_patch
        result = rollout.run()
        self.assertEqual([s for s, _ in runtime.patches], list(SERVICES))
        verify_observation(sign(result, KEY, "operator"), KEY, BINDINGS, IMAGES, ENVIRONMENT)

    def test_final_preflight_failure_prevents_all_mutations(self):
        rollout, runtime, journal = engine()
        runtime.bad_preflight = SERVICES[-1]
        with self.assertRaises(JourneyFailure):
            rollout.run()
        self.assertEqual(runtime.patches, [])
        self.assertEqual(journal.writes, [])

    def test_intent_upload_failure_prevents_patch(self):
        rollout, runtime, journal = engine()
        journal.fail = True
        with self.assertRaisesRegex(JourneyFailure, "upload"):
            rollout.run()
        self.assertEqual(runtime.patches, [])

    def test_root_group_on_replacement_stops_next_service(self):
        rollout, runtime, _ = engine()
        runtime.bad_after_patch = SERVICES[0]
        with self.assertRaisesRegex(JourneyFailure, "not-observed"):
            rollout.run()
        self.assertEqual([s for s, _ in runtime.patches], [SERVICES[0]])

    def test_retry_verifies_installed_services_without_restarting_them(self):
        rollout, runtime, _ = engine()
        rollout.run()
        runtime.patches.clear()
        result = rollout.run()
        self.assertEqual(runtime.patches, [])
        self.assertTrue(all(row["already_configured"] for row in result["baseline"].values()))

    def test_unrelated_change_in_later_service_stops_before_that_patch(self):
        rollout, runtime, _ = engine()
        runtime.drift_after_patch = SERVICES[1]
        with self.assertRaisesRegex(JourneyFailure, "changed-since-preflight"):
            rollout.run()
        self.assertEqual(len(runtime.patches), 1)

    def test_failed_final_recheck_cannot_pass(self):
        rollout, runtime, _ = engine()
        original = runtime.kubectl

        def patch(*args):
            result = original(*args)
            if len(runtime.patches) == 8:
                runtime.deployments[SERVICES[0]]["spec"]["template"]["spec"]["containers"][0]["env"] = []
            return result
        runtime.kubectl = patch
        with self.assertRaisesRegex(JourneyFailure, "final-deployment-drift"):
            rollout.run()

    def test_missing_wrong_or_duplicate_runtime_evidence_rejected(self):
        runtime = Runtime()
        runtime.deployments["account"] = target(runtime.deployments["account"], "account", NAMESPACE)
        for field in ("missing", "gid", "uid", "image", "namespace", "duplicate", "terminating", "ready"):
            pods = runtime.pods("account")
            status = pods[0]["status"]["containerStatuses"][0]
            if field == "missing":
                status.pop("user")
            elif field in {"gid", "uid"}:
                status["user"]["linux"][field] = 0
            elif field == "image":
                status["imageID"] = IMAGES["account"].replace("a" * 64, "b" * 64)
            elif field == "namespace":
                pods[0]["metadata"]["namespace"] = "wrong"
            elif field == "duplicate":
                pods[1] = pods[0]
            elif field == "terminating":
                pods[0]["metadata"]["deletionTimestamp"] = "now"
            else:
                status["ready"] = False
            with self.subTest(field=field), self.assertRaises(JourneyFailure):
                pod_observation(pods, "account", NAMESPACE, IMAGES["account"], corrected=True)

    def test_verifier_rejects_tampering_incomplete_evidence_and_wrong_bindings(self):
        rollout, _, _ = engine()
        result = rollout.run()
        signed = sign(result, KEY, "operator")
        signed["status"] = "invented"
        with self.assertRaisesRegex(JourneyFailure, "signature"):
            verify_observation(signed, KEY, BINDINGS, IMAGES, ENVIRONMENT)
        for field in ("service", "gid", "digest", "ready", "pods", "environment", "complete", "bindings"):
            value = copy.deepcopy(result)
            row = value["services"][SERVICES[0]]
            if field == "service":
                del value["services"][SERVICES[0]]
            elif field == "gid":
                row["startup_gids"] = [0, 0]
            elif field == "digest":
                row["image"] = "registry/app:latest"
            elif field == "ready":
                row["ready_replicas"] = 1
            elif field == "pods":
                row["pod_uid_sha256"] = []
            elif field == "environment":
                value["environment"]["namespace"] = "wrong"
            elif field == "complete":
                value["ms67_complete"] = True
            else:
                value["bindings"] = {}
            with self.subTest(field=field), self.assertRaises(JourneyFailure):
                verify_observation(sign(value, KEY, "operator"), KEY, BINDINGS, IMAGES, ENVIRONMENT)

    def test_deploy_applies_identity_overlay_after_logging(self):
        script = (Path(__file__).resolve().parents[1] / "factory/cloudbank/platform-qualification/gke/deploy.sh").read_text()
        self.assertLess(script.index('cloudbank_log_correlation.py" render'), script.index('cloudbank_runtime_identity.py" render'))
        self.assertIn('apply -f "$output_root/ms67-services-with-runtime-identity.json"', script)

    def test_render_cli_runs_without_cloud_credentials_and_fails_closed(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.json", Path(directory) / "output.json"
            bundle = {"kind": "List", "items": [deployment(s) for s in SERVICES]}
            source.write_text(json.dumps(bundle), encoding="utf-8")
            args = [sys.executable, str(root / "tools/cloudbank_runtime_identity.py"), "render",
                    "--namespace", NAMESPACE, "--bundle", str(source), "--output", str(output)]
            env = {**os.environ, "PYTHONPATH": str(root / "src")}
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text()), instrument_bundle(bundle, NAMESPACE))
            output.unlink()
            bundle["items"].pop()
            source.write_text(json.dumps(bundle), encoding="utf-8")
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            self.assertEqual(json.loads(result.stdout)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
