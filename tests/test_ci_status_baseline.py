"""Real Git fixtures, executed only by CI."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.ci_status_baseline import FILES, capture, finish, cli_context


class CleanStatusHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.state = Path(self.temp.name) / "lightyear-status-baseline.json"
        self.command("init")
        self.protected = ("input.json", "docs/milestones/preserved.json")
        for name in (*FILES, *self.protected):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"committed")
        self.command("add", ".")
        self.command("commit", "-m", "fixture")
        self.head = self.command("rev-parse", "HEAD")
        for name in FILES:
            (self.root / name).write_bytes(b"fresh status")

    def command(self, *args):
        return subprocess.check_output(
            ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
             "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
            cwd=self.root, stderr=subprocess.DEVNULL, text=True).strip()

    def test_clean_handoff_without_new_commit(self):
        capture(self.root, self.state)
        self.assertTrue(self.command("status", "--porcelain"))
        finish(self.root, self.state)
        self.assertEqual("", self.command("status", "--porcelain"))
        self.assertEqual(self.head, self.command("rev-parse", "HEAD"))
        for name in FILES:
            self.assertEqual(b"committed", (self.root / name).read_bytes())
        self.assertFalse(self.state.exists())

    def test_output_input_and_evidence_mutations_are_not_hidden(self):
        capture(self.root, self.state)
        for name in (*FILES, *self.protected):
            with self.subTest(path=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(b"mutated")
                with self.assertRaises(ValueError):
                    finish(self.root, self.state)
                self.assertEqual(b"mutated", path.read_bytes())
                self.assertTrue(self.state.exists())
                path.write_bytes(original)

    def test_extra_staged_change_refused(self):
        capture(self.root, self.state)
        (self.root / "input.json").write_bytes(b"staged mutation")
        self.command("add", "input.json")
        with self.assertRaisesRegex(ValueError, "staged baseline"):
            finish(self.root, self.state)

    def test_staged_output_mutation_refused(self):
        capture(self.root, self.state)
        (self.root / FILES[0]).write_bytes(b"mutated")
        self.command("add", "--", FILES[0])
        with self.assertRaisesRegex(ValueError, "status mutated"):
            finish(self.root, self.state)

    def test_untracked_mutation_refused(self):
        capture(self.root, self.state)
        (self.root / "unexpected.txt").write_text("unexpected")
        with self.assertRaisesRegex(ValueError, "untracked"):
            finish(self.root, self.state)

    def test_capture_refuses_dirty_inputs_and_existing_state(self):
        (self.root / "input.json").write_bytes(b"mutated")
        with self.assertRaisesRegex(ValueError, "input/evidence"):
            capture(self.root, self.state)
        (self.root / "input.json").write_bytes(b"committed")
        capture(self.root, self.state)
        with self.assertRaisesRegex(ValueError, "already exists"):
            capture(self.root, self.state)

    def test_local_or_repository_state_location_refused(self):
        with self.assertRaisesRegex(ValueError, "CI-only"):
            cli_context({})
        env = {"GITHUB_ACTIONS": "true", "GITHUB_WORKSPACE": str(self.root),
               "RUNNER_TEMP": self.temp.name, "LIGHTYEAR_CI_STATUS_BASELINE": str(self.root / self.state.name)}
        with self.assertRaisesRegex(ValueError, "RUNNER_TEMP"):
            cli_context(env)
