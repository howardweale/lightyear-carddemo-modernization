"""CI-only fake-build regressions; no Docker or network access."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from tools.ci import twin_build_retry as retry

ERROR = ("#4 ADD --checksum=sha256:641de77d8f142cfd62a1a6f964ba67b20754d3337c480efb529d086075a06c9a bootstrap.deb /tmp/bootstrap.deb\n"
         "#10 172.2 E: Failed to fetch "
         "https://snapshot.ubuntu.com/ubuntu/20261001T000000Z/"
         "dists/noble/multiverse/binary-amd64/Packages  503 Service Unavailable\n"
         "#10 172.2 E: " + retry.INDEX_SUMMARY + "\n"
         'ERROR: failed to build: failed to solve: process "/bin/sh -c apt-get update'
         ' && apt-get install packages" did not complete successfully: exit code: 100\n')


def result(code=1, output=ERROR):
    return subprocess.CompletedProcess(retry.COMMAND, code, output)


class TwinBuildRetryTests(unittest.TestCase):
    def run_builds(self, results):
        build = Mock(side_effect=results)
        pause = Mock()
        with patch.object(retry, "RECIPE",
                          Path(__file__).resolve().parents[1] /
                          "tools/legacy_twin/reproducible.Containerfile"):
            status = retry.build_with_retry(build, pause)
        return status, build, pause

    def test_immediate_success_does_not_retry(self):
        status, build, pause = self.run_builds([result(0, "")])
        self.assertEqual(status, 0)
        self.assertEqual(build.call_count, 1)
        pause.assert_not_called()

    def test_transient_outage_then_success(self):
        for code in ("502", "503", "504"):
            with self.subTest(http=code):
                status, build, pause = self.run_builds(
                    [result(output=ERROR.replace("503", code)), result(0, "")])
                self.assertEqual(status, 0)
                self.assertEqual(build.call_count, 2)
                pause.assert_called_once_with(60)

    def test_persistent_outage_stays_failed_after_one_retry(self):
        status, build, pause = self.run_builds([result(), result()])
        self.assertEqual(status, 1)
        self.assertEqual(build.call_count, 2)
        pause.assert_called_once_with(60)

    def test_integrity_permanent_unknown_and_wrong_layer_fail_immediately(self):
        failures = [
            result(output=ERROR.replace("503", "404")),
            result(output=ERROR.replace("snapshot.ubuntu.com", "untrusted.invalid")),
            result(output=ERROR.replace("20261001T000000Z", "latest")),
            result(output=ERROR + "E: The repository is not signed.\n"),
            result(output=ERROR + "Hash Sum mismatch\n"),
            result(output=ERROR + "checksum mismatch\n"),
            result(output=ERROR + "E: Unable to locate package foo\n"),
            result(output=ERROR.replace("apt-get update", "compile-source")),
            result(output="Dockerfile syntax error"),
            result(output=ERROR + "CAPTURE_LIMIT"),
            result(code=137),
        ]
        for failure in failures:
            with self.subTest(failure=failure.stdout):
                status, build, pause = self.run_builds([failure])
                self.assertNotEqual(status, 0)
                self.assertEqual(build.call_count, 1)
                pause.assert_not_called()

    def test_recipe_drift_refuses_before_docker(self):
        build, pause = Mock(), Mock()
        with patch.object(Path, "read_bytes", return_value=b"changed recipe"):
            self.assertEqual(retry.build_with_retry(build, pause), 1)
        build.assert_not_called()
        pause.assert_not_called()

    def test_recipe_drift_between_attempts_refuses_second_build(self):
        original = retry.RECIPE.read_bytes()
        build, pause = Mock(return_value=result()), Mock()
        with patch.object(Path, "read_bytes", side_effect=[original, b"changed"]):
            self.assertEqual(retry.build_with_retry(build, pause), 1)
        self.assertEqual(build.call_count, 1)

    def test_deterministic_second_failure_is_not_hidden(self):
        status, build, pause = self.run_builds(
            [result(), result(7, "a different build error")])
        self.assertEqual(status, 7)
        self.assertEqual(build.call_count, 2)
