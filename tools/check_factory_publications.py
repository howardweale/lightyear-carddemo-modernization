"""Verify committed main-side packages as Git data; never execute candidate code."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

REGISTRY = "factory/candidate-publications"
SHA = re.compile(r"[0-9a-f]{40}")
RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
TRUST = re.compile(r"factory@lightyear\.invalid ssh-ed25519 [A-Za-z0-9+/]+={0,2}\n?")


class Intervention(ValueError):
    """A publication is missing, changed, unsigned, or unbound."""


def git(root, *args):
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0")
    try:
        result = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=60)
    except (subprocess.SubprocessError, OSError):
        raise Intervention("factory-publication-git-refused") from None
    if len(result.stdout) > 34 * 1024 * 1024:
        raise Intervention("factory-publication-output-limit")
    return result.stdout


def safe_path(value):
    if (not value or "\\" in value or "\x00" in value or value.startswith("/")
            or any(part in ("", ".", "..") or part.casefold() == ".git" or ":" in part
                   for part in value.split("/"))):
        raise Intervention("factory-publication-path-refused")
    return value


def tree(root, revision, prefix=None):
    args = ["ls-tree", "-rz", revision]
    if prefix is not None:
        args += ["--", safe_path(prefix)]
    rows = git(root, *args).split(b"\0")
    result = {}
    for row in rows:
        if not row:
            continue
        metadata, path = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        path = safe_path(path.decode("utf-8"))
        if kind != "blob" or mode not in ("100644", "100755") or not SHA.fullmatch(oid):
            raise Intervention("factory-publication-nonregular-entry")
        result[path] = (mode, oid)
    if len(result) > 8192:
        raise Intervention("factory-publication-file-limit")
    return result


def blob(root, oid, limit):
    size = int(git(root, "cat-file", "-s", oid))
    if not 0 <= size <= limit:
        raise Intervention("factory-publication-blob-limit")
    raw = git(root, "cat-file", "blob", oid)
    if len(raw) != size:
        raise Intervention("factory-publication-blob-size")
    return raw


def manifest(root, path, entry):
    if entry[0] != "100644":
        raise Intervention("factory-publication-manifest-mode")
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise Intervention("factory-publication-duplicate-key")
            out[key] = value
        return out
    try:
        value = json.loads(blob(root, entry[1], 32768), object_pairs_hook=unique)
    except (ValueError, TypeError, UnicodeError):
        raise Intervention("factory-publication-manifest-invalid") from None
    required = {"schema", "run_id", "candidate_base", "candidate_commit", "candidate_tree",
                "source_receipt_sha256"}
    if (not isinstance(value, dict) or set(value) != required
            or value["schema"] != "factory-main-publication/1"
            or not isinstance(value["run_id"], str) or not RUN.fullmatch(value["run_id"])
            or path != f"{REGISTRY}/{value['run_id']}/publication.json"
            or any(not isinstance(value[k], str) or not SHA.fullmatch(value[k])
                   for k in ("candidate_base", "candidate_commit", "candidate_tree"))
            or not isinstance(value["source_receipt_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["source_receipt_sha256"])):
        raise Intervention("factory-publication-manifest-binding")
    return value


def verify_signature(root, commit, allowed_signers):
    # No signing operation or private key is used. Trust is never read from the candidate.
    git(root, "-c", "gpg.format=ssh", "-c", "gpg.ssh.program=ssh-keygen",
        "-c", "gpg.ssh.allowedSignersFile=" + str(allowed_signers), "verify-commit", commit)


def verify_package(root, main_tree, record, allowed_signers, *, fetch_candidates=False):
    base, end = record["candidate_base"], record["candidate_commit"]
    if fetch_candidates:
        try:
            git(root, "cat-file", "-e", end + "^{commit}")
            git(root, "cat-file", "-e", base + "^{commit}")
        except Intervention:
            git(root, "fetch", "--no-tags", "--no-write-fetch-head", "origin", end)
    git(root, "merge-base", "--is-ancestor", base, end)
    commits = git(root, "rev-list", "--reverse", base + ".." + end).decode().splitlines()
    if not 1 <= len(commits) <= 3:
        raise Intervention("factory-publication-history-bound")
    parent = base
    previous_attempt = 0
    for commit in commits:
        if not SHA.fullmatch(commit) or git(root, "show", "-s", "--format=%P", commit).decode().strip() != parent:
            raise Intervention("factory-publication-intervening-commit")
        trailers = git(root, "show", "-s", "--format=%B", commit).decode().rstrip().split("\n\n")[-1].splitlines()
        if (len(trailers) != 3 or trailers[0] != "Factory-Run: " + record["run_id"]
                or not re.fullmatch(r"Factory-Attempt: [1-3]", trailers[1])
                or not re.fullmatch(r"Factory-Provenance: [0-9a-f]{64}", trailers[2])):
            raise Intervention("factory-publication-trailer-binding")
        attempt = int(trailers[1][-1])
        if attempt <= previous_attempt:
            raise Intervention("factory-publication-attempt-order")
        verify_signature(root, commit, allowed_signers)
        previous_attempt, parent = attempt, commit
    if parent != end or git(root, "rev-parse", end + "^{tree}").decode().strip() != record["candidate_tree"]:
        raise Intervention("factory-publication-final-tree-binding")
    candidate = tree(root, end)
    prefix = f"{REGISTRY}/{record['run_id']}/package/"
    package = {path[len(prefix):]: entry for path, entry in main_tree.items() if path.startswith(prefix)}
    if not candidate or len(candidate) > 4096 or candidate != package:
        raise Intervention("factory-publication-package-intervention")
    total = 0
    for mode, oid in candidate.values():
        total += len(blob(root, oid, 8 * 1024 * 1024))
        if total > 32 * 1024 * 1024:
            raise Intervention("factory-publication-package-size")
    return dict(run_id=record["run_id"], candidate_commit=end, candidate_tree=record["candidate_tree"],
                source_receipt_sha256=record["source_receipt_sha256"], files=len(candidate), bytes=total,
                signatures_verified=len(commits), status="verified")


def verify_main(root, main_commit, trust_text, temp_root, *, fetch_candidates=False):
    if not SHA.fullmatch(main_commit):
        raise Intervention("factory-publication-main-binding")
    current = tree(root, main_commit, REGISTRY)
    parents = git(root, "show", "-s", "--format=%P", main_commit).decode().split()
    previous = tree(root, parents[0], REGISTRY) if parents else {}
    prior_manifests = {p: e for p, e in previous.items() if re.fullmatch(re.escape(REGISTRY) + r"/[^/]+/publication\.json", p)}
    if any(current.get(p) != entry for p, entry in prior_manifests.items()):
        raise Intervention("factory-publication-record-removal-or-rewrite")
    records = [manifest(root, p, e) for p, e in current.items() if re.fullmatch(re.escape(REGISTRY) + r"/[^/]+/publication\.json", p)]
    if len(records) > 128:
        raise Intervention("factory-publication-record-limit")
    covered = set()
    for record in records:
        stem = f"{REGISTRY}/{record['run_id']}/"
        covered.add(stem + "publication.json")
        covered.update(p for p in current if p.startswith(stem + "package/"))
    if covered != set(current):
        raise Intervention("factory-publication-unbound-path")
    if not records:
        return dict(schema="factory-main-package-verification/1", main_commit=main_commit,
                    status="no-candidates", packages=[], factory_run_acceptance=False)
    if not TRUST.fullmatch(trust_text):
        raise Intervention("factory-publication-external-trust-required")
    temp_root = Path(temp_root).resolve()
    if temp_root == root.resolve() or root.resolve() in temp_root.parents:
        raise Intervention("factory-publication-external-temp-required")
    with tempfile.TemporaryDirectory(prefix="factory-publication-", dir=temp_root) as directory:
        trust = Path(directory) / "allowed-signers"
        trust.write_text(trust_text, encoding="utf-8")
        packages = [verify_package(root, current, record, trust, fetch_candidates=fetch_candidates)
                    for record in records]
    return dict(schema="factory-main-package-verification/1", main_commit=main_commit,
                status="verified", packages=packages, trust_sha256=hashlib.sha256(trust_text.encode()).hexdigest(),
                factory_run_acceptance=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        head = os.environ.get("GITHUB_SHA", "")
        if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "push"
                or os.environ.get("GITHUB_REF") != "refs/heads/main" or not SHA.fullmatch(head)
                or git(root, "rev-parse", "HEAD").decode().strip() != head):
            raise Intervention("factory-publication-trusted-main-required")
        result = verify_main(root, head, os.environ.get("FACTORY_PUBLIC_ALLOWED_SIGNERS", ""),
                             os.environ.get("RUNNER_TEMP", ""), fetch_candidates=True)
    except (Intervention, KeyError, ValueError, OSError, UnicodeError):
        print(json.dumps(dict(schema="factory-main-package-verification/1", status="intervention",
                              factory_run_acceptance=False, reason="factory-publication-refused")))
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
