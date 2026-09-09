import base64
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from lightyear_data.cloudbank_image_security import (
    ImageScanner, OBSERVATION_FILE, OBSERVATION_TYPE, PASS, SOURCE_URI,
    child_environment, database_summary, documents, execute_tool,
    install_credential_helper, provenance_summary, scan_summary, sha,
    signature_summary, stamp, verify_observation,
)
from lightyear_data.cloudbank_journeys import JourneyFailure, SERVICES, hashed
from lightyear_data.contracts import sign, verify_signature


KEY = "unit-test-key-not-a-live-credential"
COMMIT = "1" * 40
ENVIRONMENT = {"project": "test-project", "region": "us-west1", "cluster": "test-cluster", "namespace": "test-namespace"}
IMAGES = {s: f"us-west1-docker.pkg.dev/test-project/cloudbank-ms67/{s}@sha256:" + sha(s) for s in SERVICES}
PROFILE = {"cluster_uid_sha256": "c" * 64, "namespace_uid_sha256": sha("namespace-uid"),
           "context": "test-context", "namespace": "test-namespace", "region": "us-west1",
           "provider": "google-gke-standard-regional", "content_sha256": "f" * 64}
BINDINGS = {"image_lock_sha256": "a" * 64, "ms64_receipt_sha256": "b" * 64, "platform_profile_sha256": "f" * 64}
START, SCANNED, END = "2026-09-09T00:00:00Z", "2026-09-09T00:00:01Z", "2026-09-09T00:00:10Z"


def signature(image):
    return {"critical": {"image": {"docker-manifest-digest": image.split("@")[1]},
                         "identity": {"docker-reference": image.split("@")[0]}}}


def statement(image, service):
    return {"_type": "https://in-toto.io/Statement/v0.1", "predicateType": "https://slsa.dev/provenance/v0.2",
            "subject": [{"name": image.split("@")[0], "digest": {"sha256": image.split("sha256:")[1]}}],
            "predicate": {"builder": {"id": "lightyear-ms67-operator"}, "buildType": "https://lightyear.ai/cloudbank/ms67",
                          "invocation": {"parameters": {"service": service}},
                          "materials": [{"uri": SOURCE_URI, "digest": {"sha1": COMMIT}},
                                        {"uri": image, "digest": {"sha256": image.split("sha256:")[1]}}]}}


def envelope(value):
    return {"payloadType": "application/vnd.in-toto+json", "payload": base64.b64encode(json.dumps(value).encode()).decode()}


def report(image):
    return {"SchemaVersion": 2, "ArtifactName": image, "ArtifactType": "container_image",
            "Metadata": {"RepoDigests": [image], "ImageConfig": {"architecture": "amd64", "os": "linux"}},
            "Results": [{"Class": "os-pkgs", "Type": "ubuntu", "Packages": [{"Name": "libc6", "Version": "2.39"}]},
                        {"Class": "lang-pkgs", "Type": "jar", "Packages": [{"Name": "org.example:test", "Version": "1.0"}]}]}


def databases():
    return {name: {"version": version, "updated_at": START, "next_update": "2026-09-10T00:00:00Z", "metadata_sha256": "d" * 64}
            for name, version in (("db", 2), ("java-db", 1))}


def fixture():
    rows = []
    for service, image in IMAGES.items():
        scan = scan_summary(json.dumps(report(image)), image)
        scan.update(observed_at=SCANNED, databases=databases())
        rows.append({"service": service, "image": image, "status": "passed",
                     "signature": signature_summary(json.dumps([signature(image)]), image),
                     "provenance": provenance_summary(json.dumps(envelope(statement(image, service))), image, service, COMMIT),
                     "scan": scan})
    live = {s: {"image": IMAGES[s], "ready_replicas": 2, "pod_identity_sha256": sha(s)} for s in SERVICES}
    return {"observation_type": OBSERVATION_TYPE, "schema_version": "1.0", "status": PASS,
            "run_id": "ms67-images-" + "2" * 32, "images": IMAGES, "bindings": BINDINGS, "source_commit": COMMIT,
            "environment": {**ENVIRONMENT, "namespace_uid_sha256": hashed("namespace-uid")},
            "cluster_identity_sha256": PROFILE["cluster_uid_sha256"], "profile_namespace_uid_sha256": PROFILE["namespace_uid_sha256"],
            "started_at": START, "finished_at": END, "application_mutations": 0, "credentials_persisted": False,
            "raw_output_persisted": False, "production_environment": False, "ms67_complete": False, "production_ready": False,
            "verification_key": {"version": "projects/test-project/locations/us-west1/keyRings/cloudbank-ms67/cryptoKeys/image-signing/cryptoKeyVersions/1",
                                 "algorithm": "EC_SIGN_P256_SHA256", "project_number": "123456", "public_key_sha256": "e" * 64},
            "tools": {n: {"version": v, "output_sha256": sha(n)} for n, v in (("cosign", "v3.1.2"), ("trivy", "0.74.0"))},
            "services": rows, "live": {"before": copy.deepcopy(live), "after": copy.deepcopy(live)},
            "deployment_specs_before": {s: sha(s) for s in SERVICES}, "deployment_specs_after": {s: sha(s) for s in SERVICES}}


def verify(value):
    return verify_observation(value, KEY, IMAGES, BINDINGS, COMMIT, ENVIRONMENT, PROFILE)


class ClaimTests(unittest.TestCase):
    def test_signature_array_and_attestation_json_stream_bind_exact_image(self):
        service = SERVICES[0]; image = IMAGES[service]
        self.assertEqual(signature_summary(json.dumps([signature(image)]), image)["count"], 1)
        raw = json.dumps(envelope(statement(image, service)))
        self.assertEqual(provenance_summary(raw + "\n" + raw, image, service, COMMIT)["count"], 2)

    def test_empty_or_noisy_verified_output_rejected(self):
        for raw in ("", "[]", "{}\nerror", "null", "[false]"):
            with self.subTest(raw=raw), self.assertRaises(JourneyFailure):
                documents(raw)

    def test_valid_signature_for_different_digest_or_repository_rejected(self):
        image = IMAGES[SERVICES[0]]
        for other in (image.replace(sha(SERVICES[0]), "9" * 64), image.replace("test-project", "other-project")):
            with self.subTest(image=other), self.assertRaises(JourneyFailure):
                signature_summary(json.dumps([signature(other)]), image)

    def test_provenance_cannot_relabel_subject_service_builder_or_source(self):
        service = SERVICES[0]; image = IMAGES[service]
        changes = (
            lambda v: v["subject"][0]["digest"].update(sha256="9" * 64),
            lambda v: v["predicate"]["materials"][0]["digest"].update(sha1="0" * 40),
            lambda v: v["predicate"]["invocation"]["parameters"].update(service="other-service"),
            lambda v: v["predicate"]["builder"].update(id="unapproved-builder"),
            lambda v: v["predicate"]["materials"].append(v["predicate"]["materials"][0]),
            lambda v: v.update(predicateType="https://example.invalid/unknown"),
        )
        for change in changes:
            value = statement(image, service); change(value)
            with self.subTest(value=value), self.assertRaises(JourneyFailure):
                provenance_summary(json.dumps(envelope(value)), image, service, COMMIT)

    def test_unfixed_high_findings_remain_blocking_and_raw_details_are_not_retained(self):
        image = IMAGES[SERVICES[0]]; value = report(image)
        value["Results"][1]["Vulnerabilities"] = [{"VulnerabilityID": "CVE-2026-1234", "Severity": "HIGH",
                                                   "FixedVersion": "", "Description": "not-for-evidence", "PkgName": "private-package"}]
        result = scan_summary(json.dumps(value), image)
        self.assertEqual(result["high"], 1)
        self.assertEqual(result["finding_ids"], [{"severity": "HIGH", "id": "CVE-2026-1234"}])
        self.assertNotIn("not-for-evidence", json.dumps(result))
        self.assertNotIn("private-package", json.dumps(result))

    def test_scan_requires_correct_digest_platform_and_both_package_classes(self):
        image = IMAGES[SERVICES[0]]
        changes = (
            lambda v: v.update(Results=[]), lambda v: v["Results"].pop(1), lambda v: v["Results"].pop(0),
            lambda v: v["Results"][1].update(Packages=[None]),
            lambda v: v["Metadata"].update(RepoDigests=[]), lambda v: v.update(ArtifactName="mutable:tag"),
            lambda v: v["Metadata"]["ImageConfig"].update(architecture="arm64"),
            lambda v: v["Results"][1].update(ExperimentalModifiedFindings=[{"Status": "not_affected"}]),
        )
        for change in changes:
            value = report(image); change(value)
            with self.subTest(value=value), self.assertRaises(JourneyFailure):
                scan_summary(json.dumps(value), image)

    def test_missing_stale_or_wrong_schema_database_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, version in (("db", 2), ("java-db", 1)):
                (root / name).mkdir()
                (root / name / "metadata.json").write_text(json.dumps({"Version": version, "UpdatedAt": START, "NextUpdate": END}))
            self.assertEqual(set(database_summary(root, SCANNED)), {"db", "java-db"})
            for metadata in ({"Version": 1, "UpdatedAt": START, "NextUpdate": START},
                             {"Version": 1, "UpdatedAt": END, "NextUpdate": END}, {"Version": 99}):
                (root / "java-db/metadata.json").write_text(json.dumps(metadata))
                with self.assertRaises(JourneyFailure):
                    database_summary(root, SCANNED)
            (root / "java-db/metadata.json").unlink()
            with self.assertRaises(JourneyFailure):
                database_summary(root, SCANNED)


class CommandTests(unittest.TestCase):
    def test_failed_process_cannot_pass_using_stdout_and_does_not_leak_stderr(self):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, b'{"status":"passed"}', b"sensitive-token")):
            with self.assertRaisesRegex(JourneyFailure, "image-security-tool-failed-cosign-exit-1") as raised:
                execute_tool(["cosign", "verify"], workspace=Path.cwd(), env={})
            self.assertNotIn("sensitive-token", str(raised.exception))

    def test_scanner_ignores_environment_suppression_and_passes_token_only_in_memory(self):
        image = IMAGES[SERVICES[0]]
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "TRIVY_IGNORE_UNFIXED": "true", "COSIGN_REPOSITORY": "wrong.example", "LIGHTYEAR_TEST_SECRET": KEY,
            "DOCKER_CONFIG": "operator-config", "MS67_REGISTRY_ACCESS_TOKEN": "old-token"}):
            root = Path(directory)
            env = child_environment(root, "synthetic-token", "us-west1-docker.pkg.dev")
            self.assertFalse(any(k in env for k in ("TRIVY_IGNORE_UNFIXED", "COSIGN_REPOSITORY", "LIGHTYEAR_TEST_SECRET")))
            run = Mock(return_value=json.dumps(report(image)))
            scanner = ImageScanner("test-project", "us-west1", root, invoke=Mock(return_value="synthetic-token"), run=run)
            with patch("lightyear_data.cloudbank_image_security.database_summary", return_value=databases()):
                scanner.scan(image)
            argv = run.call_args.args[0]
            self.assertNotIn("synthetic-token", " ".join(argv))
            self.assertIn("--ignore-unfixed=false", argv)
            self.assertIn("--list-all-pkgs", argv)
            self.assertEqual(run.call_args.kwargs["env"]["MS67_REGISTRY_ACCESS_TOKEN"], "synthetic-token")
            self.assertNotIn("TRIVY_PASSWORD", run.call_args.kwargs["env"])
            for path in root.rglob("*"):
                if path.is_file():
                    self.assertNotIn(b"synthetic-token", path.read_bytes())

    def test_native_helper_launches_without_shell_and_rejects_other_hosts_and_mutations(self):
        try:
            import distlib  # noqa: F401
        except ImportError:
            if os.name == "nt":
                self.fail("Windows CI must install the pinned distlib dependency")
            self.skipTest("native launcher integration runs in the Windows CI gate")
        with tempfile.TemporaryDirectory(prefix="ms67 helper path ") as directory:
            root = Path(directory); (root / "docker").mkdir()
            install_credential_helper(root, "us-west1-docker.pkg.dev")
            exe = root / "helpers" / ("docker-credential-lightyear-ms67.exe" if os.name == "nt" else "docker-credential-lightyear-ms67")
            env = child_environment(root, "synthetic-token", "us-west1-docker.pkg.dev")
            result = subprocess.run([str(exe), "get"], input="us-west1-docker.pkg.dev\n", capture_output=True,
                                    text=True, env=env, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"Username": "oauth2accesstoken", "Secret": "synthetic-token"})
            for action, host in (("get", "other.example"), ("store", "us-west1-docker.pkg.dev"), ("erase", "us-west1-docker.pkg.dev")):
                result = subprocess.run([str(exe), action], input=host + "\n", capture_output=True, text=True, env=env, timeout=30)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("synthetic-token", result.stdout + result.stderr)
            for path in root.rglob("*"):
                if path.is_file():
                    self.assertNotIn(b"synthetic-token", path.read_bytes())


class ObservationTests(unittest.TestCase):
    def test_signed_complete_observation_verifies(self):
        verify(sign(fixture(), KEY, "unit-test-operator"))

    def test_tampering_breaks_signature(self):
        value = sign(fixture(), KEY, "unit-test-operator")
        value["source_commit"] = "0" * 40
        with self.assertRaisesRegex(JourneyFailure, "signature-invalid"):
            verify(value)

    def test_signature_does_not_replace_completeness_or_binding_checks(self):
        changes = (
            lambda v: v["services"].pop(), lambda v: v["services"][0]["scan"].update(high=1),
            lambda v: v["services"][0]["scan"]["coverage"].update(java_packages=0),
            lambda v: v["services"][0]["scan"]["databases"]["java-db"].update(next_update=START),
            lambda v: v["services"][0]["provenance"].update(source_commit="0" * 40),
            lambda v: v["services"][0]["signature"].update(verified=False),
            lambda v: v["services"][0]["scan"]["severity_counts"].update(HIGH=3),
            lambda v: v["services"][0]["scan"].update(observed_at="2025-09-09T00:00:00Z"),
            lambda v: v["bindings"].update(image_lock_sha256="0" * 64),
            lambda v: v.update(profile_namespace_uid_sha256="0" * 64),
            lambda v: v["environment"].update(project="other-project"),
            lambda v: v["deployment_specs_after"].update(account="0" * 64),
            lambda v: v["live"]["after"]["account"].update(ready_replicas=1),
            lambda v: v.update(ms67_complete=True), lambda v: v.update(production_ready=True),
            lambda v: v["tools"].update(cosign={}), lambda v: v["verification_key"].update(version="other-key"),
        )
        for i, change in enumerate(changes):
            value = copy.deepcopy(fixture()); change(value)
            with self.subTest(case=i), self.assertRaises(JourneyFailure):
                verify(sign(value, KEY, "unit-test-operator"))


class WorkflowTests(unittest.TestCase):
    def exercise(self, *, finding=False, upload_failure=False):
        root = Path(__file__).resolve().parents[1]
        with patch.object(sys, "path", [str(root / "tools"), *sys.path]):
            spec = importlib.util.spec_from_file_location("ms67_image_security_cli_test", root / "tools/cloudbank_image_security.py")
            cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        observed = fixture()
        runtime = Mock(context="test-context")
        runtime.environment.return_value = observed["environment"]
        runtime.get.return_value = {"metadata": {"uid": "namespace-uid"}}
        runtime.service_ready.side_effect = lambda s: observed["live"]["before"][s]
        runtime.deployment.side_effect = lambda s: {"metadata": {"uid": s}, "spec": {"replicas": 2, "image": IMAGES[s]}}
        scanner = Mock()
        scanner.prepare.return_value = (observed["tools"], observed["verification_key"])
        scanner.signature.side_effect = lambda image: signature_summary(json.dumps([signature(image)]), image)
        scanner.provenance.side_effect = lambda image, s, commit: provenance_summary(json.dumps(envelope(statement(image, s))), image, s, commit)
        def scan(image):
            value = scan_summary(json.dumps(report(image)), image)
            value.update(observed_at=stamp(), databases=databases())
            now = datetime.now(timezone.utc)
            for db in value["databases"].values():
                db.update(updated_at=(now - timedelta(days=1)).isoformat(), next_update=(now + timedelta(days=1)).isoformat())
            if finding and image == IMAGES[SERVICES[0]]:
                value["high"] = 1
            return value
        scanner.scan.side_effect = scan
        class FakeJournal:
            def __init__(self, path, *args):
                self.path = path
            def write(self, value):
                if upload_failure and value.get("status") == PASS:
                    raise JourneyFailure("test-independent-readback-failed")
                signed = sign(value, KEY, "unit-test-operator")
                self.path.write_text(json.dumps(signed), encoding="utf-8")
                return signed
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory); output = work / "output"
            inputs = ({"content_sha256": BINDINGS["image_lock_sha256"], "images": [{"service": s, "reference": IMAGES[s]} for s in SERVICES]},
                      {"content_sha256": BINDINGS["ms64_receipt_sha256"]}, PROFILE)
            args = ["run", "--output-root", str(output), "--signer", "unit-test-operator", "--build-source-commit", COMMIT,
                    "--evidence-bucket", "gs://test-project-ms67-evidence/image-security"]
            for k, v in ENVIRONMENT.items():
                args.extend(["--" + k, v])
            for name, data in zip(("image-lock", "ms64-receipt", "platform-profile"), inputs):
                path = work / (name + ".json"); path.write_text(json.dumps(data))
                args.extend(["--" + name, str(path)])
            with patch.multiple(cli, evidence_key=Mock(return_value=KEY), validate_ms64=Mock(return_value=[]),
                                validate_image_lock=Mock(return_value=[]), validate_profile=Mock(return_value=[]),
                                cluster_identity=Mock(return_value=PROFILE["cluster_uid_sha256"]),
                                GkeRuntime=Mock(return_value=runtime), ImageScanner=Mock(return_value=scanner), Journal=FakeJournal), \
                    patch("sys.stdout", new_callable=io.StringIO) as stdout:
                code = cli.main(args)
                result = json.loads((output / OBSERVATION_FILE).read_text())
                self.assertEqual(scanner.scan.call_count, 8)
                self.assertTrue(verify_signature(result, KEY))
                if not finding and not upload_failure:
                    verify(result)
                    self.assertEqual(cli.main(["verify", *args[1:], "--observation", str(output / OBSERVATION_FILE)]), 0)
                else:
                    self.assertEqual(result["status"], "failed")
                    self.assertNotIn("MS67_IMAGE_SECURITY_OBSERVATION=", stdout.getvalue())
                return code, result

    def test_complete_run_and_independent_verifier(self):
        self.assertEqual(self.exercise()[0], 0)

    def test_all_eight_scanned_before_findings_fail_the_run(self):
        code, result = self.exercise(finding=True)
        self.assertEqual(code, 1)
        self.assertEqual(result["reason"], "image-security-high-or-critical-findings")

    def test_success_cannot_be_printed_when_final_readback_fails(self):
        code, result = self.exercise(upload_failure=True)
        self.assertEqual(code, 1)
        self.assertEqual(result["reason"], "test-independent-readback-failed")


if __name__ == "__main__":
    unittest.main()
