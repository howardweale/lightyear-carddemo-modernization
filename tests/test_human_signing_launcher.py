"""CI-only real launcher/spawn regression; staged adapters use disposable fixtures."""
import ast
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization

from lightyear_control_tower.decisions import canonical
import test_human_signing_command as fixtures

sha = fixtures.sha


REPO = Path(__file__).resolve().parents[1]
GROUPS = {
    "lightyear_execution": ("__init__", "external_signing", "human_signing_packet",
                           "signing_designation", "signing_key_a"),
    "lightyear_control_tower": ("__init__", "decisions", "verification", "kinds"),
    "carddemo_oracle": ("__init__", "compare", "records"),
    "lightyear_common": ("__init__", "io", "trust"),
}
# Test-only module staged outside the repository. Production has no fake-worker
# switch, injected configuration or host-guard escape hatch.
FIXTURE = r'''
import base64
import json
import os
from pathlib import Path
import stat
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]

def configure(command_globals):
    keys = json.loads((ROOT / "fixture.json").read_text())
    registry = command_globals["PUBLIC_KEYS"]
    registry.clear()
    registry.update({r: (base64.b64decode(k["pem"]), k["sha"]) for r, k in keys.items()})
    if os.name != "posix":
        # Windows still exercises real exclusive files/directories and spawn.
        # POSIX identity, no-follow and directory-fsync seams only are synthetic.
        os.O_NOFOLLOW = 0
        os.O_NONBLOCK = 0
        os.getuid = lambda: 42
        original = Path.lstat
        def owned(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path.name == "human-signing-attempts":
                fields = list(result)
                fields[0], fields[4] = stat.S_IFDIR | 0o700, 42
                return os.stat_result(fields)
            return result
        Path.lstat = owned
        command_globals["sync_dir"] = lambda path: None

def run_worker(pipe, purpose, message, wall, deadline, preflight):
    try:
        # Reaching this file proves a fresh spawn imported the named target.
        with (ROOT / "worker-starts").open("a") as stream:
            stream.write(purpose + "\n")
        mode = (ROOT / "mode").read_text()
        if mode == "refuse":
            pipe.send_bytes(b"REFUSED:device-slot-public-key-or-policy-mismatch")
        elif mode == "untrusted":
            pipe.send_bytes(b"REFUSED:SECRET-serial-PIN-exception")
        elif preflight:
            pipe.send_bytes(b"READY_FOR_PIN")
        else:
            keys = json.loads((ROOT / "fixture.json").read_text())
            private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(keys[purpose]["private"]))
            pipe.send_bytes(b"OK:" + private.sign(message))
    finally:
        pipe.close()
'''


class LauncherSpawnTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bundle = self.root / "lightyear505"
        self.bundle.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.fixtures = fixtures.HumanSigningTests()
        self.fixtures.setUp()
        self.addCleanup(self.fixtures.doCleanups)
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home))
        # Copy the exact real launcher and the same source closure as the bundle.
        shutil.copyfile(REPO / "tools/human_signing_mac/run.py", self.bundle / "run.py")
        for package, names in GROUPS.items():
            for name in names:
                relative = Path("src") / package / (name + ".py")
                dest = self.bundle / "code" / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / relative, dest)
        tools = self.bundle / "code/tools"
        tools.mkdir(parents=True)
        (tools / "__init__.py").write_text("")
        source = (REPO / "tools/human_signing.py").read_text()
        tree = ast.parse(source)
        lines = source.splitlines(keepends=True)
        replacements = {
            "require_human_host": "    return  # CI synthetic host only\n",
            "hardware_worker": (
                "    from fixture_adapter import run_worker\n"
                "    return run_worker(pipe, purpose, message, wall_deadline, monotonic_deadline, preflight)\n"
            ),
        }
        # Keep the target name, module identity, Process construction, spawn,
        # pipes, packet validation, confirmation and journal code unchanged.
        for node in reversed(tree.body):
            if isinstance(node, ast.FunctionDef) and node.name in replacements:
                lines[node.body[0].lineno - 1:node.end_lineno] = [replacements[node.name]]
        source = "".join(lines)
        source = source.replace('if __name__ == "__main__":',
                                'from fixture_adapter import configure\nconfigure(globals())\n\n'
                                'if __name__ == "__main__":')
        (tools / "human_signing.py").write_text(source)
        (self.bundle / "code/fixture_adapter.py").write_text(FIXTURE)
        keys = {}
        for role, key in self.fixtures.keys.items():
            pem = key.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            private = key.private_bytes(serialization.Encoding.Raw,
                                        serialization.PrivateFormat.Raw, serialization.NoEncryption())
            keys[role] = dict(pem=base64.b64encode(pem).decode(), sha=sha(pem),
                              private=base64.b64encode(private).decode())
        (self.bundle / "fixture.json").write_text(json.dumps(keys))
        (self.bundle / "mode").write_text("success")

    def invoke(self, command, purpose="controller-receipt", phrase=None):
        request = canonical(self.fixtures.request(purpose))
        files = {"request": request, "designation": self.fixtures.designation.record,
                 "revocations": canonical(self.fixtures.rev)}
        args = [sys.executable, "-I", str(self.bundle / "run.py"), command,
                "--source-commit", "a" * 40, "--work-order-sha256", "b" * 64,
                "--context-sha256", "c" * 64]
        for name, raw in files.items():
            path = self.root / (name + ".json")
            path.write_bytes(raw)
            args += ["--" + name, str(path), "--" + name + "-sha256", sha(raw)]
        role = "controller-envelope" if purpose == "controller-receipt" else purpose
        args += ["--role", role]
        output = self.root / (purpose + ".reply")
        if command == "sign":
            args += ["--output", str(output)]
        if phrase is None:
            phrase = role + " " + sha(request)[:8]
        return subprocess.run(args, input=phrase + "\n", text=True, capture_output=True,
                              env=self.env, cwd=self.root, timeout=25), output

    def test_preflight_then_both_signatures_and_durable_no_retry(self):
        for purpose in self.fixtures.keys:
            with self.subTest(purpose=purpose):
                result, output = self.invoke("preflight", purpose)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("READY_FOR_PIN", result.stdout)
                self.assertFalse(output.exists())
                # No reservation for this role, even after the other role signed.
                before = list(self.home.rglob("intent.json"))
                self.assertEqual(len(before), 0 if purpose == "controller-receipt" else 1)
                result, output = self.invoke("sign", purpose)
                self.assertEqual(result.returncode, 0, result.stderr)
                packet = self.fixtures.packet(purpose)
                expected = packet.reply(self.fixtures.keys[purpose].sign(packet.signing_bytes()))
                self.assertEqual(output.read_bytes(), expected)
                old = output.read_bytes()
                intents = {p: p.read_bytes() for p in self.home.rglob("intent.json")}
                result, _ = self.invoke("sign", purpose)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Reason: attempt-or-output-already-exists\nSTOP:", result.stderr)
                self.assertEqual(output.read_bytes(), old)
                self.assertEqual({p: p.read_bytes() for p in self.home.rglob("intent.json")}, intents)
        self.assertEqual(len(list(self.home.rglob("result.json"))), 2)
        self.assertEqual(len((self.bundle / "worker-starts").read_text().splitlines()), 4)

    def test_preflight_reason_codes_and_untrusted_error_redaction(self):
        for mode, expected in (("refuse", "device-slot-public-key-or-policy-mismatch"),
                               ("untrusted", "hardware-failed-no-retry-unplug-key")):
            (self.bundle / "mode").write_text(mode)
            result, output = self.invoke("preflight")
            self.assertEqual(result.returncode, 1)
            self.assertIn("Reason: " + expected + "\nSTOP:", result.stderr)
            self.assertNotIn("SECRET", result.stdout + result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse(list(self.home.rglob("intent.json")))

    def test_wrong_short_confirmation_does_not_spawn_or_reserve(self):
        result, output = self.invoke("sign", phrase="controller-envelope 00000000")
        self.assertEqual(result.returncode, 1)
        self.assertIn("human-confirmation-required", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse((self.bundle / "worker-starts").exists())
        self.assertFalse(list(self.home.rglob("intent.json")))

    def test_old_runpy_launcher_is_rejected_without_preflight_reservation(self):
        # Mutation control proves the regression catches the reported launcher,
        # rather than merely exercising an already-importable fake target.
        launcher = self.bundle / "run.py"
        source = launcher.read_text()
        prefix = source.split("from tools.human_signing import main")[0]
        launcher.write_text(prefix + 'import runpy\nrunpy.run_module("tools.human_signing", run_name="__main__")\n')
        result, output = self.invoke("preflight")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Reason: worker-start-failed\nSTOP:", result.stderr)
        self.assertNotIn("PicklingError", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse((self.bundle / "worker-starts").exists())
        self.assertFalse(list(self.home.rglob("intent.json")))
