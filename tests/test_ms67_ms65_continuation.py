from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
previous = list(sys.path)
sys.path.insert(0, str(ROOT / "tools"))
try:
    spec = importlib.util.spec_from_file_location("ms67_resume_ms65_test", ROOT / "tools/ms67_resume_ms65.py")
    continuation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(continuation)
finally:
    sys.path[:] = previous

BUILD = "12345678-1234-1234-1234-123456789012"
GIT = "gcr.io/cloud-builders/git@sha256:" + "a" * 64
SDK = "gcr.io/google.com/cloudsdktool/google-cloud-cli:573.0.0@sha256:" + "b" * 64


def config():
    substitutions = {
        "_SOURCE_COMMIT": continuation.CONTROLLER, "_REGION": continuation.REGION,
        "_CLUSTER": continuation.CLUSTER, "_NAMESPACE": continuation.NAMESPACE,
        "_SIGNER": continuation.SA, "_EVIDENCE_BUCKET_PREFIX": continuation.BUCKET + "/test",
    }
    for name in ("IMAGE_LOCK", "MS64_RECEIPT", "MS65_ENVIRONMENT", "JOURNEYS", "DATABASE_RECOVERY"):
        substitutions["_" + name + "_URI"] = continuation.BUCKET + "/test/" + name.lower() + ".json"
        substitutions["_" + name + "_SHA256"] = "c" * 64
    return continuation.build_config((ROOT / continuation.TEMPLATE).read_text(), GIT, SDK, substitutions, "test-tag")


def build(value, resolve=False):
    result = {
        "id": BUILD, "projectId": continuation.PROJECT, "serviceAccount": continuation.SA_RESOURCE,
        "substitutions": copy.deepcopy(value["substitutions"]), "tags": value["tags"],
        "availableSecrets": value["availableSecrets"], "steps": copy.deepcopy(value["steps"]),
    }
    if resolve:
        for row in result["steps"]:
            for name in ("args", "env"):
                if name in row:
                    row[name] = continuation.expanded(row[name], value["substitutions"], BUILD)
    return result


class Ms65ContinuationTests(unittest.TestCase):
    def test_canonical_worker_pins_controller_builders_key_and_existing_inputs(self):
        value = config()
        self.assertEqual(3, len(value["steps"]))
        self.assertEqual([GIT, GIT, SDK], [row["name"] for row in value["steps"]])
        self.assertEqual(continuation.CONTROLLER, value["substitutions"]["_SOURCE_COMMIT"])
        self.assertTrue(value["availableSecrets"]["secretManager"][0]["versionName"].endswith("/versions/1"))
        worker = value["steps"][-1]["args"][-1]
        self.assertIn("cloudbank-ms65-rehearsal.sh run", worker)
        self.assertIn("--database-recovery /workspace/inputs/database-recovery.json", worker)
        self.assertNotIn("cloudbank-sql-recovery.sh", worker)
        self.assertNotIn("run-sustained-load.sh", worker)
        self.assertIn("rm -f /workspace/ms65-kubeconfig", worker)
        for resolved in (False, True):
            continuation.verify_build(build(value, resolved), value)

    def test_wrong_worker_source_secret_identity_and_release_are_rejected(self):
        value = config()
        changes = [
            lambda b: b.update(projectId="another-project"),
            lambda b: b.update(serviceAccount="another-account"),
            lambda b: b["substitutions"].update(_SOURCE_COMMIT="d" * 40),
            lambda b: b["substitutions"].update(_DATABASE_RECOVERY_SHA256="e" * 64),
            lambda b: b["steps"][-1].update(args=["-ceu", "echo success"]),
            lambda b: b["steps"][0].update(name="untrusted/git"),
            lambda b: b["availableSecrets"]["secretManager"][0].update(versionName="projects/other/versions/latest"),
        ]
        for mutate in changes:
            with self.subTest(mutation=mutate):
                observed = copy.deepcopy(build(value, True))
                mutate(observed)
                with self.assertRaises(Exception):
                    continuation.verify_build(observed, value)

    def test_canonical_template_shape_and_unused_substitutions_are_rejected(self):
        value = config()
        with self.assertRaises(Exception):
            continuation.build_config("steps: []", GIT, SDK, value["substitutions"], "tag")
        value["substitutions"]["_UNUSED"] = "invalid"
        with self.assertRaises(Exception):
            continuation.build_config((ROOT / continuation.TEMPLATE).read_text(), GIT, SDK, value["substitutions"], "tag")

    def test_resume_adopts_existing_build_without_repeating_uncertain_submission(self):
        self.assertIsNone(continuation.choose_build({"phase": "prepared"}, []))
        self.assertEqual(BUILD, continuation.choose_build({"phase": "submitting"}, [{"id": BUILD}]))
        self.assertEqual(BUILD, continuation.choose_build({"phase": "submitted", "build_id": BUILD}, []))
        self.assertEqual(BUILD, continuation.choose_build({"phase": "verified", "build_id": BUILD}, [{"id": BUILD}]))
        for state, matches in (
            ({"phase": "submitting"}, []),
            ({"phase": "prepared"}, [{"id": BUILD}, {"id": BUILD}]),
            ({"phase": "submitted", "build_id": BUILD}, [{"id": "another"}]),
            ({"phase": "prepared"}, [{"id": "malformed"}]),
        ):
            with self.subTest(state=state, matches=matches), self.assertRaises(Exception):
                continuation.choose_build(state, matches)

    def test_shell_variables_are_preserved_when_build_substitutions_expand(self):
        script = "$$output $" + "{_CLUSTER} $BUILD_ID $$BUILD_ID"
        self.assertEqual("$output cloudbank-ms67 " + BUILD + " $BUILD_ID",
                         continuation.expanded(script, {"_CLUSTER": "cloudbank-ms67"}, BUILD))

    def test_builder_uses_previously_resolved_digest(self):
        previous = {"steps": [{"id": "git", "name": "gcr.io/cloud-builders/git"}],
                    "results": {"buildStepImages": ["sha256:" + "a" * 64]}}
        self.assertEqual(GIT, continuation.builder(previous, "git"))
        previous["results"]["buildStepImages"][0] = "latest"
        with self.assertRaises(Exception):
            continuation.builder(previous, "git")
