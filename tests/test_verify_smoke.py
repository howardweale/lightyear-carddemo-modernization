"""Portable regressions for the VM kit. Native isolation stays a separate platform check."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import patch, Mock
from types import SimpleNamespace

from tools.verify_smoke import provision, build_candidates, acceptance, agent
from lightyear_toolkit.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]


class KitTests(unittest.TestCase):
    def test_architecture_mapping_refuses_unknown(self):
        self.assertEqual("arm64", provision.architecture("aarch64"))
        self.assertEqual("x86_64", provision.architecture("x86_64"))
        with self.assertRaises(KeyError):
            provision.architecture("riscv64")

    def test_evaluation_exact_public_run1_idempotent_and_extra_file_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "evaluation"
            first = provision.evaluation_copy(ROOT, target)
            self.assertEqual(first, provision.evaluation_copy(ROOT, target))
            self.assertTrue(all(p.startswith("INTCALC-run1-") for p in first))
            (target / "unapproved.bin").write_bytes(b"not a fixture")
            with self.assertRaisesRegex(ValueError, "exactly"):
                provision.evaluation_copy(ROOT, target)

    def test_modified_evaluation_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            provision.evaluation_copy(ROOT, target)
            path = next(target.rglob("ACCTFILE.bin"))
            path.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                provision.evaluation_copy(ROOT, target)
            self.assertEqual(b"modified", path.read_bytes())

    def test_public_manifest_usable_and_byte_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            digest = provision.public_workspace(ROOT, path)
            self.assertEqual(digest, provision.public_workspace(ROOT, path))
            manifest = json.loads((path / "public.json").read_bytes())
            self.assertEqual({"account.cpy", "accounts.bin", "job.txt"}, set(manifest["files"]))
            ws = Workspace(path, manifest["files"])
            self.assertEqual(300, ws.describe("account.cpy")["record_length"])
            self.assertTrue(ws.decode("accounts.bin", "account.cpy", "cp037", "fixed"))
            (path / "accounts.bin").write_bytes(b"unexpected")
            with self.assertRaises(ValueError):
                provision.public_workspace(ROOT, path)

    def test_install_refuses_modified_fixture_and_excludes_untracked_private_paths(self):
        fixture = provision.FIXTURE + "/run.json"
        paths = (fixture + "\0work/private.bin\0README.md\0").encode()
        public_bytes = (ROOT / fixture).read_bytes()
        def git_read(source, *args):
            return paths if args[0] == "ls-files" else public_bytes
        with patch.object(provision, "git_output", side_effect=git_read):
            files = provision.source_files(ROOT)
            self.assertNotIn("work/private.bin", files)
            self.assertIn(fixture, files)
        with patch.object(provision, "git_output", side_effect=lambda _, *args: paths if args[0] == "ls-files" else b"different public commitment"):
            with self.assertRaisesRegex(ValueError, "differs from"):
                provision.source_files(ROOT)

    def test_existing_different_config_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "config.json"
            provision.write_same(p, b"first")
            provision.write_same(p, b"first")
            with self.assertRaises(ValueError):
                provision.write_same(p, b"second")
            self.assertEqual(b"first", p.read_bytes())

    def test_mutations_match_acceptance_and_require_expected_anchor_count(self):
        original = ROOT / "candidate-java/src/main/java/ai/lightyear/carddemo/service/InterestCalculationService.java"
        text = original.read_text(encoding="utf-8")
        acceptance_source = (ROOT / "tests/test_verify_mcp.py").read_text(encoding="utf-8")
        for name, (old, new) in build_candidates.CHANGES.items():
            self.assertIn(old, acceptance_source)
            self.assertIn(new, acceptance_source)
            self.assertNotEqual(text, build_candidates.mutate(text, name))
            with self.assertRaises(ValueError):
                build_candidates.mutate(text + text, name)
            with self.assertRaises(ValueError):
                build_candidates.mutate("", name)

    def test_acceptance_cannot_report_pass_if_skipped_or_no_native_sentinel(self):
        ok = "Ran 25 tests in 1s\nOK\nVERIFY_ACCEPTANCE: five real sandbox submissions"
        self.assertEqual("passed", acceptance.result_status(0, ok))
        for rc, output in ((1, ok), (0, "Ran 25 tests\nOK"),
                           (0, ok + "\nOK (skipped=3)"), (0, ok + "\n... skipped 'no jar'")):
            self.assertEqual("failed", acceptance.result_status(rc, output))

    def test_agent_drops_privileges_before_exec_and_never_places_token_in_argv(self):
        # No real root operations: every privilege-changing primitive is mocked.
        events = []
        fake_pwd = SimpleNamespace(getpwnam=lambda _: SimpleNamespace(
            pw_name="lyagent", pw_dir="/home/lyagent", pw_uid=2002, pw_gid=2002))
        fake_path = Mock()
        fake_path.read_text.return_value = "test-capability"
        def capture_exec(executable, argv, env):
            self.assertEqual(["groups", "gid", "uid"], events)
            self.assertNotIn("test-capability", repr(argv))
            self.assertEqual("test-capability", env["LIGHTYEAR_VERIFY_TOKEN"])
            self.assertNotIn("PYTHONPATH", env)
            self.assertEqual("/home/lyagent", env["HOME"])
        with patch.dict("sys.modules", pwd=fake_pwd), patch.object(agent.os, "geteuid", create=True, return_value=0), \
             patch.object(agent, "Path", return_value=fake_path), \
             patch.object(agent.os, "setgroups", create=True, side_effect=lambda _: events.append("groups")), \
             patch.object(agent.os, "setgid", create=True, side_effect=lambda _: events.append("gid")), \
             patch.object(agent.os, "setuid", create=True, side_effect=lambda _: events.append("uid")), \
             patch.object(agent.os, "chdir"), patch.object(agent.os, "umask"), \
             patch.object(agent.os, "execvpe", side_effect=capture_exec), \
             patch.object(agent.sys, "argv", ["agent.py"]):
            agent.main()


@unittest.skipUnless(shutil.which("javac") and (ROOT / "candidate-java/target/classes").is_dir(),
                     "Build the public candidate with Maven first")
class CandidateBuildTests(unittest.TestCase):
    def test_real_mutant_compiles_change_only_service_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            project = workspace / "candidate-java"
            shutil.copytree(ROOT / "candidate-java/src", project / "src")
            shutil.copytree(ROOT / "candidate-java/target/classes", project / "target/classes")
            name = "carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar"
            shutil.copyfile(ROOT / "candidate-java/target" / name, project / "target" / name)
            build_candidates.build(workspace)
            with zipfile.ZipFile(workspace / "good.jar") as good:
                for mutant in build_candidates.CHANGES:
                    with zipfile.ZipFile(workspace / (mutant + ".jar")) as changed:
                        self.assertEqual(good.namelist(), changed.namelist())
                        differences = [n for n in good.namelist() if good.read(n) != changed.read(n)]
                        self.assertEqual(["BOOT-INF/classes/" + build_candidates.CLASS], differences)
            report = json.loads((workspace / "candidates.json").read_bytes())
            self.assertEqual(4, len(set(report["jars"].values())))


if __name__ == "__main__":
    unittest.main()
