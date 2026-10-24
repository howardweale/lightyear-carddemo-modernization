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
        self.ref = "refs/pull/452/merge"
        self.event = dict(number=452, pull_request=dict(number=452, base=dict(sha=self.base), head=dict(sha=self.head), merge_commit_sha=self.merge))

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, env=self.env, stderr=subprocess.DEVNULL).decode().strip()

    def commit(self, path, text):
        (self.root / path).write_text(text)
        self.git("add", path)
        self.git("commit", "--quiet", "-m", "synthetic")
        return self.git("rev-parse", "HEAD")

    def test_stale_event_base_excludes_only_merged_main_work(self):
        base = comparison_base(self.root, self.base, "pull_request", self.event, self.merge, self.ref)
        self.assertEqual(self.current, base)
        self.assertEqual("candidate.txt", self.git("diff", "--name-only", base, self.merge))
        self.assertIn("historical.txt", self.git("diff", "--name-only", self.base, self.merge))
        self.assertEqual("candidate", self.git("show", self.merge + ":candidate.txt"))

    def test_wrong_head_base_checkout_and_nonmerge_refuse(self):
        for key, value in (("head", self.base), ("base", self.head)):
            event = deepcopy(self.event); event["pull_request"][key]["sha"] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                comparison_base(self.root, self.base, "pull_request", event, self.merge, self.ref)
        with self.assertRaises(ValueError):
            comparison_base(self.root, self.base, "pull_request", self.event, self.head, self.ref)
        self.git("reset", "--hard", self.head)
        with self.assertRaises(ValueError):
            comparison_base(self.root, self.base, "pull_request", self.event, self.merge, self.ref)

    def test_merge_tree_tampering_and_unrelated_base_refuse(self):
        altered = self.git("rev-parse", self.head + "^{tree}")
        bad = self.git("commit-tree", altered, "-p", self.current, "-p", self.head, "-m", "wrong merge")
        self.git("reset", "--hard", bad)
        event = deepcopy(self.event); event["pull_request"]["merge_commit_sha"] = bad
        with self.assertRaisesRegex(ValueError, "merge-tree"):
            comparison_base(self.root, self.base, "pull_request", event, bad, self.ref)
        self.git("reset", "--hard", self.merge)
        event = deepcopy(self.event); event["pull_request"]["base"]["sha"] = self.head
        with self.assertRaises(subprocess.CalledProcessError):
            comparison_base(self.root, self.head, "pull_request", event, self.merge, self.ref)

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
        for code in ("comparison-event-base", "comparison-event-merge", "comparison-pr-merge-ref", "comparison-merge-tree"):
            self.assertEqual(code, refusal_code(ValueError(code)))
        for exc in (ValueError(secret), KeyError(secret), RuntimeError(secret),
                    subprocess.CalledProcessError(1, ["unexpected", secret], output=secret),
                    subprocess.CalledProcessError(1, ["git", secret], stderr=secret)):
            self.assertEqual("comparison-unexpected-error", refusal_code(exc))
        for operation in ("rev-parse", "rev-list", "merge-base", "merge-tree"):
            exc = subprocess.CalledProcessError(1, ["git", operation, secret], output=secret, stderr=secret)
            self.assertEqual("comparison-git-" + operation, refusal_code(exc))
            self.assertNotIn(secret, refusal_code(exc))

    def test_event_base_and_ref_failures_remain_refused_with_distinct_codes(self):
        event = deepcopy(self.event); event["pull_request"]["base"]["sha"] = self.head
        with self.assertRaisesRegex(ValueError, "comparison-event-base"):
            comparison_base(self.root, self.base, "pull_request", event, self.merge, self.ref)
        with self.assertRaisesRegex(ValueError, "comparison-pr-merge-ref"):
            comparison_base(self.root, self.base, "pull_request", self.event, self.merge, "refs/pull/452/head")

    def test_event_merge_metadata_is_not_the_checkout_authority(self):
        for value in (None, self.head, self.base):
            event = deepcopy(self.event); event["pull_request"]["merge_commit_sha"] = value
            with self.subTest(value=value):
                self.assertEqual(self.current, comparison_base(self.root, self.base, "pull_request", event, self.merge, self.ref))
        event["pull_request"].pop("merge_commit_sha")
        self.assertEqual(self.current, comparison_base(self.root, self.base, "pull_request", event, self.merge, self.ref))
        # Ignoring event merge metadata must never bypass checked-out identity.
        with self.assertRaisesRegex(ValueError, "comparison-merge-parents"):
            comparison_base(self.root, self.base, "pull_request", event, self.head, self.ref)

    def test_runner_ref_and_both_pr_numbers_are_bound(self):
        for ref in (None, "", "refs/heads/main", "refs/pull/453/merge", "refs/pull/452/head", "refs/pull/0452/merge"):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, "comparison-pr-merge-ref"):
                comparison_base(self.root, self.base, "pull_request", self.event, self.merge, ref)
        for number in (None, True, "452", 0, -1, 453):
            for location in ("event", "pr"):
                event = deepcopy(self.event)
                target = event if location == "event" else event["pull_request"]
                target["number"] = number
                with self.subTest(number=number, location=location), self.assertRaisesRegex(ValueError, "comparison-pr-merge-ref"):
                    comparison_base(self.root, self.base, "pull_request", event, self.merge, self.ref)
        for location in ("event", "pr"):
            event = deepcopy(self.event)
            target = event if location == "event" else event["pull_request"]
            target.pop("number")
            with self.assertRaisesRegex(ValueError, "comparison-pr-merge-ref"):
                comparison_base(self.root, self.base, "pull_request", event, self.merge, self.ref)
