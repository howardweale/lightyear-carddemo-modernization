"""Controller-owned candidate history; the agent workspace never contains Git data.

Identity/trailers are provenance signals, not cryptographic proof of the operator.
The controller must protect the history directory and bind it to its trusted CI run.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re
import subprocess

from .contracts import ContractError, canonical_hash
from .ledger import RunLedger
from .workspace import IsolatedWorkspace

FACTORY_NAME = "LIGHTYEAR Factory"
FACTORY_EMAIL = "factory@lightyear.invalid"
REF = "refs/heads/candidate"


class CandidateHistory:
    def __init__(self, workspace: IsolatedWorkspace, history: Path, run_id: str,
                 ledger: RunLedger) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}", run_id):
            raise ContractError("candidate-history-run-id")
        if workspace.read_manifest is None:
            raise ContractError("candidate-history-requires-allowlist")
        self.workspace = workspace
        self.history = history.resolve()
        if self.history == workspace.root or workspace.root in self.history.parents:
            raise ContractError("candidate-history-visible-to-agent")
        self.run_id, self.ledger = run_id, ledger
        self.start_commit = None

    def _git(self, *args: str, data: bytes | None = None,
             identity: tuple[str, str] | None = None,
             work_tree: bool = True) -> bytes:
        # No inherited alternate object database, config injection, hooks or signer.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_CONFIG_COUNT="0", GIT_TERMINAL_PROMPT="0")
        name, email = identity or (FACTORY_NAME, FACTORY_EMAIL)
        env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
                   GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)
        return subprocess.check_output([
            "git", "--git-dir=" + str(self.history),
            *(["--work-tree=" + str(self.workspace.root)] if work_tree else []),
            "-c", "core.hooksPath=" + os.devnull,
            "-c", "core.autocrlf=false", "-c", "commit.gpgSign=false",
            *args], env=env, input=data, stderr=subprocess.PIPE)

    def initialize(self) -> str:
        if self.history.exists():
            raise ContractError("candidate-history-already-exists")
        self.workspace.verify_read_boundary()
        self.history.parent.mkdir(parents=True, exist_ok=True)
        # Bare initialization must not receive --work-tree; later index and
        # candidate operations explicitly bind the separate workspace.
        self._git("init", "--bare", "--object-format=sha1", str(self.history),
                  work_tree=False)
        self._git("read-tree", "--empty")
        tree = self._git("write-tree").decode().strip()
        start = self._git("commit-tree", "--no-gpg-sign", tree,
                          data=("Factory run start\n\nFactory-Run: " + self.run_id +
                                "\nFactory-Attempt: 0\n").encode()).decode().strip()
        self._git("update-ref", REF, start, "0" * 40)
        self.start_commit = start
        self.ledger.append("ACCEPTED", "candidate_history_started", dict(
            run_id=self.run_id, start_commit=start, factory_name=FACTORY_NAME,
            factory_email=FACTORY_EMAIL,
            candidate_paths=list(self.workspace.allowed_paths)))
        return start

    def commit(self, attempt: int) -> str:
        if self.start_commit is None or type(attempt) is not int or not 1 <= attempt <= 3:
            raise ContractError("candidate-history-attempt")
        self.workspace.verify_read_boundary()
        # Only candidate paths enter the private index. Read-only inputs never do.
        for path in self.workspace.allowed_paths:
            tracked = self._git("ls-files", "--", path)
            if (self.workspace.root / path).exists() or tracked:
                self._git("add", "-A", "--", path)
        tree = self._git("write-tree").decode().strip()
        parent = self._git("rev-parse", REF).decode().strip()
        message = (f"Factory candidate attempt {attempt}\n\nFactory-Run: {self.run_id}\n"
                   f"Factory-Attempt: {attempt}\n")
        commit = self._git("commit-tree", "--no-gpg-sign", tree, "-p", parent,
                           data=message.encode()).decode().strip()
        self._git("update-ref", REF, commit, parent)
        self.ledger.append("BUILDING", "candidate_committed", dict(
            run_id=self.run_id, attempt=attempt, commit=commit, parent=parent,
            tree=tree, candidate_manifest_sha256=canonical_hash(self.workspace.snapshot())))
        return commit

    def audit(self, end: str, artifacts) -> dict:
        if self.start_commit is None or not re.fullmatch("[0-9a-f]{40}", end):
            raise ContractError("candidate-history-range")
        if end != self._git("rev-parse", REF).decode().strip():
            raise ContractError("candidate-history-stale-end")
        try:
            self._git("merge-base", "--is-ancestor", self.start_commit, end)
        except subprocess.CalledProcessError as exc:
            raise ContractError("candidate-history-unrelated-end") from exc
        # Walk every commit, including side branches and merges, without Git's
        # path-history simplification (which can hide a reverted human edit).
        commits = self._git("rev-list", "--reverse", "--topo-order",
                            self.start_commit + ".." + end).decode().splitlines()
        records = []
        for commit in commits:
            raw = self._git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", commit)
            name, email, committer, committer_email, message = raw.decode().split("\0", 4)
            parents = self._git("show", "-s", "--format=%P", commit).decode().split()
            diffs = []
            for parent in parents or [self._git("hash-object", "-t", "tree", "--stdin", data=b"").decode().strip()]:
                diff = self._git("diff", "--no-ext-diff", "--no-textconv", "--binary",
                                 parent, commit, "--", *self.workspace.allowed_paths)
                if diff:
                    diffs.append(dict(parent=parent, sha256=hashlib.sha256(diff).hexdigest(),
                                      diff_base64=base64.b64encode(diff).decode("ascii")))
            if not diffs:
                continue
            # Trailers must be the final paragraph, unique and exact. A quoted
            # trailer elsewhere in a human commit message grants no attribution.
            trailers = message.rstrip().split("\n\n")[-1].splitlines()
            valid_trailers = (len(trailers) == 2 and
                              trailers[0] == "Factory-Run: " + self.run_id and
                              re.fullmatch(r"Factory-Attempt: [1-3]", trailers[1]) is not None)
            identity_matches = (name == committer == FACTORY_NAME and
                                email == committer_email == FACTORY_EMAIL)
            factory = identity_matches and valid_trailers
            reference = artifacts.write("candidate-commit-diff", "controller", "verifier_private",
                                        dict(commit=commit, diffs=diffs))
            records.append(dict(commit=commit, author_name=name, author_email=email,
                                committer_name=committer, committer_email=committer_email,
                                factory=factory, human_intervention=not factory,
                                diff_artifact=reference))
        result = dict(schema="factory-candidate-authorship/1", run_id=self.run_id,
                      start_commit=self.start_commit, candidate_commit=end,
                      commits=records, human_interventions=sum(r["human_intervention"] for r in records),
                      qualification="Identity and trailers require a trusted controller run; not a signature.")
        result["content_sha256"] = canonical_hash(result)
        self.ledger.append("VERIFYING", "candidate_authorship_audited", result)
        return result
