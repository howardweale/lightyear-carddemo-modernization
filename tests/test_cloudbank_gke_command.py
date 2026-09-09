"""Exercise Windows SDK launch, literal arguments and private stdin boundaries."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from lightyear_data.cloudbank_journeys import JourneyFailure
from lightyear_data.cloudbank_journeys_gke import command


class WindowsSdkCommandTests(unittest.TestCase):
    def sdk(self, root: Path, program: str | None) -> Path:
        sdk = root / "Cloud SDK & tools"
        (sdk / "bin").mkdir(parents=True)
        launcher = sdk / "bin" / "gcloud.cmd"
        launcher.write_text("@echo Batch launcher must not execute\n@exit /b 99\n")
        if program is not None:
            (sdk / "lib").mkdir()
            (sdk / "lib" / "gcloud.py").write_text(program, encoding="utf-8")
        return launcher

    def test_windows_sdk_preserves_literal_arguments_and_utf8_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = self.sdk(root, "import json, sys\n"
                "print(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read()}, ensure_ascii=False))\n")
            arguments = ["storage", "cp", str(root / "evidence with spaces.json"),
                'gs://private-test/object#123&literal|value', '%LIGHTYEAR_COMMAND_TEST%',
                '--format=value(generation)', '{"unchanged": "quoted argument"}']
            payload = '{"marker": "synthetic café 日本語", "pepper": "synthetic-stdin-only"}\n'
            with patch("lightyear_data.cloudbank_journeys_gke.sys.platform", "win32"), \
                    patch("lightyear_data.cloudbank_journeys_gke.shutil.which", return_value=str(launcher)), \
                    patch.dict(os.environ, {"LIGHTYEAR_COMMAND_TEST": "must-not-expand"}):
                result = json.loads(command(["gcloud", *arguments], data=payload))
            self.assertEqual(result, {"argv": arguments, "stdin": payload})
            self.assertNotIn("synthetic-stdin-only", result["argv"])

    def test_incomplete_windows_sdk_stops_before_running_batch_file(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = self.sdk(Path(directory), None)
            with patch("lightyear_data.cloudbank_journeys_gke.sys.platform", "win32"), \
                    patch("lightyear_data.cloudbank_journeys_gke.shutil.which", return_value=str(launcher)), \
                    patch("lightyear_data.cloudbank_journeys_gke.subprocess.run") as spawn:
                with self.assertRaisesRegex(JourneyFailure, "operator-gcloud-sdk-entrypoint-missing"):
                    command(["gcloud", "version"])
            spawn.assert_not_called()

    def test_windows_sdk_failure_does_not_expose_raw_output(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = self.sdk(Path(directory), "import sys\n"
                "print('synthetic-private-output')\n"
                "print('synthetic-private-error', file=sys.stderr)\n"
                "sys.exit(3)\n")
            with patch("lightyear_data.cloudbank_journeys_gke.sys.platform", "win32"), \
                    patch("lightyear_data.cloudbank_journeys_gke.shutil.which", return_value=str(launcher)):
                with self.assertRaises(JourneyFailure) as failed:
                    command(["gcloud", "secrets", "versions", "access", "1"])
            self.assertEqual(str(failed.exception), "operator-command-failed")

    def test_native_command_keeps_stdin_and_arguments_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "native tool.py"
            script.write_text("import json, sys\n"
                "print(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read()}, ensure_ascii=False))\n")
            value = json.loads(command([sys.executable, "-X", "utf8", str(script), "literal & argument"],
                                       data="synthetic café 日本語"))
            self.assertEqual(value, {"argv": ["literal & argument"], "stdin": "synthetic café 日本語"})


@unittest.skipUnless(sys.platform == "win32" and os.environ.get("LIGHTYEAR_TEST_WINDOWS_GCLOUD") == "1",
                     "requires the dedicated Windows SDK CI job")
class InstalledWindowsSdkTests(unittest.TestCase):
    def test_installed_sdk_564_runs_without_batch_command_interpretation(self):
        version = json.loads(command(["gcloud", "version", "--format=json"], timeout=120))
        self.assertEqual(version["Google Cloud SDK"], "564.0.0")
        sdk_root = command(["gcloud", "info", "--format=value(installation.sdk_root)"], timeout=120).strip()
        self.assertTrue((Path(sdk_root) / "lib" / "gcloud.py").is_file())


if __name__ == "__main__":
    unittest.main()
