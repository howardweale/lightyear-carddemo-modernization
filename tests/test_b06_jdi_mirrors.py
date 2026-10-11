"""Explicitly enabled host-only tests for pinned JDI cache pruning."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.environ.get("B06_HOST_JDK"), "pinned host JDK explicitly enabled")
class MirrorCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.classes = Path(cls.temp.name)
        jdk = Path(os.environ["B06_HOST_JDK"]) / "bin"
        cls.java = jdk / ("java.exe" if os.name == "nt" else "java")
        javac = jdk / ("javac.exe" if os.name == "nt" else "javac")
        subprocess.run([str(javac), "--add-modules", "jdk.jdi", "-d", str(cls.classes),
            str(ROOT/"factory/idempiere/b06-observer/BoundedJdiMirrors.java"),
            str(ROOT/"tools/b06_host_probe/BoundedMirrorsProbe.java"),
            str(ROOT/"tools/b06_host_probe/BoundedMirrorsTarget.java")], check=True,
            capture_output=True, text=True, timeout=60)

    def run_probe(self, opens=True):
        args = [str(self.java), "--add-modules", "jdk.jdi", "-Xmx192m"]
        if opens:
            args.append("--add-opens=jdk.jdi/com.sun.tools.jdi=ALL-UNNAMED")
        args += ["-cp", str(self.classes), "BoundedMirrorsProbe", str(self.classes)]
        if not opens:
            args.append("no-opens")
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_real_host_lifecycle_identity_queries_and_fail_closed_bounds(self):
        self.assertIn("host-mirror-lifecycle-passed", self.run_probe())

    def test_module_access_missing_refuses_before_collection(self):
        self.assertIn("missing-opens-refused", self.run_probe(False))
