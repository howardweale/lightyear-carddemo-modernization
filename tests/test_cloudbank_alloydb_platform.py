"""Managed platform adapters must never silently use the Cloud SQL target."""
import json
import unittest
from unittest.mock import Mock

from lightyear_data.cloudbank_journeys import JourneyFailure
from lightyear_data.cloudbank_secret_rotation_gke import GkeSecretBackend, SECRET
from lightyear_data.cloudbank_ms67_drills import CandidateRuntime
from lightyear_data.cloudbank_managed_target import ManagedGkeRuntime


class ManagedPlatformTests(unittest.TestCase):
    def test_provider_secret_is_separate_from_kubernetes_target_secret(self):
        runtime = Mock(project="test-project")
        invoke = Mock(return_value=json.dumps({"name": "projects/test-project/secrets/isolated-credit", "createTime": "now"}))
        backend = GkeSecretBackend(runtime, invoke, provider_secret="isolated-credit")
        self.assertEqual(backend.parent()["name"], "projects/test-project/secrets/isolated-credit")
        self.assertIn("isolated-credit", invoke.call_args.args[0])
        self.assertNotIn(SECRET, invoke.call_args.args[0])
        runtime.get.return_value = {"metadata": {"ownerReferences": [{"uid": "owner", "controller": True}]}, "data": {}}
        backend.secret("owner")
        runtime.get.assert_called_once_with("secret", SECRET)

    def test_invalid_provider_secret_is_rejected_before_access(self):
        invoke = Mock()
        with self.assertRaisesRegex(JourneyFailure, "provider-secret-invalid"):
            GkeSecretBackend(Mock(), invoke, provider_secret="--other-project")
        invoke.assert_not_called()

    def test_cutover_candidate_uses_deployed_namespace_credentials(self):
        self.assertTrue(issubclass(CandidateRuntime, ManagedGkeRuntime))

    def test_ha_requires_changed_zone_and_unchanged_database_identity(self):
        from lightyear_data.cloudbank_alloydb_ha import AlloyHa, AlloyHaRuntime
        self.assertTrue(issubclass(AlloyHaRuntime, ManagedGkeRuntime))
        drill = object.__new__(AlloyHa)
        before = {"active_zone": "us-west1-a", "instance_uid": "original", "private_ip": "10.1.2.3"}
        drill.state = {"source_profile": before}
        drill.profile = Mock(return_value=dict(before))
        with self.assertRaisesRegex(JourneyFailure, "zone-promotion-or-endpoint-invalid"):
            drill.promoted()
        drill.profile.return_value = {**before, "active_zone": "us-west1-b", "instance_uid": "replacement"}
        with self.assertRaisesRegex(JourneyFailure, "zone-promotion-or-endpoint-invalid"):
            drill.promoted()
        drill.profile.return_value = {**before, "active_zone": "us-west1-b"}
        self.assertEqual(drill.promoted()["instance_uid"], "original")

    def test_managed_network_evidence_must_bind_the_actual_probe_address(self):
        from test_cloudbank_network_enforcement import engine, KEY, BINDINGS, IMAGES, ENV, ARTIFACT
        from lightyear_data.cloudbank_network_enforcement import verify_observation
        from lightyear_data.cloudbank_journeys import hashed
        from lightyear_data.contracts import seal, sign
        run, _, _ = engine()
        value = run.run()
        bindings = {**BINDINGS, "managed_target_profile_sha256": "a" * 64}
        value["bindings"] = bindings
        value["managed_target"] = seal({"profile_sha256": "a" * 64, "images_sha256": hashed(IMAGES),
            "environment": ENV, "database": seal({"address": run.s["database_ip"]})})
        verify_observation(sign(value, KEY, "operator"), KEY, bindings, IMAGES, ENV, ARTIFACT)
        value["managed_target"]["database"] = seal({"address": "10.99.99.99"})
        value["managed_target"] = seal(value["managed_target"])
        with self.assertRaisesRegex(JourneyFailure, "managed-database-probes-mismatch"):
            verify_observation(sign(value, KEY, "operator"), KEY, bindings, IMAGES, ENV, ARTIFACT)
