from copy import deepcopy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.ci.comparison_base import comparison_base, refusal_code


class ComparisonBaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.env = dict(os.environ, GIT_AUTHOR_NAME="Synthetic", GIT_AUTHOR_EMAIL="synthetic@example.invalid",
                        GIT_COMMITTER_NAME="Synthetic", GIT_COMMITTER_EMAIL="synthetic@example.invalid")
        self.git("init", "--quiet")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "commit.gpgsign", "false")
        self.base = self.commit("initial.txt", "base")
        self.head = self.commit("candidate.txt", "candidate")
        self.git("checkout", "--detach", self.base)
        self.current = self.commit("historical.txt", "already on main")
        tree = self.git("merge-tree", "--write-tree", self.current, self.head)
        self.merge = self.git("commit-tree", tree, "-p", self.current, "-p", self.head, "-m", "synthetic merge")
        self.git("reset", "--hard", self.merge)
        self.event = dict(pull_request=dict(base=dict(sha=self.base), head=dict(sha=self.head), merge_commit_sha=self.merge))

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, env=self.env, stderr=subprocess.DEVNULL).decode().strip()

    def commit(self, path, text):
        (self.root / path).write_text(text)
        self.git("add", path)
        self.git("commit", "--quiet", "-m", "synthetic")
        return self.git("rev-parse", "HEAD")

    def test_stale_event_base_excludes_only_merged_main_work(self):
        base = comparison_base(self.root, self.base, "pull_request", self.event, self.merge)
        self.assertEqual(self.current, base)
        self.assertEqual("candidate.txt", self.git("diff", "--name-only", base, self.merge))
        self.assertIn("historical.txt", self.git("diff", "--name-only", self.base, self.merge))
        self.assertEqual("candidate", self.git("show", self.merge + ":candidate.txt"))

    def test_wrong_head_base_checkout_and_nonmerge_refuse(self):
        for key, value in (("head", self.base), ("base", self.head)):
            event = deepcopy(self.event); event["pull_request"][key]["sha"] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                comparison_base(self.root, self.base, "pull_request", event, self.merge)
        with self.assertRaises(ValueError):
            comparison_base(self.root, self.base, "pull_request", self.event, self.head)
        self.git("reset", "--hard", self.head)
        with self.assertRaises(ValueError):
            comparison_base(self.root, self.base, "pull_request", self.event, self.merge)

    def test_merge_tree_tampering_and_unrelated_base_refuse(self):
        altered = self.git("rev-parse", self.head + "^{tree}")
        bad = self.git("commit-tree", altered, "-p", self.current, "-p", self.head, "-m", "wrong merge")
        self.git("reset", "--hard", bad)
        event = deepcopy(self.event); event["pull_request"]["merge_commit_sha"] = bad
        with self.assertRaisesRegex(ValueError, "merge-tree"):
            comparison_base(self.root, self.base, "pull_request", event, bad)
        self.git("reset", "--hard", self.merge)
        event = deepcopy(self.event); event["pull_request"]["base"]["sha"] = self.head
        with self.assertRaises(subprocess.CalledProcessError):
            comparison_base(self.root, self.head, "pull_request", event, self.merge)

    def test_push_uses_exact_event_range_and_refuses_wrong_identity(self):
        event = dict(before=self.base, after=self.head)
        self.git("reset", "--hard", self.head)
        self.assertEqual(self.base, comparison_base(self.root, self.base, "push", event, self.head))
        with self.assertRaises(ValueError):
            comparison_base(self.root, self.current, "push", event, self.head)
        with self.assertRaises(ValueError):
            comparison_base(self.root, self.base, "workflow_dispatch", event, self.head)

    def test_diagnostics_are_closed_and_never_include_exception_payloads(self):
        secret = "synthetic-private-payload-must-not-be-printed"
        for code in ("comparison-event-base", "comparison-event-merge", "comparison-merge-tree"):
            self.assertEqual(code, refusal_code(ValueError(code)))
        for exc in (ValueError(secret), KeyError(secret), RuntimeError(secret),
                    subprocess.CalledProcessError(1, ["unexpected", secret], output=secret),
                    subprocess.CalledProcessError(1, ["git", secret], stderr=secret)):
            self.assertEqual("comparison-unexpected-error", refusal_code(exc))
        for operation in ("rev-parse", "rev-list", "merge-base", "merge-tree"):
            exc = subprocess.CalledProcessError(1, ["git", operation, secret], output=secret, stderr=secret)
            self.assertEqual("comparison-git-" + operation, refusal_code(exc))
            self.assertNotIn(secret, refusal_code(exc))

    def test_event_base_and_merge_failures_remain_refused_with_distinct_codes(self):
        for field, value, code in (("base", {"sha": self.head}, "comparison-event-base"),
                                   ("merge_commit_sha", self.head, "comparison-event-merge")):
            event = deepcopy(self.event); event["pull_request"][field] = value
            with self.assertRaisesRegex(ValueError, code):
                comparison_base(self.root, self.base, "pull_request", event, self.merge)
