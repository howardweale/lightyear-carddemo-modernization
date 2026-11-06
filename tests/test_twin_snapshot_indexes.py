"""CI-only regression coverage with fake APT; no network or package installs."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/legacy_twin/update-snapshot-indexes.sh"


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux container bootstrap")
class SnapshotIndexRefreshTests(unittest.TestCase):
    def exercise(self, succeed_on):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apt = root / "apt-get"
            apt.write_text("""#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$APT_TEST_DIR/calls"
count=$(wc -l < "$APT_TEST_DIR/calls")
if [ "$count" -eq "$APT_TEST_SUCCESS" ]; then exit 0; fi
echo 'E: Failed to fetch snapshot index: 503 Service Unavailable' >&2
exit 100
""", encoding="utf-8")
            sleeper = root / "sleep"
            sleeper.write_text("""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$APT_TEST_DIR/delays"
""", encoding="utf-8")
            for executable in (apt, sleeper):
                executable.chmod(0o755)
            env = dict(os.environ, APT_TEST_DIR=str(root),
                       APT_TEST_SUCCESS=str(succeed_on),
                       PATH=str(root) + os.pathsep + os.environ["PATH"])
            # The sentinel represents installation chained after refresh.
            result = subprocess.run(
                ["bash", "-c", 'bash "$1" && printf installed', "check", str(SCRIPT)],
                env=env, text=True, capture_output=True, timeout=10)
            calls = (root / "calls").read_text().splitlines()
            delays = ((root / "delays").read_text().splitlines()
                      if (root / "delays").exists() else [])
            self.assertTrue(all(
                call == "-o APT::Update::Error-Mode=any update" for call in calls))
            return result, calls, delays

    def test_success_does_not_retry(self):
        result, calls, delays = self.exercise(1)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "installed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(delays, [])

    def test_transient_failure_requires_later_complete_success(self):
        result, calls, delays = self.exercise(3)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "installed")
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, ["10", "20"])

    def test_persistent_failure_is_bounded_and_prevents_install(self):
        result, calls, delays = self.exercise(4)
        self.assertEqual(result.returncode, 100)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, ["10", "20"])
        self.assertIn("failed after 3 attempts", result.stderr)
