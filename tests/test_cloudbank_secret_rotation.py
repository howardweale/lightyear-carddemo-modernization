"""Exercise actual scoring contracts, crash recovery and live boundary guards."""
from __future__ import annotations

import base64
import copy
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_data.cloudbank_journeys import JourneyFailure
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.cloudbank_secret_rotation_gke import (
    ANNOTATION, EXTERNAL, GkeSecretBackend, Journal, MARKER, PEPPER, SECRET, SERVICE,
    STATE_TYPE, STORE, SecretRotation, check_score, credit_score, hashed,
    normalized_deployment, normalized_external, rotated_payload, verified,
)
from lightyear_data.contracts import sign


ORIGINAL = {PEPPER: "a" * 64, MARKER: "unchanged-synthetic-marker"}
SUBJECT = "synthetic-credit-client"
KEY = "unit-test-signing-key-only"


class Crash(BaseException):
    pass


class MemoryJournal:
    def __init__(self):
        self.records = []

    def write(self, state):
        self.records.append(copy.deepcopy(state))


class FakeBackend:
    def __init__(self):
        self.r = SimpleNamespace(credentials={"credit": (SUBJECT, "not-a-real-password")})
        self.values = {"1": dict(ORIGINAL)}
        self.states = {"1": "ENABLED"}
        self.latest, self.pinned = "1", None
        self.live = dict(ORIGINAL)
        self.marker, self.pod_generation = None, 0
        self.locked, self.disabled = False, []
        self.actions, self.crash_after = [], None
        self.lose_add_response = False
        self.missing_add_response = False
        self.bad_identity = False

    def done(self, name):
        self.actions.append(name)
        if len(self.actions) == self.crash_after:
            raise Crash(name)

    def guard(self, state):
        if self.bad_identity:
            raise JourneyFailure("secret-rotation-live-identity-or-config-drift")

    def acquire(self, state):
        if self.locked:
            raise JourneyFailure("secret-rotation-lock-held-recovery-required")
        self.locked = True
        self.done("acquire")
        return "lease-uid"

    def owned(self, state):
        if not self.locked:
            raise JourneyFailure("secret-rotation-lock-ownership-mismatch")

    def release(self, state):
        self.owned(state)
        self.locked = False
        self.done("release")

    def version(self, number):
        number = self.latest if number == "latest" else number
        return {"name": "projects/test/secrets/" + SECRET + "/versions/" + number, "state": self.states[number], "etag": number}

    def versions(self):
        return [self.version(n) for n in self.values]

    def payload(self, number):
        if self.states[number] != "ENABLED":
            raise JourneyFailure("version-disabled")
        return copy.deepcopy(self.values[number])

    def add(self, payload):
        if self.missing_add_response:
            raise JourneyFailure("operator-command-unavailable-or-timed-out")
        self.latest = str(int(self.latest) + 1)
        self.values[self.latest], self.states[self.latest] = copy.deepcopy(payload), "ENABLED"
        self.done("add")
        if self.lose_add_response:
            self.lose_add_response = False
            raise JourneyFailure("operator-command-unavailable-or-timed-out")
        return self.latest

    def pin(self, number):
        self.pinned = number
        self.done("pin")

    def sync(self, state, payload):
        selected = self.latest if self.pinned in {None, "latest"} else self.pinned
        if self.payload(selected) != payload:
            raise JourneyFailure("secret-rotation-sync-timeout")
        self.live = copy.deepcopy(payload)

    def rollout(self, marker):
        if marker != self.marker:
            self.pod_generation += 1
        self.marker = marker
        self.done("rollout")

    def observe(self, state, payload, prior=None):
        self.guard(state)
        if self.live != payload:
            raise JourneyFailure("secret-rotation-pod-secret-not-active")
        return {"pod_uid_sha256": [hashed(f"pod-{self.pod_generation}-{i}") for i in range(2)],
                "verified_replicas": 2, "authenticated_contract_matches": True, "different_from_prior": prior is not None}

    def disable(self, number):
        self.states[number] = "DISABLED"
        self.disabled.append(number)
        self.done("disable")


def state():
    return {"state_type": STATE_TYPE, "run_id": "unit-run", "executor_id": "executor-test", "baseline": {
        "original_version": "1", "original_payload_sha256": hashed(ORIGINAL),
        "subject_sha256": hashed(SUBJECT), "original_version_field": {},
        "parent": {"name": "projects/test/secrets/" + SECRET}, "environment": {"namespace": "test"}},
        "recovery_uri": "gs://test-ms67-evidence/secret-rotation/run/state.json", "bindings": {},
        "versions": {}, "version_payloads": {}, "observations": {}, "pending_add": None,
        "lease_uid": None, "cleanup_complete": False}


class RotationTests(unittest.TestCase):
    def make(self):
        backend, journal = FakeBackend(), MemoryJournal()
        return backend, journal, SecretRotation(backend, journal, state())

    def test_rotates_and_restores_without_disabling_preexisting_versions(self):
        backend, journal, engine = self.make()
        result = engine.run(ORIGINAL)
        self.assertEqual(result["status"], "passed-secret-rotation-and-restoration")
        self.assertEqual(backend.values["3"], ORIGINAL)
        self.assertNotEqual(backend.values["2"][PEPPER], ORIGINAL[PEPPER])
        self.assertEqual(backend.values["2"][MARKER], ORIGINAL[MARKER])
        self.assertEqual(backend.states, {"1": "ENABLED", "2": "DISABLED", "3": "ENABLED"})
        self.assertEqual(backend.live, ORIGINAL)
        self.assertIsNone(backend.marker)
        self.assertIsNone(backend.pinned)
        self.assertFalse(backend.locked)
        evidence = json.dumps(journal.records + [result])
        for value in [*ORIGINAL.values(), backend.values["2"][PEPPER], "not-a-real-password", SUBJECT]:
            self.assertNotIn(value, evidence)

    def test_recovery_after_every_acknowledged_mutation_and_lost_response(self):
        complete, _, engine = self.make()
        engine.run(ORIGINAL)
        # The two post-cleanup checkpoints are read-only/idempotent in the CLI.
        for position in range(1, len(complete.actions)):
            with self.subTest(action=position, operation=complete.actions[position - 1]):
                backend, journal, engine = self.make()
                backend.crash_after = position
                with self.assertRaises(Crash):
                    engine.run(ORIGINAL)
                backend.crash_after = None
                recovered = SecretRotation(backend, journal, copy.deepcopy(journal.records[-1]))
                result = recovered.restore()
                self.assertEqual(result["status"], "restored")
                self.assertEqual(backend.live, ORIGINAL)
                self.assertEqual(backend.states["1"], "ENABLED")
                self.assertIsNone(backend.marker)
                self.assertIsNone(backend.pinned)
                self.assertFalse(backend.locked)
                for number in backend.values:
                    if backend.values[number] != ORIGINAL:
                        self.assertEqual(backend.states[number], "DISABLED")

    def test_lost_add_response_is_reconciled_without_duplicate_rotation(self):
        backend, journal, engine = self.make()
        backend.lose_add_response = True
        with self.assertRaises(JourneyFailure):
            engine.run(ORIGINAL)
        self.assertEqual(backend.live, ORIGINAL)  # The numeric pin protected ESO.
        self.assertTrue(engine.state["pending_add"])
        recovered = SecretRotation(backend, journal, copy.deepcopy(journal.records[-1]))
        recovered.restore()
        self.assertEqual(len(backend.values), 3)
        self.assertEqual(backend.disabled, ["2"])

    def test_unresolved_add_keeps_original_behavior_pin_and_lock(self):
        backend, _, engine = self.make()
        backend.missing_add_response = True
        with self.assertRaises(JourneyFailure):
            engine.run(ORIGINAL)
        with self.assertRaisesRegex(JourneyFailure, "add-outcome-uncertain"):
            engine.restore()
        self.assertEqual(backend.live, ORIGINAL)
        self.assertEqual(backend.pinned, "1")
        self.assertTrue(backend.locked)
        self.assertFalse(engine.state["cleanup_complete"])
        self.assertEqual(backend.disabled, [])

    def test_drift_prevents_recovery_mutations(self):
        backend, _, engine = self.make()
        backend.crash_after = 5
        with self.assertRaises(Crash):
            engine.run(ORIGINAL)
        before = copy.deepcopy(backend.actions)
        backend.bad_identity = True
        with self.assertRaisesRegex(JourneyFailure, "identity-or-config-drift"):
            engine.restore()
        self.assertEqual(backend.actions, before)

    def test_concurrent_provider_version_is_never_disabled_or_overwritten(self):
        backend, _, engine = self.make()
        backend.lose_add_response = True
        with self.assertRaises(JourneyFailure):
            engine.run(ORIGINAL)
        other = {**ORIGINAL, PEPPER: "some-other-operators-secret" * 3}
        backend.add(other)
        with self.assertRaisesRegex(JourneyFailure, "unrecognized-provider-version"):
            engine.restore()
        self.assertEqual(backend.payload("3"), other)
        self.assertEqual(backend.disabled, [])
        self.assertEqual(backend.pinned, "1")

    def test_cannot_steal_active_rotation_lock(self):
        backend, journal, engine = self.make()
        backend.locked = True
        with self.assertRaisesRegex(JourneyFailure, "lock-held"):
            engine.run(ORIGINAL)
        self.assertEqual(backend.actions, [])

    def test_checkpoint_failure_prevents_mutation(self):
        backend, journal, engine = self.make()
        with patch.object(journal, "write", side_effect=JourneyFailure("upload-unavailable")):
            with self.assertRaisesRegex(JourneyFailure, "upload-unavailable"):
                engine.run(ORIGINAL)
        self.assertEqual(backend.actions, [])

    def test_latest_alias_can_catch_up_only_to_a_known_version(self):
        backend, _, engine = self.make()
        engine.state["versions"]["rotated"] = "2"
        with patch.object(backend, "version", side_effect=[{"name": "versions/1"}, {"name": "versions/2"}]), \
             patch("lightyear_data.cloudbank_secret_rotation_gke.time.sleep"):
            self.assertEqual(engine.head(), "2")
        with patch.object(backend, "version", return_value={"name": "versions/3"}):
            with self.assertRaisesRegex(JourneyFailure, "head-changed"):
                engine.head()

    def test_restore_does_not_qualify_the_failed_rotation(self):
        backend, _, engine = self.make()
        backend.lose_add_response = True
        with self.assertRaises(JourneyFailure):
            engine.run(ORIGINAL)
        result = engine.observation("recovered-secret-rotation", engine.restore())
        self.assertNotIn("rotated", result["observations"])
        self.assertFalse(result["ms67_complete"])


class ContractTests(unittest.TestCase):
    def test_midnight_and_wrong_secret(self):
        start, end = date(2026, 9, 8), date(2026, 9, 9)
        body = {"Provider": "synthetic-v1", "Date": end.isoformat(),
                "Credit Score": str(credit_score(ORIGINAL[PEPPER], SUBJECT, end.isoformat()))}
        check_score(body, ORIGINAL[PEPPER], SUBJECT, start, end)
        other = rotated_payload(ORIGINAL, SUBJECT, end)
        with self.assertRaisesRegex(JourneyFailure, "not-active"):
            check_score(body, other[PEPPER], SUBJECT, start, end)
        with self.assertRaisesRegex(JourneyFailure, "date-or-provider"):
            check_score(body, ORIGINAL[PEPPER], SUBJECT, start, start)

    def test_rotation_avoids_equal_response_and_preserves_unrelated_key(self):
        today = date(2026, 9, 9)
        with patch("lightyear_data.cloudbank_secret_rotation_gke.secrets.token_hex", side_effect=[ORIGINAL[PEPPER], "b" * 64]):
            payload = rotated_payload(ORIGINAL, SUBJECT, today)
        self.assertEqual(payload[MARKER], ORIGINAL[MARKER])
        self.assertEqual(payload[PEPPER], "b" * 64)
        for day in ("2026-09-08", "2026-09-09", "2026-09-10"):
            self.assertNotEqual(credit_score(payload[PEPPER], SUBJECT, day), credit_score(ORIGINAL[PEPPER], SUBJECT, day))

    def test_score_collision_never_counts_as_rotation(self):
        day = date(2026, 9, 9)
        body = {"Provider": "synthetic-v1", "Date": day.isoformat(),
                "Credit Score": str(credit_score(ORIGINAL[PEPPER], SUBJECT, day.isoformat()))}
        with self.assertRaisesRegex(JourneyFailure, "collision"):
            check_score(body, ORIGINAL[PEPPER], SUBJECT, day, day, ORIGINAL[PEPPER])

    def test_state_hash_and_signature_are_both_required(self):
        value = sign(state(), KEY, "unit-test")
        verified(value, KEY)
        for field in ("run_id", "content_sha256"):
            modified = {**value, field: "tampered"}
            with self.assertRaisesRegex(JourneyFailure, "signature-invalid"):
                verified(modified, KEY)

    def test_normalizers_allow_only_the_owned_fields(self):
        ext = {"spec": {"dataFrom": [{"extract": {"key": SECRET}}], "target": {"name": SECRET}}}
        changed = copy.deepcopy(ext)
        changed["spec"]["dataFrom"][0]["extract"]["version"] = "2"
        self.assertEqual(normalized_external(ext), normalized_external(changed))
        changed["spec"]["target"]["name"] = "some-other-secret"
        self.assertNotEqual(normalized_external(ext), normalized_external(changed))
        deploy = {"spec": {"template": {"metadata": {}, "spec": {"containers": [{"name": SERVICE, "image": "locked"}]}}, "replicas": 2}}
        changed = copy.deepcopy(deploy)
        changed["spec"]["template"]["metadata"]["annotations"] = {ANNOTATION: "our-run"}
        self.assertEqual(normalized_deployment(deploy), normalized_deployment(changed))
        changed["spec"]["replicas"] = 1
        self.assertNotEqual(normalized_deployment(deploy), normalized_deployment(changed))


class JournalTests(unittest.TestCase):
    def test_generation_fences_stale_writer_and_readback_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            remote = {"generation": 0, "body": ""}
            def invoke(argv, **kwargs):
                if argv[1:3] == ["storage", "cp"]:
                    expected = int(next(a.split("=", 1)[1] for a in argv if a.startswith("--if-generation-match=")))
                    if expected != remote["generation"]:
                        raise JourneyFailure("generation-precondition-failed")
                    remote["body"] = Path(argv[3]).read_text(encoding="utf-8")
                    remote["generation"] += 1
                    return ""
                if argv[1:4] == ["storage", "objects", "describe"]:
                    return str(remote["generation"])
                self.assertEqual(argv[3].rsplit("#", 1)[1], str(remote["generation"]))
                return remote["body"]
            uri = "gs://test-ms67-evidence/secret-rotation/run/state.json"
            journal = Journal(Path(directory) / "state.json", uri, "test", KEY, "tester", invoke)
            journal.write(state())
            verified(json.loads(remote["body"]), KEY)
            recovery = Journal(Path(directory) / "recovery.json", uri, "test", KEY, "tester", invoke, generation="1")
            recovery.write({**state(), "executor_id": "new-executor"})
            with self.assertRaisesRegex(JourneyFailure, "generation-precondition-failed"):
                journal.write(state())
            self.assertEqual(journal.generation, "1")

    def test_wrong_readback_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            def invoke(argv, **kwargs):
                return "1" if "describe" in argv else "wrong"
            journal = Journal(Path(directory) / "state.json", "gs://test/secret-rotation/state.json", "test", KEY, "tester", invoke)
            with self.assertRaisesRegex(JourneyFailure, "readback-mismatch"):
                journal.write(state())
            self.assertEqual(journal.generation, "0")


class ProviderBoundaryTests(unittest.TestCase):
    def test_old_executor_cannot_release_recoverys_lock(self):
        current = state()
        current["lease_uid"] = "lease-uid"
        lease = {"metadata": {"name": "lease", "uid": "lease-uid", "resourceVersion": "2",
                "labels": {"app.kubernetes.io/managed-by": "lightyear-secret-rotation"},
                "annotations": {"lightyear.ai/recovery-state": current["recovery_uri"], "lightyear.ai/executor": "new-executor"}},
            "spec": {"holderIdentity": current["run_id"]}}
        backend = GkeSecretBackend(SimpleNamespace())
        with patch.object(backend, "lease", return_value=lease), patch.object(backend, "patch") as mutate:
            with self.assertRaisesRegex(JourneyFailure, "ownership-mismatch"):
                backend.release(current)
        mutate.assert_not_called()

    def test_release_patches_the_exact_snapshot_that_proved_ownership(self):
        current = state()
        current["lease_uid"] = "lease-uid"
        lease = {"metadata": {"name": "lease", "uid": "lease-uid", "resourceVersion": "1",
                "labels": {"app.kubernetes.io/managed-by": "lightyear-secret-rotation"},
                "annotations": {"lightyear.ai/recovery-state": current["recovery_uri"], "lightyear.ai/executor": current["executor_id"]}},
            "spec": {"holderIdentity": current["run_id"]}}
        backend = GkeSecretBackend(SimpleNamespace())
        with patch.object(backend, "lease", return_value=lease) as read, patch.object(backend, "patch") as mutate:
            backend.release(current)
        read.assert_called_once()
        self.assertEqual(mutate.call_args.args[1], lease)
    def test_secret_value_only_enters_stdin(self):
        calls = []
        def invoke(argv, **kwargs):
            calls.append((argv, kwargs))
            if "add" in argv:
                return json.dumps({"name": "projects/test/secrets/" + SECRET + "/versions/2"})
            return json.dumps({"name": "projects/test/secrets/" + SECRET, "createTime": "2026-09-01T00:00:00Z"})
        backend = GkeSecretBackend(SimpleNamespace(project="test"), invoke)
        with patch.object(backend, "owned"):
            self.assertEqual(backend.add(ORIGINAL), "2")
        creation = next(call for call in calls if "add" in call[0])
        self.assertIn("--data-file=-", creation[0])
        self.assertEqual(json.loads(creation[1]["data"]), ORIGINAL)
        for value in ORIGINAL.values():
            self.assertNotIn(value, json.dumps([call[0] for call in calls]))

    def test_disable_uses_numeric_id_and_etag(self):
        calls = []
        backend = GkeSecretBackend(SimpleNamespace(project="test"), lambda argv, **kw: calls.append(argv) or "")
        with patch.object(backend, "owned"), patch.object(backend, "version", side_effect=[
            {"state": "ENABLED", "etag": '"guarded-etag"'}, {"state": "DISABLED"}]):
            backend.disable("2")
        self.assertEqual(calls[0][3:5], ["disable", "2"])
        self.assertIn('"guarded-etag"', calls[0])

    def test_live_secret_must_be_owned_by_expected_external_secret(self):
        value = {"metadata": {"ownerReferences": [{"uid": "other-uid", "controller": True}]},
                 "data": {k: base64.b64encode(v.encode()).decode() for k, v in ORIGINAL.items()}}
        backend = GkeSecretBackend(SimpleNamespace(get=lambda *args: value))
        with self.assertRaisesRegex(JourneyFailure, "owner-mismatch"):
            backend.secret("expected-uid")


class LiveBoundaryTests(unittest.TestCase):
    def setUp(self):
        services = ("azn-server", "customer", "account", "transfer", "checks", "testrunner", "creditscore", "chatbot")
        images = {s: "registry/" + s + "@sha256:" + "a" * 64 for s in services}
        self.runtime = GkeRuntime(project="test", region="us-west1", cluster="test", namespace="test",
                                  run_id="unit-run", output=Path("unused"), images=images)
        ready = {"conditions": [{"type": "Ready", "status": "True"}]}
        self.objects = {}
        for service in services:
            name = "cloudbank-" + service
            self.objects[("externalsecret", name)] = {"metadata": {"name": name, "uid": name + "-uid", "resourceVersion": "1"},
                "spec": {"secretStoreRef": {"kind": "SecretStore", "name": STORE},
                    "target": {"name": name + "-external", "creationPolicy": "Owner"}, "refreshInterval": "1m",
                    "dataFrom": [{"extract": {"key": name + "-external"}}]}, "status": ready}
        self.objects[("secretstore", STORE)] = {"metadata": {"uid": "store-uid"},
            "spec": {"provider": {"gcpsm": {"projectID": "test"}}}, "status": ready}
        self.objects[("configmap", "cloudbank-runtime")] = {"metadata": {"uid": "config-uid"}, "data": {"SAFE_SETTING": "value"}}
        self.objects[("secret", SECRET)] = {"metadata": {"uid": "secret-uid", "ownerReferences": [{"controller": True, "uid": EXTERNAL + "-uid"}]},
            "data": {k: base64.b64encode(v.encode()).decode() for k, v in ORIGINAL.items()}}
        self.objects[("deployment", SERVICE)] = {"metadata": {"name": SERVICE, "uid": "deployment-uid", "resourceVersion": "1"}, "spec": {
            "replicas": 2, "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0}},
            "template": {"metadata": {}, "spec": {"containers": [{"name": SERVICE, "image": images[SERVICE],
                "envFrom": [{"configMapRef": {"name": "cloudbank-runtime"}}, {"secretRef": {"name": SECRET}}]}]}}}}
        self.runtime.get = lambda kind, name: copy.deepcopy(self.objects[(kind, name)])
        self.runtime.environment = lambda: {"namespace_uid_sha256": "test-uid-hash"}
        self.runtime.service_ready = lambda service: None
        self.runtime.secret_json = lambda name: {"AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_ID": SUBJECT,
            "AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_SECRET": "not-a-real-password"}
        self.backend = GkeSecretBackend(self.runtime)
        self.backend.parent = lambda: {"name": "projects/test/secrets/" + SECRET, "createTime": "2026-09-01T00:00:00Z"}
        self.backend.version = lambda number: {"name": "projects/test/secrets/" + SECRET + "/versions/1", "state": "ENABLED"}
        self.backend.payload = lambda number: dict(ORIGINAL)

    def test_mapping_matches_the_live_creditscore_shape(self):
        baseline, original = self.backend.preflight()
        self.assertEqual(original, ORIGINAL)
        current = state()
        current["baseline"] = baseline
        self.backend.guard(current)
        self.assertEqual(baseline["original_version_field"], {})
        self.assertNotIn(PEPPER, json.dumps(baseline))

    def test_bad_provider_override_or_sync_blocks_admission(self):
        mutations = [
            lambda: self.objects[("secretstore", STORE)]["spec"]["provider"]["gcpsm"].update(projectID="other"),
            lambda: self.objects[("deployment", SERVICE)]["spec"]["template"]["spec"]["containers"][0].update(env=[{"name": PEPPER, "value": "override"}]),
            lambda: self.objects[("secret", SECRET)]["data"].update({PEPPER: base64.b64encode(b"wrong" * 20).decode()}),
            lambda: self.objects[("externalsecret", EXTERNAL)]["spec"]["dataFrom"][0]["extract"].update(version="2"),
            lambda: self.objects[("deployment", SERVICE)]["spec"]["template"]["spec"]["containers"][0].update(image="registry/unlocked:latest"),
        ]
        original = copy.deepcopy(self.objects)
        for mutation in mutations:
            self.objects = copy.deepcopy(original)
            mutation()
            with self.assertRaises(JourneyFailure):
                self.backend.preflight()

    def test_recreated_deployment_or_secret_refuses_recovery(self):
        baseline, _ = self.backend.preflight()
        current = {**state(), "baseline": baseline}
        for kind, name in (("deployment", SERVICE), ("secret", SECRET), ("externalsecret", EXTERNAL), ("secretstore", STORE)):
            original_uid = self.objects[(kind, name)]["metadata"]["uid"]
            self.objects[(kind, name)]["metadata"]["uid"] = "recreated"
            with self.subTest(kind=kind), self.assertRaises(JourneyFailure):
                self.backend.guard(current)
            self.objects[(kind, name)]["metadata"]["uid"] = original_uid

    def test_both_owned_pods_are_probed_without_service_fallback(self):
        from datetime import datetime, timezone
        from unittest.mock import MagicMock
        baseline, _ = self.backend.preflight()
        current = {**state(), "baseline": baseline}
        pods = [{"metadata": {"name": "credit-" + str(n), "uid": "pod-" + str(n)}} for n in range(2)]
        self.runtime.pods = lambda service: copy.deepcopy(pods)
        for pod in pods:
            self.objects[("pod", pod["metadata"]["name"])] = pod
        self.runtime.token = lambda role: "ephemeral-token"
        calls = []
        def spawn(argv, **kwargs):
            calls.append(argv)
            process = MagicMock()
            process.poll.return_value = None
            return process
        day = datetime.now(timezone.utc).date().isoformat()
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps({"Date": day, "Provider": "synthetic-v1",
            "Credit Score": str(credit_score(ORIGINAL[PEPPER], SUBJECT, day))}).encode()
        self.runtime.opener = MagicMock()
        self.runtime.opener.open.return_value.__enter__.return_value = response
        with patch("lightyear_data.cloudbank_secret_rotation_gke.subprocess.Popen", side_effect=spawn), \
             patch("lightyear_data.cloudbank_secret_rotation_gke.socket.create_connection"), \
             patch.object(self.runtime, "send", side_effect=AssertionError("must not use Service fallback")):
            observed = self.backend.observe(current, ORIGINAL)
        self.assertEqual(observed["verified_replicas"], 2)
        self.assertEqual(self.runtime.opener.open.call_count, 2)
        self.assertIn("pod/credit-0", calls[0])
        self.assertIn("pod/credit-1", calls[1])
        self.assertNotIn("ephemeral-token", json.dumps(calls))
        self.assertFalse(self.runtime.forwards)


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        import cloudbank_secret_rotation
        cls.cli = cloudbank_secret_rotation

    @classmethod
    def tearDownClass(cls):
        sys.path.pop(0)

    def test_final_observation_verifier_rejects_missing_or_reused_pod_proof(self):
        backend, journal = FakeBackend(), MemoryJournal()
        engine = SecretRotation(backend, journal, state())
        result = engine.run(ORIGINAL)
        self.cli.verify_observation(sign(result, KEY, "tester"), KEY)
        bad = copy.deepcopy(result)
        bad["observations"]["rotated"]["pod_uid_sha256"] = bad["observations"]["baseline"]["pod_uid_sha256"]
        with self.assertRaisesRegex(JourneyFailure, "fresh-replica"):
            self.cli.verify_observation(sign(bad, KEY, "tester"), KEY)
        bad = copy.deepcopy(result)
        bad["observations"]["rotated"]["verified_replicas"] = 1
        with self.assertRaisesRegex(JourneyFailure, "two-replica"):
            self.cli.verify_observation(sign(bad, KEY, "tester"), KEY)

    def test_run_requires_ack_before_loading_secrets_or_running_commands(self):
        import io
        from contextlib import redirect_stdout
        args = ["run", "--project", "test", "--region", "us-west1", "--cluster", "test", "--namespace", "test",
                "--signer", "tester", "--evidence-bucket", "gs://test-ms67-evidence/secret-rotation"]
        with patch.dict("os.environ", {}, clear=True), patch.object(self.cli, "evidence_key") as key, redirect_stdout(io.StringIO()):
            self.assertEqual(self.cli.main(args), 1)
        key.assert_not_called()

    def test_completed_cleanup_is_idempotent(self):
        backend, journal = FakeBackend(), MemoryJournal()
        engine = SecretRotation(backend, journal, state())
        engine.run(ORIGINAL)
        backend.r.get = lambda *args: {"spec": {"dataFrom": [{"extract": {"key": SECRET}}]}}
        backend.r.deployment = lambda service: {"spec": {"template": {"metadata": {}}}}
        backend.lease = lambda: None
        before = copy.deepcopy(backend.actions)
        for _ in range(2):
            self.assertEqual(self.cli.check_restored(engine)["status"], "restored")
        self.assertEqual(backend.actions, before)


if __name__ == "__main__":
    unittest.main()
