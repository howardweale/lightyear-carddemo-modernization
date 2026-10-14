"""Offline tests. Keys are ephemeral test fixtures; no cloud or native processes."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lightyear_cloud_runner.contracts import admission, cleanup_observation, verify_object
from lightyear_cloud_runner.signing import GcpKmsSigner, canonical, crc32c, seal, sha256, verify
from lightyear_cloud_runner.__main__ import load


def key():
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(serialization.Encoding.PEM,
                                           serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, pem


def signed(body, pair):
    return {"body": body, "content_sha256": seal(body),
            "signature": {"algorithm": "Ed25519", "key_id": sha256(pair[1].encode()),
                          "value": base64.b64encode(pair[0].sign(canonical(body))).decode()}}


def ref(data):
    return {"bucket": "unit-only-inputs", "name": "sha256/" + sha256(data),
            "sha256": sha256(data), "size": len(data), "generation": "123"}


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.keys = {scope: {purpose: key() for purpose in ("go", "witness")}
                     for scope in ("engineering", "qualification", "factory")}
        self.now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
        image = {"project": "unit-project", "name": "sealed-image", "id": "987",
                 "build_manifest_sha256": "a" * 64}
        self.policy = {"project": "unit-project", "bucket": "unit-only-inputs", "region": "us-west1",
                       "zones": ["us-west1-a"], "machine_types": ["n2-standard-16"],
                       "images": [image], "commits": ["a" * 40],
                       "keys": {s: {p: k[1] for p, k in keys.items()} for s, keys in self.keys.items()},
                       "min_memory_gib": 30, "min_disk_gib": 60,
                       "max_seconds": 3600, "max_witness_age_seconds": 86400}
        self.witness = signed({"purpose": "cloud-memory-witness", "scope": "engineering",
                               "provider": "gcp", "project": "unit-project", "region": "us-west1",
                               "machine_type": "n2-standard-16", "image": deepcopy(image),
                               "observed_at": "2030-01-01T11:00:00Z", "free_memory_gib": 50,
                               "free_disk_gib": 120}, self.keys["engineering"]["witness"])
        self.request = {"schema": "lightyear.cloud-request.v1", "scope": "engineering",
                        "attempt_id": "unit-attempt-1", "commit": "a" * 40,
                        "project": "unit-project", "data_project": "unit-project",
                        "region": "us-west1", "zone": "us-west1-a", "machine_type": "n2-standard-16",
                        "image": deepcopy(image), "containers": ["example.invalid/twin@sha256:" + "b" * 64],
                        "inputs": [ref(b"input")], "memory_witness": ref(canonical(self.witness)),
                        "not_before": "2030-01-01T12:00:00Z", "deadline": "2030-01-01T15:00:00Z",
                        "max_seconds": 3600}
        self.resign()

    def resign(self):
        self.go = signed({"purpose": "cloud-run-go", "scope": self.request["scope"],
                          "request_sha256": seal(self.request),
                          **{k: self.request[k] for k in ("attempt_id", "commit", "not_before", "deadline")}},
                         self.keys["engineering"]["go"])

    def admit(self):
        return admission(self.request, self.go, self.witness, self.policy, self.now)

    def test_valid_is_only_plan_and_contains_create_only_claim(self):
        plan = self.admit()
        self.assertFalse(plan["execution_enabled"])
        self.assertEqual(plan["mode"], "plan-only")
        self.assertEqual(plan["claim"]["ifGenerationMatch"], 0)
        self.assertFalse(plan["instance"]["external_ip"])

    def test_request_tampering_cannot_reuse_go(self):
        self.request["attempt_id"] = "another-attempt"
        with self.assertRaises(ValueError):
            self.admit()

    def test_even_signed_disallowed_requests_are_refused(self):
        mutations = [
            ("data_project", "other-customer"), ("project", "other-customer"),
            ("scope", "qualification"), ("commit", "b" * 40), ("zone", "us-east1-b"),
            ("machine_type", "n2-standard-32"), ("containers", ["example.invalid/twin:latest"]),
            ("not_before", "2030-01-02T12:00:00Z"), ("deadline", "2030-01-01T12:10:00Z"),
            ("max_seconds", 3601), ("max_seconds", True), ("attempt_id", "../reuse"),
            ("inputs", []),
        ]
        original = deepcopy(self.request)
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                self.request = deepcopy(original)
                self.request[field] = value
                self.resign()
                with self.assertRaises((ValueError, TypeError)):
                    self.admit()

    def test_unpinned_and_wrong_generation_refused(self):
        for field, value in (("generation", "latest"), ("bucket", "other-customer"),
                             ("name", "inputs/source.tar"), ("size", -1)):
            with self.subTest(field=field):
                saved = deepcopy(self.request["inputs"])
                self.request["inputs"][0][field] = value
                self.resign()
                with self.assertRaises(ValueError):
                    self.admit()
                self.request["inputs"] = saved

    def test_image_id_cannot_change_under_same_name(self):
        self.request["image"]["id"] = "988"
        self.resign()
        with self.assertRaises(ValueError):
            self.admit()

    def test_host_stale_wrong_machine_and_low_memory_witness_refused(self):
        original = deepcopy(self.witness["body"])
        for field, value in (("provider", "laptop"), ("observed_at", "2029-01-01T12:00:00Z"),
                             ("machine_type", "laptop"), ("free_memory_gib", 29),
                             ("free_disk_gib", 59), ("free_memory_gib", float("inf"))):
            with self.subTest(field=field):
                body = deepcopy(original)
                body[field] = value
                # Non-finite JSON cannot even be signed.
                with self.assertRaises(ValueError):
                    self.witness = signed(body, self.keys["engineering"]["witness"])
                    self.request["memory_witness"] = ref(canonical(self.witness))
                    self.resign()
                    self.admit()

    def test_keys_may_not_cross_scope_or_purpose(self):
        self.policy["keys"]["qualification"]["go"] = self.policy["keys"]["engineering"]["go"]
        with self.assertRaises(ValueError):
            self.admit()

    def test_unknown_fields_fail_closed(self):
        self.request["run_anyway"] = True
        self.resign()
        with self.assertRaises(ValueError):
            self.admit()

    def test_fetched_bytes_and_generation_are_verified(self):
        r = ref(b"input")
        verify_object(r, r["bucket"], "123", b"input")
        for generation, data in (("124", b"input"), ("123", b"other")):
            with self.assertRaises(ValueError):
                verify_object(r, r["bucket"], generation, data)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "input.json"
            p.write_text('{"project":"first","project":"second"}')
            with self.assertRaises(ValueError):
                load(p)


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.pair = key()
        self.version = "projects/unit/locations/us-west1/keyRings/unit/cryptoKeys/go/cryptoKeyVersions/1"
        self.requests = []

    def transport(self, url, payload):
        self.requests.append((url, payload))
        data = base64.b64decode(payload["data"])
        self.assertEqual(payload["dataCrc32c"], str(crc32c(data)))
        signature = self.pair[0].sign(data)
        return {"name": self.version, "protectionLevel": "SOFTWARE", "verifiedDataCrc32c": True,
                "signature": base64.b64encode(signature).decode(),
                "signatureCrc32c": str(crc32c(signature))}

    def test_crc_known_vector(self):
        self.assertEqual(crc32c(b"123456789"), 0xE3069283)

    def test_raw_bytes_signature_can_be_verified_without_cloud(self):
        signer = GcpKmsSigner(self.version, "engineering", self.pair[1], self.transport)
        body = {"purpose": "cloud-run-go", "scope": "engineering", "message": "test"}
        self.assertEqual(verify(signer.sign(body), self.pair[1]), body)
        self.assertNotIn("digest", self.requests[0][1])

    def test_response_corruption_and_wrong_key_fail_closed(self):
        for field, value in (("name", self.version + "2"), ("verifiedDataCrc32c", False),
                             ("signatureCrc32c", "0"), ("protectionLevel", "HSM"),
                             ("signature", base64.b64encode(b"x" * 64).decode())):
            with self.subTest(field=field):
                def corrupt(url, payload):
                    result = self.transport(url, payload)
                    result[field] = value
                    return result
                signer = GcpKmsSigner(self.version, "engineering", self.pair[1], corrupt)
                with self.assertRaises(ValueError):
                    signer.sign({"scope": "engineering", "purpose": "cloud-run-go"})

    def test_scope_refused_before_transport(self):
        signer = GcpKmsSigner(self.version, "engineering", self.pair[1], self.transport)
        with self.assertRaises(ValueError):
            signer.sign({"scope": "qualification", "purpose": "cloud-run-go"})
        self.assertEqual(self.requests, [])

    def test_version_alias_refused(self):
        with self.assertRaises(ValueError):
            GcpKmsSigner(self.version.rsplit("/", 1)[0] + "/latest",
                         "engineering", self.pair[1], self.transport)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.operation = {"status": "DONE", "operationType": "delete", "project": "unit",
                          "targetId": "123", "completed_at": "2030-01-01T13:00:00Z"}
        self.pages = [{"project": "unit", "kind": kind, "request_page_token": "",
                       "next_page_token": "", "items": [], "observed_at": "2030-01-01T13:01:00Z"}
                      for kind in ("instances", "disks")]

    def check(self):
        return cleanup_observation("unit-attempt", "unit", "123", ["456"], self.pages, self.operation)

    def test_complete_observation_is_not_independent_attestation(self):
        self.assertTrue(self.check()["cleanup_complete"])
        self.assertIn("not independent", self.check()["claim"])

    def test_missing_pages_resources_errors_and_stale_observations_refused(self):
        for field, value in (("next_page_token", "page-2"), ("unreachable", ["zone-a"]),
                             ("warnings", ["partial"]), ("observed_at", "2030-01-01T12:00:00Z"),
                             ("items", [{"id": "123"}])):
            with self.subTest(field=field):
                original = deepcopy(self.pages)
                self.pages[0][field] = value
                with self.assertRaises(ValueError):
                    self.check()
                self.pages = original
        self.pages[1]["items"] = [{"id": "456"}]
        with self.assertRaises(ValueError):
            self.check()

    def test_failed_delete_and_wrong_target_refused(self):
        for field, value in (("status", "RUNNING"), ("error", {"code": 403}), ("targetId", "other")):
            with self.subTest(field=field):
                original = deepcopy(self.operation)
                self.operation[field] = value
                with self.assertRaises(ValueError):
                    self.check()
                self.operation = original

    def test_all_pages_and_both_inventories_required(self):
        self.pages[0]["next_page_token"] = "second"
        self.pages.insert(1, {**self.pages[0], "request_page_token": "second", "next_page_token": ""})
        self.assertTrue(self.check()["cleanup_complete"])
        self.pages.pop()
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
