"""Preserve complete image configs and retry only a verified failed pre-drill build."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from test_ms67_finish import Cloud, COMMIT, KEY, RUN, IMAGES, BINDINGS, finish, images_tool
from lightyear_data.cloudbank_journeys import JourneyFailure, hashed


def add(stream, name, raw):
    info = tarfile.TarInfo(name)
    info.size = len(raw)
    stream.addfile(info, io.BytesIO(raw))


def archive_fixture(directory, *, modern=False):
    layer = io.BytesIO()
    with tarfile.open(fileobj=layer, mode="w") as out:
        add(out, "marker", b"unchanged filesystem\n")
    layer = layer.getvalue()
    config = {"architecture": "amd64", "os": "linux", "created": "2026-09-10T00:00:00Z",
              "config": {"Env": ["MODE=synthetic"], "Cmd": ["argument"], "Entrypoint": ["/nonexistent"],
                         "User": "65532:65532", "WorkingDir": "/app", "Labels": {"keep": "this"},
                         "Image": "sha256:" + "9"*64, "Hostname": "retained-host", "Domainname": "",
                         "AttachStdin": False, "AttachStdout": False, "AttachStderr": False,
                         "Tty": False, "OpenStdin": False, "StdinOnce": False, "ArgsEscaped": True,
                         "OnBuild": None, "Volumes": None, "StopSignal": "SIGTERM",
                         "Healthcheck": {"Test": ["NONE"]}, "ExposedPorts": {"8080/tcp": {}}},
              "rootfs": {"type": "layers", "diff_ids": ["sha256:" + hashlib.sha256(layer).hexdigest()]},
              "history": [{"created_by": "retained baseline"}], "container_config": {"Image": "kept"}}
    raw = json.dumps(config).encode()
    digest = hashlib.sha256(raw).hexdigest()
    name = "blobs/sha256/" + digest if modern else digest + ".json"
    layer_name = "blobs/sha256/" + hashlib.sha256(layer).hexdigest() if modern else "layer/layer.tar"
    source = directory / "base.tar"
    with tarfile.open(source, "w") as out:
        add(out, name, raw)
        add(out, layer_name, layer)
        add(out, "manifest.json", json.dumps([{"Config": name, "RepoTags": ["ms67-config-test:base"], "Layers": [layer_name]}]).encode())
        if modern:
            add(out, "index.json", b'{"manifests":[{"digest":"old"}]}')
            add(out, "oci-layout", b'{"imageLayoutVersion":"1.0.0"}')
    return source, config, "sha256:" + digest, layer_name, layer


class ArchiveTests(unittest.TestCase):
    def test_complete_config_and_layer_bytes_preserved_for_both_archive_layouts(self):
        for modern in (False, True):
            with self.subTest(modern=modern), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source, original, digest, layer_name, layer = archive_fixture(root, modern=modern)
                target = root / "candidate.tar"
                revised_digest = images_tool.revise_archive(source, target, "ms67-config-test:candidate", RUN, digest)
                with tarfile.open(target) as stream:
                    manifest = json.load(stream.extractfile("manifest.json"))[0]
                    raw = stream.extractfile(manifest["Config"]).read()
                    revised = json.loads(raw)
                    self.assertEqual(revised_digest, "sha256:" + hashlib.sha256(raw).hexdigest())
                    self.assertEqual(revised["config"]["Labels"].pop(images_tool.REVISION_LABEL), RUN)
                    self.assertEqual(revised, original)
                    self.assertEqual(stream.extractfile(layer_name).read(), layer)
                    self.assertEqual(manifest["RepoTags"], ["ms67-config-test:candidate"])
                    self.assertNotIn("index.json", stream.getnames())

    def test_wrong_baseline_digest_and_linked_layer_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, _, digest, layer_name, _ = archive_fixture(root)
            with self.assertRaisesRegex(JourneyFailure, "digest-mismatch"):
                images_tool.revise_archive(source, root/"candidate.tar", "test:candidate", RUN, "sha256:"+"0"*64)
            with tarfile.open(source, "a") as stream:
                info = tarfile.TarInfo("evil")
                info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                stream.addfile(info)
            with tarfile.open(source) as stream:
                parts = [(m, stream.extractfile(m).read() if m.isfile() else None) for m in stream]
            with tarfile.open(source, "w") as stream:
                for m, raw in parts:
                    if m.name == "manifest.json":
                        value = json.loads(raw); value[0]["Layers"] = ["evil"]
                        raw = json.dumps(value).encode(); m.size = len(raw)
                    stream.addfile(m, io.BytesIO(raw) if raw is not None else None)
            with self.assertRaisesRegex(JourneyFailure, "relative-image-member"):
                images_tool.revise_archive(source, root/"candidate.tar", "test:candidate", RUN, digest)

    @unittest.skipUnless(os.environ.get("LIGHTYEAR_MS67_DOCKER_TEST") == "1", "real Docker round trip runs in CI")
    def test_real_docker_load_preserves_settings_and_strict_proof(self):
        def docker(*args):
            return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, timeout=180).stdout
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, _, _, _, _ = archive_fixture(root)
            try:
                docker("load", "--input", str(source))
                base = json.loads(docker("inspect", "ms67-config-test:base"))[0]
                # Exercise a real daemon export, not only our fixture layout.
                saved = root / "saved.tar"
                docker("save", "--output", str(saved), "ms67-config-test:base")
                target = root / "candidate.tar"
                images_tool.revise_archive(saved, target, "ms67-config-test:candidate", RUN, base["Id"])
                docker("load", "--input", str(target))
                candidate = json.loads(docker("inspect", "ms67-config-test:candidate"))[0]
                base["RepoDigests"] = [IMAGES["account"]]
                candidate["RepoDigests"] = [images_tool.REGISTRY+"/account@sha256:"+"c"*64]
                images_tool.packaging_proof("account", base, candidate, RUN)
                candidate["Config"]["User"] = "0"
                with self.assertRaisesRegex(JourneyFailure, "runtime-configuration-changed"):
                    images_tool.packaging_proof("account", base, candidate, RUN)
            finally:
                subprocess.run(["docker", "image", "rm", "--force", "ms67-config-test:base", "ms67-config-test:candidate"],
                               capture_output=True, timeout=60, check=False)


BUILD = "43bee3ac-7b44-4407-bafe-bdfedca5bd8e"


class RetryTests(unittest.TestCase):
    def setup_old(self, root, cloud):
        context = {"images": IMAGES, "bindings": BINDINGS, "retained_sha256": {"load": "l", "sql": "s"}}
        session = finish.Session(root, context, KEY, COMMIT)
        previous = {"serviceAccount": "projects/"+finish.PROJECT+"/serviceAccounts/cloudbank-ms67-evidence@"+finish.PROJECT+".iam.gserviceaccount.com",
            "steps": [{"id": name, "name": "gcr.io/test/"+name} for name in
                      ("checkout-fix", "sign-verify-and-scan-images", "build-and-push-eight-images")],
            "results": {"buildStepImages": ["sha256:"+"a"*64]*3}}
        inputs = {"run_id": session.state["run_id"], "controller_commit": COMMIT, "images": IMAGES, "bindings": BINDINGS}
        config = finish.candidate_config(inputs, previous, session.prefix)
        # The failed deployed controller used four steps, before this correction.
        config["steps"] = [*config["steps"][:2], {"id": "build-eight-packaging-revisions",
            "name": config["steps"][2]["name"], "entrypoint": "sh", "args": ["/workspace/final-images/package.sh"]}, config["steps"][-1]]
        (root/"candidate-cloudbuild.json").write_text(json.dumps(config))
        session.publish("candidate-context.json", inputs)
        session.state["candidate_build"] = {"phase": "submitted", "build_id": BUILD, "config_sha256": hashed(config)}
        session.save()
        build = {**config, "projectId": finish.PROJECT, "id": BUILD, "status": "FAILURE"}
        return session, context, build

    def test_retry_keeps_original_state_and_has_durable_resumable_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            cloud, root = Cloud(), Path(folder)
            def invoke(*args, **kw):
                return json.dumps(build) if args[0] == "builds" else cloud(["gcloud", *args], **kw)
            with patch.object(finish, "invoke", cloud), patch.object(finish, "cloud", side_effect=invoke):
                original, context, build = self.setup_old(root, cloud)
                before = copy.deepcopy(cloud.objects)
                local_before = (root/"finish-state.json").read_bytes()
                target, reference = finish.candidate_retry(root, context, KEY, BUILD)
                self.assertEqual(cloud.objects, before)
                retry = finish.Session(target, context, KEY, "b"*40, retry_of=reference)
                self.assertNotEqual(retry.state["run_id"], original.state["run_id"])
                retry.state["candidate_build"] = {"phase": "submitting"}; retry.save()
                target2, reference2 = finish.candidate_retry(root, context, KEY, BUILD)
                resumed = finish.Session(target2, context, KEY, "b"*40, retry_of=reference2)
                self.assertEqual(resumed.state["run_id"], retry.state["run_id"])
                with self.assertRaisesRegex(JourneyFailure, "no-duplicate"):
                    finish.choose_build(resumed.state["candidate_build"], [])
                self.assertEqual((root/"finish-state.json").read_bytes(), local_before)
                for uri, value in before.items():
                    self.assertEqual(cloud.objects[uri], value)

    def test_active_completed_tampered_mismatched_or_running_attempts_cannot_retry(self):
        for problem in ("active", "completed", "context", "config", "build", "signature", "running", "success"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as folder:
                cloud, root = Cloud(), Path(folder)
                def invoke(*args, **kw):
                    return json.dumps(build) if args[0] == "builds" else cloud(["gcloud", *args], **kw)
                with patch.object(finish, "invoke", cloud), patch.object(finish, "cloud", side_effect=invoke):
                    old, context, build = self.setup_old(root, cloud)
                    if problem == "active": old.state["active"] = {"phase": "secret-rotation"}; old.save()
                    if problem == "completed": old.state["completed"] = {"candidates": {}}; old.save()
                    if problem == "context": context = {**context, "changed": True}
                    if problem == "config": (root/"candidate-cloudbuild.json").write_text("{}")
                    if problem == "build": build["id"] = "wrong"
                    if problem == "running": build["status"] = "WORKING"
                    if problem == "success": build["status"] = "SUCCESS"
                    if problem == "signature":
                        state = json.loads((root/"finish-state.json").read_text()); state["controller_commit"] = "forged"
                        (root/"finish-state.json").write_text(json.dumps(state))
                    before = copy.deepcopy(cloud.objects)
                    with self.assertRaises(JourneyFailure):
                        finish.candidate_retry(root, context, KEY, BUILD)
                    self.assertEqual(cloud.objects, before)
                    self.assertFalse((root/("candidate-retry-"+BUILD)).exists())


if __name__ == "__main__":
    unittest.main()
