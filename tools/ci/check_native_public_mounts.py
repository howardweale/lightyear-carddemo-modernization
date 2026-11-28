"""Regression checks on Linux CI using only public synthetic data."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_intcalc_native_candidate_runtime import archive
from tools import intcalc_native_candidate_runtime as native


class PublicMountTests(unittest.TestCase):
    def setUp(self):
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)
        tmp = self.enterContext(tempfile.TemporaryDirectory(dir="/dev/shm"))
        self.folder = Path(tmp)
        inputs = {dd: bytes((0, index, 255)) for index, dd in enumerate(native.p5.INPUTS)}
        jar = archive()
        cli = "a" * 64
        profile = dict(binaries={"docker": {"sha256": cli, "path": "/unused"}},
                       private_root=tmp, client_config="/unused")
        host = Mock(p=profile)
        image = SimpleNamespace(cli=cli, host_profile=native.h1.sha(native.h1.canonical(profile)))
        # Only the host admission and Docker boundary are synthetic. Both writers are real.
        with (patch.object(native.h1, "profile"), patch.object(native.h1, "source_identity"),
              patch.object(native.h1, "private_directory", return_value=self.folder)):
            runtime = native._Runtime(host, image, jar)
        docker = Mock()
        docker.cleanup.return_value = [{"kind": k, "absence_confirmed": True}
                                       for k in ("container", "container", "volume")]
        with patch.object(runtime, "_docker", return_value=docker):
            runtime._case(inputs, runtime.root, self.folder, "stamp", "date", time.monotonic() + 60)
        self.leaves = [(runtime.jar, "/candidate.jar", jar)]
        for dd, raw in inputs.items():
            self.leaves.append((self.folder / (dd + ".bin"), "/input/" + dd + ".bin", raw))

    def test_umask_does_not_change_mounted_modes_or_bytes(self):
        for leaf, dest, raw in self.leaves:
            with self.subTest(dest=dest):
                self.assertEqual(stat.S_IMODE(leaf.parent.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(leaf.stat().st_mode), 0o444)
                self.assertEqual(leaf.read_bytes(), raw)

    def test_candidate_uid_reads_all_five_individual_mounts(self):
        mounts, destinations, expected = [], [], []
        for leaf, dest, raw in self.leaves:
            self.assertNotEqual(leaf.stat().st_uid, 65534)
            mounts.extend(["--mount", f"type=bind,src={leaf},dst={dest},readonly"])
            destinations.append(dest)
            expected.append(hashlib.sha256(raw).hexdigest() + "  " + dest)
        image = "ubuntu@sha256:f610ab94648195aa356059f5b41d6085c9d4d903c072430cdd1af7bdb646106b"
        subprocess.run(["docker", "pull", "--platform=linux/amd64", image], check=True, timeout=150)
        script = 'test "$(id -u):$(id -g)" = 65534:65534 && exec /usr/bin/sha256sum "$@"'
        cmd = ["docker", "run", "--rm", *native.ISOLATION, *mounts, image,
               "/bin/sh", "-ec", script, "read-mounts", *destinations]
        run = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        self.assertEqual(run.stdout.splitlines(), expected)


if __name__ == "__main__":
    unittest.main()
