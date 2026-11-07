"""Exact D1 source registration loaded from trusted base; never self-approval.

This preserves the raw fence result and grants no merge or execution authority.
Operator-chat provenance is recorded attribution, not authentication of a human.
"""
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess

REPOSITORY = "howardweale/lightyear-carddemo-modernization"
SOURCE_ANCHOR = "061229839ca5f9a68f729c8d3fb930eb8489bfb4"
RECORD = "docs/factory/d1-controller-phase-exact-registration-20261107.json"
VALIDATOR = "tools/check_d1_exact_registration.py"
PARENT_VALIDATOR = "tools/check_f2_fence_exceptions.py"
ORCHESTRATOR = "src/lightyear_factory/orchestrator.py"
PAYLOADS = {
    ORCHESTRATOR: ("beee29177a35c5a45f283fe888f5c417bebe7b62d9dd51fd1a9bd961bfd66add",
                   "f71635e613ef5aeef14923a1a16b4d4fdaf95e4b10ff8a6f713c39862996d7fd"),
    "src/lightyear_factory/controller_phase_capture.py": (None, "dd963493c2492495f608717b282ed3f683afd480bcf6b3fd94676eea2155f4dc"),
    "tests/test_controller_phase_capture.py": (None, "0957592bd180d1f63728ee1ee568705b5936bb818f75058049b24582163f09db"),
}
AUTHORITY = dict(merge=False, run=False, signing=False, spend=False, gap_acceptance=False)


def require(condition, code):
    if not condition:
        raise ValueError(code)


def fields(value, expected, code):
    require(type(value) is dict and set(value) == set(expected), code)


def digest(value, length):
    require(type(value) is str and re.fullmatch("[0-9a-f]{%d}" % length, value),
            "d1-digest")
    return value


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "d1-duplicate-json-key")
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique)


def timestamp(value):
    require(type(value) is str and value.endswith("Z"), "d1-timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("d1-timestamp") from None
    require(result.tzinfo is not None, "d1-timestamp")
    return result


def validate_record(record, *, now=None):
    fields(record, {"schema", "repository", "status", "source_anchor", "pr",
                    "candidate_commit", "entries", "approval", "authority"}, "d1-fields")
    require(record["schema"] == "d1-exact-source-registration/1" and
            record["repository"] == REPOSITORY and record["source_anchor"] == SOURCE_ANCHOR,
            "d1-target")
    require(record["authority"] == AUTHORITY, "d1-authority")
    expected = [dict(path=path, mode="100644", before_sha256=before, after_sha256=after)
                for path, (before, after) in sorted(PAYLOADS.items())]
    require(record["entries"] == expected, "d1-exact-payload-set")
    if record["status"] == "pending-exact-hash-approval":
        require(record["pr"] is None and record["candidate_commit"] is None and
                record["approval"] is None, "d1-pending-provenance")
        return None
    require(record["status"] == "approved-exact-hashes" and
            type(record["pr"]) is int and record["pr"] > 0 and record["pr"] != 455,
            "d1-approval-required")
    digest(record["candidate_commit"], 40)
    approval = record["approval"]
    fields(approval, {"source", "approved_by", "recorded_at_utc", "expires_at_utc",
                     "exact_sha256", "github_identity_is_human_proof"}, "d1-approval-fields")
    require(approval["source"] == "operator-chat" and approval["approved_by"] == "Howard Weale"
            and approval["github_identity_is_human_proof"] is False, "d1-provenance")
    require(approval["exact_sha256"] == {path: pair[1] for path, pair in PAYLOADS.items()},
            "d1-approval-hashes")
    start, end = timestamp(approval["recorded_at_utc"]), timestamp(approval["expires_at_utc"])
    current = now or datetime.now(timezone.utc)
    require(start <= current < end, "d1-approval-expired-or-future")
    return record


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def blob(repo, rev, path):
    rows = git(repo, "ls-tree", "-z", rev, "--", path)
    if not rows:
        return None
    metadata, actual = rows.rstrip(b"\0").split(b"\t")
    mode, kind, oid = metadata.decode().split()
    require(actual.decode() == path and mode == "100644" and kind == "blob", "d1-blob-mode")
    return hashlib.sha256(git(repo, "cat-file", "blob", oid)).hexdigest()


def inspect_registration(repo, base, head, report, event, environment, query, *, now=None):
    for path in (RECORD, VALIDATOR, PARENT_VALIDATOR):
        before = blob(repo, base, path)
        require(before is not None and before == blob(repo, head, path),
                "d1-candidate-control-change")
    unvalidated = parse(git(repo, "show", base + ":" + RECORD))
    kind = environment.get("GITHUB_EVENT_NAME")
    if unvalidated.get("status") == "pending-exact-hash-approval":
        return validate_record(unvalidated, now=now)
    if kind == "pull_request" and event.get("pull_request", {}).get("number") != unvalidated.get("pr"):
        return None  # Historical #455 path remains independently enforced.
    if kind == "push":
        parents = git(repo, "show", "-s", "--format=%P", head).decode().split()
        if len(parents) != 2 or parents[1] != unvalidated.get("candidate_commit"):
            return None
    record = validate_record(unvalidated, now=now)
    require(report["blocked_paths"] == [ORCHESTRATOR] and
            report["merge_permitted"] is False and report["automatic_expiry"] is False,
            "d1-raw-fence-scope")
    candidate = record["candidate_commit"]
    require(git(repo, "show", "-s", "--format=%P", candidate).decode().split() == [SOURCE_ANCHOR],
            "d1-candidate-parent")
    require(subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                            SOURCE_ANCHOR, base], capture_output=True).returncode == 0,
            "d1-base-ancestry")
    changed = set(filter(None, git(repo, "diff", "--no-renames", "--name-only", "-z",
                                  base, head).decode().split("\0")))
    require(changed == set(PAYLOADS), "d1-changed-file-set")
    for path, (before, after) in PAYLOADS.items():
        require(blob(repo, SOURCE_ANCHOR, path) == before and
                blob(repo, base, path) == before, "d1-preimage")
        require(blob(repo, candidate, path) == after and
                blob(repo, head, path) == after, "d1-postimage")
    require(environment.get("GITHUB_REPOSITORY") == REPOSITORY and
            event.get("repository", {}).get("full_name") == REPOSITORY,
            "d1-repository")
    live = query("pulls/" + str(record["pr"]))
    require(live.get("number") == record["pr"] and live.get("base", {}).get("ref") == "main"
            and live["head"]["sha"] == candidate and
            live["base"]["repo"]["full_name"] == REPOSITORY and
            live["head"]["repo"]["full_name"] == REPOSITORY, "d1-live-context")
    if kind == "pull_request":
        actual = event.get("pull_request", {})
        require(live.get("state") == "open" and live.get("merged", False) is False and
                live["base"]["sha"] == base and actual.get("number") == record["pr"] and
                actual.get("state") == "open" and actual.get("merged", False) is False and
                actual.get("base", {}).get("ref") == "main" and
                actual["base"]["sha"] == base and actual["head"]["sha"] == candidate and
                actual["base"]["repo"]["full_name"] == REPOSITORY and
                actual["head"]["repo"]["full_name"] == REPOSITORY, "d1-live-context")
    elif kind == "push":
        require(event.get("ref") == "refs/heads/main" and event.get("before") == base and
                event.get("after") == head and live.get("merged") is True and
                live.get("merge_commit_sha") == head and live.get("state") == "closed",
                "d1-exact-main-merge")
    else:
        raise ValueError("d1-pr-or-exact-merge-only")
    if head != candidate:
        require(git(repo, "show", "-s", "--format=%P", head).decode().split() == [base, candidate],
                "d1-merge-parents")
        expected_tree = git(repo, "merge-tree", "--write-tree", base, candidate).decode().strip()
        require(git(repo, "rev-parse", head + "^{tree}").decode().strip() == expected_tree,
                "d1-merge-tree")
    require(query("pulls/" + str(record["pr"])) == live, "d1-context-changed")
    return dict(schema="d1-exact-source-registration-result/1",
                candidate=candidate, pr=record["pr"], entries=record["entries"],
                raw_fence_report=report, fence_requirement_met=True,
                merge_authorized=False, run_authorized=False)
