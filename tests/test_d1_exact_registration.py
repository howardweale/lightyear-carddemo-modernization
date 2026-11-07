"""CI-only exact D1 registration rejection regressions; all identities synthetic."""
import copy
from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import check_d1_exact_registration as d1


NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
BASE, HEAD = "b" * 40, "c" * 40


def record(approved=True):
    value = dict(schema="d1-exact-source-registration/1", repository=d1.REPOSITORY,
                 status="pending-exact-hash-approval", source_anchor=d1.SOURCE_ANCHOR,
                 pr=None, candidate_commit=None, approval=None, authority=dict(d1.AUTHORITY),
                 entries=[dict(path=p, mode="100644", before_sha256=a, after_sha256=b)
                          for p, (a, b) in sorted(d1.PAYLOADS.items())])
    if approved:
        value.update(status="approved-exact-hashes", pr=999999, candidate_commit=HEAD,
                     approval=dict(source="operator-chat", approved_by="Howard Weale",
                        recorded_at_utc="2026-01-01T11:00:00Z",
                        expires_at_utc="2026-01-01T13:00:00Z",
                        exact_sha256={p: pair[1] for p, pair in d1.PAYLOADS.items()},
                        github_identity_is_human_proof=False))
    return value


def live():
    return dict(number=999999, state="open", merged=False,
                base=dict(ref="main", sha=BASE, repo=dict(full_name=d1.REPOSITORY)),
                head=dict(sha=HEAD, repo=dict(full_name=d1.REPOSITORY)))


class D1ExactRegistrationTests(unittest.TestCase):
    def test_pending_is_inert_and_exact_approved_bytes_validate(self):
        self.assertIsNone(d1.validate_record(record(False), now=NOW))
        self.assertEqual(d1.validate_record(record(), now=NOW), record())

    def test_record_cannot_widen_payload_authority_or_identity(self):
        cases = []
        for field, value in (("repository", "other/repo"), ("source_anchor", "f" * 40),
                             ("pr", 455), ("candidate_commit", "main"),
                             ("authority", dict(d1.AUTHORITY, merge=True))):
            row = record()
            row[field] = value
            cases.append(row)
        row = record()
        row["entries"][0]["after_sha256"] = "f" * 64
        cases.append(row)
        row = record()
        row["entries"].append(copy.deepcopy(row["entries"][0]))
        cases.append(row)
        row = record()
        row["entries"][0]["mode"] = "100755"
        cases.append(row)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    d1.validate_record(value, now=NOW)

    def test_expiry_null_identity_assertion_and_approval_drift_refused(self):
        for field, value in (("expires_at_utc", "2026-01-01T12:00:00Z"),
                             ("expires_at_utc", None),
                             ("recorded_at_utc", "2026-01-01T12:01:00Z"),
                             ("exact_sha256", {}),
                             ("github_identity_is_human_proof", True)):
            row = record()
            row["approval"][field] = value
            with self.assertRaises(ValueError):
                d1.validate_record(row, now=NOW)
        row = record(False)
        row["pr"] = 999999
        with self.assertRaises(ValueError):
            d1.validate_record(row, now=NOW)

    def inspect(self, *, changed=None, control_drift=False, postimage_drift=False,
                wrong_parent=False, stale=False, extra_fence=False, pending=False,
                other_pr=False):
        current = live()
        if stale:
            current["head"]["sha"] = "d" * 40
        event = dict(repository=dict(full_name=d1.REPOSITORY), pull_request=copy.deepcopy(live()))
        if other_pr:
            event["pull_request"]["number"] = 455
        environment = dict(GITHUB_REPOSITORY=d1.REPOSITORY, GITHUB_EVENT_NAME="pull_request")
        report = dict(blocked_paths=[d1.ORCHESTRATOR] + (["other.py"] if extra_fence else []),
                      merge_permitted=False, automatic_expiry=False)
        controls = {d1.RECORD, d1.VALIDATOR, d1.PARENT_VALIDATOR}

        def blob(repo, rev, path):
            if path in controls:
                return "d" * 64 if control_drift and rev == HEAD else "e" * 64
            before, after = d1.PAYLOADS[path]
            return (("f" * 64 if postimage_drift else after) if rev == HEAD else before)

        def git(repo, *args):
            if args[0] == "show" and args[-1] == BASE + ":" + d1.RECORD:
                return json.dumps(record(not pending)).encode()
            if args[:3] == ("show", "-s", "--format=%P"):
                return (("f" * 40 if wrong_parent else d1.SOURCE_ANCHOR) + "\n").encode()
            if args[0] == "diff":
                return ("\0".join(changed if changed is not None else d1.PAYLOADS) + "\0").encode()
            raise AssertionError(args)

        with patch.object(d1, "blob", blob), patch.object(d1, "git", git), \
                patch.object(d1.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
            return d1.inspect_registration(".", BASE, HEAD, report, event, environment,
                                           lambda route: copy.deepcopy(current), now=NOW)

    def test_exact_candidate_only_and_raw_report_unchanged(self):
        result = self.inspect()
        self.assertTrue(result["fence_requirement_met"])
        self.assertFalse(result["merge_authorized"])
        self.assertFalse(result["run_authorized"])
        self.assertEqual(result["raw_fence_report"]["blocked_paths"], [d1.ORCHESTRATOR])
        self.assertFalse(result["raw_fence_report"]["merge_permitted"])

    def test_pending_or_other_pr_does_not_replace_historical_455_path(self):
        self.assertIsNone(self.inspect(pending=True))
        self.assertIsNone(self.inspect(other_pr=True))

    def test_candidate_control_byte_scope_parent_and_context_drift_refused(self):
        for changes in (dict(control_drift=True), dict(postimage_drift=True),
                        dict(wrong_parent=True), dict(stale=True), dict(extra_fence=True),
                        dict(changed=[d1.ORCHESTRATOR]),
                        dict(changed=[*d1.PAYLOADS, "extra.py"])):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.inspect(**changes)
