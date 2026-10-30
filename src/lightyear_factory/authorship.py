"""Controller-owned candidate history; the agent workspace never contains Git data.

Legacy identity/trailers cannot qualify a factory receipt. The signed path verifies
ledger-bound builder responses and exact final bytes/modes; the trusted controller
must supply the externally provisioned CI signer.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import stat

from .contracts import ContractError, canonical_hash
from .ledger import RunLedger
from .process_environment import _without_provider_credentials
from .workspace import IsolatedWorkspace

FACTORY_NAME = "LIGHTYEAR Factory"
FACTORY_EMAIL = "factory@lightyear.invalid"
REF = "refs/heads/candidate"


class CandidateHistory:
    def __init__(self, workspace: IsolatedWorkspace, history: Path, run_id: str,
                 ledger: RunLedger, signer=None) -> None:
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
        if signer is not None and type(signer) is not CICommitSigner:
            raise ContractError("candidate-history-real-signer-required")
        self.signer = signer

    def _git(self, *args: str, data: bytes | None = None,
             identity: tuple[str, str] | None = None,
             work_tree: bool = True) -> bytes:
        # No inherited alternate object database, config injection, hooks or signer.
        env = {k: v for k, v in _without_provider_credentials().items() if not k.startswith("GIT_")}
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
        if self.signer is not None:
            # Preserve the approved input baseline; only subsequent broker changes
            # are attributed to model responses. This is not a generated candidate.
            for path in self.workspace.allowed_paths:
                if (self.workspace.root / path).exists():
                    self._git('add', '-A', '--', path)
        tree = self._git("write-tree").decode().strip()
        start = self._git("commit-tree", "--no-gpg-sign", tree,
                          data=("Factory run start\n\nFactory-Run: " + self.run_id +
                                "\nFactory-Attempt: 0\n").encode()).decode().strip()
        self._git("update-ref", REF, start, "0" * 40)
        self.start_commit = start
        self.ledger.append("ACCEPTED", "candidate_history_started", dict(
            run_id=self.run_id, start_commit=start, start_tree=tree, factory_name=FACTORY_NAME,
            factory_email=FACTORY_EMAIL,
            candidate_paths=list(self.workspace.allowed_paths)))
        return start

    def commit(self, attempt: int, *, response_events=None) -> str:
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
        if self.signer is not None:
            return self._verified_commit(attempt, tree, parent, response_events)
        if response_events is not None:
            raise ContractError("candidate-history-signer-required")
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
        if self.signer is not None:
            return self._verified_audit(end, artifacts)
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
                      cryptographically_verified=False, qualifies_for_factory_receipt=False,
                      qualification="Identity and trailers require a trusted controller run; not a signature.")
        result["content_sha256"] = canonical_hash(result)
        self.ledger.append("VERIFYING", "candidate_authorship_audited", result)
        return result


    def verify_before_build(self):
        """Reject changes outside the broker before a builder call is admitted."""
        if self.signer is None or self.start_commit is None:
            raise ContractError('candidate-history-signer-required')
        parent = self._git('rev-parse', REF).decode().strip()
        self._verify_package(parent)
        return parent

    def commit_applied_changes(self, attempt, *, parent, change_set, response_events):
        """Bind exact PatchBroker output to the current private Git tree."""
        if self.signer is None or self.start_commit is None:
            raise ContractError('candidate-history-signer-required')
        if parent != self._git('rev-parse', REF).decode().strip():
            raise ContractError('candidate-history-stale-parent')
        if (change_set.get('broker') != 'lightyear-constrained-patch-broker'
                or canonical_hash(change_set, {'content_sha256'}) != change_set.get('content_sha256')):
            raise ContractError('candidate-history-broker-binding')
        changes = change_set.get('changes', [])
        if not changes or len({r['path'] for r in changes}) != len(changes):
            raise ContractError('candidate-history-broker-paths')
        expected = self._candidate_tree(parent)
        mapping = {}
        for change in changes:
            path = change['path']
            if path not in expected or change['before_sha256'] != expected[path]['sha256']:
                raise ContractError('candidate-history-broker-before')
            expected[path] = dict(expected[path], sha256=change['after_sha256'])
            mapping[path] = list(response_events)
        # The broker only supports in-place regular-text changes. Refuse any
        # extra file, deletion, mode change or same-file mutation around it.
        self.workspace.verify_read_boundary()
        actual = self.workspace.snapshot()
        if set(actual) != set(expected) or any(actual[p] != expected[p]['sha256'] for p in actual):
            raise ContractError('candidate-history-broker-after')
        for path, entry in expected.items():
            mode = '100755' if (self.workspace.root/path).stat().st_mode & 0o111 else '100644'
            if mode != entry['mode']:
                raise ContractError('candidate-history-broker-mode')
        return self.commit(attempt, response_events=mapping)

    def _candidate_tree(self, revision):
        result = {}; entries = []; total = 0; seen = set()
        rows = [row for row in self._git('ls-tree', '-rz', revision).split(b'\0') if row]
        if len(rows) > 4096:
            raise ContractError('candidate-history-tree-limit')
        for row in rows:
            metadata, raw_path = row.split(b'\t', 1)
            mode, kind, oid = metadata.decode('ascii').split()
            path = raw_path.decode('utf-8')
            IsolatedWorkspace._strict_relative(path)
            if (kind != 'blob' or mode not in ('100644', '100755')
                    or not any(path == p or path.startswith(p.rstrip('/')+'/')
                               for p in self.workspace.allowed_paths)):
                raise ContractError('candidate-history-tree-boundary')
            size = int(self._git('cat-file', '-s', oid))
            total += size
            if path in seen or not 0 <= size <= 8*1024*1024 or total > 32*1024*1024:
                raise ContractError('candidate-history-tree-limit')
            seen.add(path); entries.append((path, mode, oid, size))
        # Refuse the whole tree's advertised sizes before materializing any blob.
        for path, mode, oid, size in entries:
            raw = self._git('cat-file', 'blob', oid)
            if len(raw) != size:
                raise ContractError('candidate-history-tree-size-mismatch')
            result[path] = dict(mode=mode, sha256=hashlib.sha256(raw).hexdigest())
        return result

    def _changed_tree_files(self, parent, tree):
        before, after = self._candidate_tree(parent), self._candidate_tree(tree)
        # A deletion has an explicit domain-separated digest, never an empty-file digest.
        absent = hashlib.sha256(b'factory-candidate-deleted/1').hexdigest()
        return {path: after[path]['sha256'] if path in after else absent
                for path in sorted(set(before) | set(after)) if before.get(path) != after.get(path)}

    def _verified_commit(self, attempt, tree, parent, response_events):
        proof = bind_candidate_changes(self.ledger, self.run_id, attempt,
                                       self._changed_tree_files(parent, tree), response_events or {})
        message = (f'Factory candidate attempt {attempt}\n\nFactory-Run: {self.run_id}\n'
                   f'Factory-Attempt: {attempt}\nFactory-Provenance: {proof["content_sha256"]}\n')
        commit = self.signer.sign(self, tree, parent, message.encode())
        # Signing adapters cannot substitute another tree or parent.
        if (self._git('show', '-s', '--format=%T %P', commit).decode().strip() != tree+' '+parent
                or self._git('show', '-s', '--format=%B', commit).decode().strip() != message.strip()):
            raise ContractError('candidate-history-signed-commit-mismatch')
        self._git('update-ref', REF, commit, parent)
        self.ledger.append('BUILDING', 'candidate_committed', dict(
            run_id=self.run_id, attempt=attempt, commit=commit, parent=parent, tree=tree,
            provenance=proof, signed=True))
        return commit

    def _verify_package(self, end):
        self.workspace.verify_read_boundary()
        tree = self._candidate_tree(end)
        current = self.workspace.snapshot()
        if set(current) != set(tree) or any(current[p] != tree[p]['sha256'] for p in current):
            raise ContractError('candidate-history-package-tree-mismatch')
        for path, entry in tree.items():
            item = self.workspace.root / path
            mode = '100755' if item.stat().st_mode & 0o111 else '100644'
            if item.is_symlink() or not item.is_file() or mode != entry['mode']:
                raise ContractError('candidate-history-package-mode-mismatch')
        return canonical_hash(tree)

    def verify_exported_package(self, end, destination, scanner):
        """Verify the package consumers receive against the signed candidate tree."""
        if self.signer is None or not callable(scanner):
            raise ContractError('candidate-package-verification-required')
        try:
            destination = Path(destination)
            if not destination.is_absolute() or not destination.is_dir():
                raise ValueError('destination')
            for part in (destination, *destination.parents):
                if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
                    raise ValueError('link')
            tree = self._candidate_tree(end)
            if not tree or len(tree) > 4096:
                raise ValueError('tree-limit')
            actual = {}; total = 0; entries = 0
            for path in destination.rglob('*'):
                entries += 1
                if entries > 8192 or path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                    raise ValueError('entry')
                relative = path.relative_to(destination).as_posix()
                IsolatedWorkspace._strict_relative(relative)
                info = path.stat()
                if stat.S_ISDIR(info.st_mode):
                    if not any(p.startswith(relative+'/') for p in tree):
                        raise ValueError('extra-directory')
                    continue
                if (relative not in tree or not stat.S_ISREG(info.st_mode)
                        or info.st_nlink != 1 or info.st_size > 8*1024*1024):
                    raise ValueError('file')
                total += info.st_size
                if total > 32*1024*1024:
                    raise ValueError('total-limit')
                with path.open('rb') as handle:
                    raw = handle.read(8*1024*1024+1)
                    opened = os.fstat(handle.fileno())
                after = path.stat()
                identity = lambda v: (v.st_dev,v.st_ino,v.st_size,v.st_mtime_ns,v.st_nlink,v.st_mode)
                if (identity(info) != identity(opened) or identity(info) != identity(after)
                        or len(raw) != info.st_size or path.is_symlink()):
                    raise ValueError('replacement')
                scanner('final-package-path', relative.encode('utf-8'))
                scanner('final-package-file', raw)
                actual[relative] = {'mode': '100755' if info.st_mode & 0o111 else '100644',
                                    'sha256': hashlib.sha256(raw).hexdigest()}
            if actual != tree:
                raise ValueError('tree-mismatch')
            return {'tree_sha256': canonical_hash(tree), 'files': len(tree), 'bytes': total}
        except Exception:
            raise ContractError('candidate-package-refused') from None

    def revalidate_exported_package(self, end, destination, manifest, scanner, artifacts):
        """Recheck retained package bytes and signatures when finalizing its run receipt."""
        try:
            if (self.signer is None or not callable(scanner)
                    or manifest.get('schema') != 'factory-candidate-package/1'
                    or manifest.get('run_id') != self.run_id
                    or manifest.get('candidate_commit') != end
                    or canonical_hash(manifest, {'content_sha256'}) != manifest.get('content_sha256')):
                raise ValueError('manifest')
            persisted = RunLedger(self.ledger.path)
            exports = [e for e in persisted.events if e['kind']=='candidate_package_verified'
                       and e['payload']==manifest]
            audits = [e for e in persisted.events if e['kind']=='candidate_authorship_audited'
                      and e['payload'].get('content_sha256')==manifest.get('authorship_audit_sha256')]
            if (persisted.events != self.ledger.events or len(exports)!=1 or len(audits)!=1
                    or persisted.events.index(audits[0]) >= persisted.events.index(exports[0])
                    or self._git('rev-parse', REF).decode().strip()!=end):
                raise ValueError('binding')
            # A retained manifest cannot replace current signature verification.
            verified = self.verify_exported_package(end, destination, scanner)
            audit = self.audit(end, artifacts)
            if (audit.get('qualifies_for_factory_receipt') is not True
                    or audit.get('cryptographically_verified') is not True
                    or audit.get('final_package_tree_sha256') != verified['tree_sha256']
                    or any(manifest.get(k)!=v for k,v in verified.items())
                    or self._git('rev-parse', REF).decode().strip()!=end):
                raise ValueError('drift')
            result = {'schema': 'factory-candidate-package-finalization/1',
                      'run_id': self.run_id, 'candidate_commit': end,
                      'package_manifest_sha256': manifest['content_sha256'],
                      'current_authorship_audit_sha256': audit['content_sha256'], **verified}
            result['content_sha256'] = canonical_hash(result)
            scanner('candidate-package-finalization', json.dumps(result,sort_keys=True).encode('utf-8'))
            self.ledger.append('VERIFYING', 'candidate_package_finalized', result)
            return result
        except Exception:
            raise ContractError('candidate-package-finalization-refused') from None

    def export_verified_package(self, end, destination, audit, scanner):
        if (self.signer is None or not callable(scanner)
                or audit.get('run_id') != self.run_id or audit.get('candidate_commit') != end
                or audit.get('qualifies_for_factory_receipt') is not True
                or audit.get('cryptographically_verified') is not True
                or canonical_hash(audit, {'content_sha256'}) != audit.get('content_sha256')):
            raise ContractError('candidate-package-audit-required')
        persisted = RunLedger(self.ledger.path)
        if (persisted.events != self.ledger.events or not persisted.events
                or persisted.events[-1]['kind'] != 'candidate_authorship_audited'
                or persisted.events[-1]['payload'] != audit
                or self._git('rev-parse', REF).decode().strip() != end):
            raise ContractError('candidate-package-audit-binding')
        try:
            destination = Path(destination)
            if not destination.is_absolute() or destination.exists():
                raise ValueError('destination')
            for part in (destination, *destination.parents):
                if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
                    raise ValueError('link')
            resolved = destination.resolve()
            if (resolved == self.workspace.root or self.workspace.root in resolved.parents
                    or resolved == self.history or self.history in resolved.parents):
                raise ValueError('exposed-destination')
            tree = self._candidate_tree(end)
            if not tree or len(tree) > 4096 or self._verify_package(end) != audit['final_package_tree_sha256']:
                raise ValueError('tree')
            destination.mkdir(parents=True)
            total = 0
            for relative, entry in sorted(tree.items()):
                size = int(self._git('cat-file', '-s', end+':'+relative))
                total += size
                if size > 8*1024*1024 or total > 32*1024*1024:
                    raise ValueError('byte-limit')
                raw = self._git('show', end+':'+relative)
                if len(raw) != size or hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise ValueError('blob')
                scanner('package-export-path', relative.encode('utf-8'))
                scanner('package-export-file', raw)
                target = destination/relative; target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as handle:
                    handle.write(raw)
                target.chmod(0o755 if entry['mode']=='100755' else 0o644)
            verified = self.verify_exported_package(end, destination, scanner)
            if (verified['tree_sha256'] != audit['final_package_tree_sha256']
                    or self._git('rev-parse', REF).decode().strip() != end
                    or self._verify_package(end) != verified['tree_sha256']):
                raise ValueError('final-drift')
            result = {'schema': 'factory-candidate-package/1', 'run_id': self.run_id,
                      'candidate_commit': end, 'authorship_audit_sha256': audit['content_sha256'],
                      **verified}
            result['content_sha256'] = canonical_hash(result)
            self.ledger.append('VERIFYING', 'candidate_package_verified', result)
            return result
        except Exception:
            raise ContractError('candidate-package-refused') from None

    def _verified_audit(self, end, artifacts):
        persisted = RunLedger(self.ledger.path)
        if persisted.events != self.ledger.events:
            raise ContractError('candidate-provenance-stale-ledger')
        starts = [e for e in persisted.events if e['kind']=='candidate_history_started'
                  and e['payload'].get('run_id')==self.run_id]
        start_tree = self._git('rev-parse', self.start_commit+'^{tree}').decode().strip()
        if (len(starts)!=1 or starts[0]['payload'].get('start_commit')!=self.start_commit
                or starts[0]['payload'].get('start_tree')!=start_tree):
            raise ContractError('candidate-history-baseline-binding')
        commits = self._git('rev-list', '--reverse', '--topo-order', self.start_commit+'..'+end).decode().splitlines()
        if not commits:
            raise ContractError('candidate-history-empty')
        records = []
        for commit in commits:
            # Every intervening commit is audited, including empty commits, merges and reverted edits.
            parents = self._git('show', '-s', '--format=%P', commit).decode().split()
            matches = [e for e in persisted.events if e['kind'] == 'candidate_committed'
                       and e['payload'].get('run_id') == self.run_id and e['payload'].get('commit') == commit]
            verified = False
            try:
                if len(parents) != 1 or len(matches) != 1:
                    raise ContractError('candidate-history-unrecorded-commit')
                event = matches[0]; record = event['payload']; proof = record.get('provenance', {})
                tree = self._git('rev-parse', commit+'^{tree}').decode().strip()
                if (record.get('signed') is not True or record.get('parent') != parents[0]
                        or record.get('tree') != tree or event['previous_sha256'] != proof.get('ledger_head_sha256')):
                    raise ContractError('candidate-history-ledger-binding')
                mapping = {f['path']: [r['event_sha256'] for r in f['model_responses']] for f in proof['files']}
                expected = bind_candidate_changes(self.ledger, self.run_id, record['attempt'],
                                                  self._changed_tree_files(parents[0], tree), mapping,
                                                  ledger_head=proof['ledger_head_sha256'])
                if proof != expected:
                    raise ContractError('candidate-history-provenance-mismatch')
                trailers = self._git('show', '-s', '--format=%B', commit).decode().rstrip().split('\n\n')[-1].splitlines()
                if trailers != [f'Factory-Run: {self.run_id}', f'Factory-Attempt: {record["attempt"]}',
                                f'Factory-Provenance: {proof["content_sha256"]}']:
                    raise ContractError('candidate-history-provenance-trailer')
                self.signer.verify(self, commit)
                verified = True
            except (ContractError, KeyError, TypeError, ValueError):
                verified = False
            diffs = [dict(parent=parent, diff_base64=base64.b64encode(self._git(
                'diff', '--no-ext-diff', '--no-textconv', '--binary', parent, commit)).decode('ascii'))
                     for parent in parents]
            reference = artifacts.write('candidate-commit-diff', 'controller', 'verifier_private',
                                        dict(commit=commit, diffs=diffs))
            records.append(dict(commit=commit, factory=verified, signature_and_provenance_verified=verified,
                                human_intervention=not verified, diff_artifact=reference))
        package_hash = self._verify_package(end)
        qualified = all(record['signature_and_provenance_verified'] for record in records)
        result = dict(schema='factory-candidate-authorship/1', run_id=self.run_id,
                      start_commit=self.start_commit, candidate_commit=end, commits=records,
                      human_interventions=sum(not r['factory'] for r in records),
                      cryptographically_verified=qualified, qualifies_for_factory_receipt=qualified,
                      final_package_tree_sha256=package_hash,
                      qualification='Each intervening commit requires a signature and ledger-bound builder responses.')
        result['content_sha256'] = canonical_hash(result)
        self.ledger.append('VERIFYING', 'candidate_authorship_audited', result)
        return result


def bind_candidate_changes(ledger, run_id, attempt, changed_files, response_events, *, ledger_head=None):
    """Join controller-computed changed bytes to completed builder transport events."""
    if type(attempt) is not int or not 1 <= attempt <= 3:
        raise ContractError('candidate-provenance-attempt')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}', run_id):
        raise ContractError('candidate-provenance-run')
    persisted = RunLedger(ledger.path)
    if persisted.events != ledger.events or not persisted.head_sha256:
        raise ContractError('candidate-provenance-stale-ledger')
    if not changed_files or set(changed_files) != set(response_events):
        raise ContractError('candidate-provenance-path-coverage')
    selected = persisted.events
    if ledger_head is not None:
        positions = [i for i, e in enumerate(selected) if e['event_sha256'] == ledger_head]
        if len(positions) != 1:
            raise ContractError('candidate-provenance-ledger-prefix')
        selected = selected[:positions[0]+1]
    events = {event['event_sha256']: event for event in selected}
    files = []
    for path, digest in sorted(changed_files.items()):
        IsolatedWorkspace._strict_relative(path)
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ContractError('candidate-provenance-file-digest')
        ids = response_events[path]
        if not isinstance(ids, (list, tuple)) or not ids or len(ids) != len(set(ids)):
            raise ContractError('candidate-provenance-response-coverage')
        responses = []
        for event_id in ids:
            event = events.get(event_id, {})
            payload = event.get('payload', {})
            response = payload.get('response') or {}
            start = events.get(payload.get('start_event_sha256'), {})
            begun = start.get('payload', {})
            if (event.get('kind') != 'model-transport-finished' or payload.get('run_id') != run_id
                    or payload.get('attempt') != attempt or payload.get('role') != 'builder'
                    or payload.get('status') != 'response' or payload.get('response_complete') is not True
                    or start.get('kind') != 'model-transport-started'
                    or start.get('sequence', 0) >= event.get('sequence', 0)
                    or any(begun.get(key) != payload.get(key) for key in
                           ('run_id', 'attempt', 'role', 'request', 'provider', 'configured_model_version'))
                    or response.get('artifact_type') != 'model-response'
                    or response.get('run_id') != run_id or response.get('role') != 'builder'
                    or response.get('visibility') != 'controller-encrypted'
                    or any(not isinstance(response.get(key), str) or not re.fullmatch('[0-9a-f]{64}', response[key])
                           for key in ('plaintext_sha256', 'artifact_sha256', 'ciphertext_sha256'))):
                raise ContractError('candidate-provenance-unverified-response')
            responses.append(dict(event_sha256=event_id, response_sha256=response['plaintext_sha256'],
                                  encrypted_artifact_sha256=response.get('artifact_sha256')))
        files.append(dict(path=path, sha256=digest, model_responses=responses))
    result = dict(schema='factory-candidate-provenance/1', run_id=run_id, attempt=attempt,
                  ledger_head_sha256=selected[-1]['event_sha256'], files=files)
    result['content_sha256'] = canonical_hash(result)
    return result


class CICommitSigner:
    """Use externally provisioned CI SSH key files; never generate or persist keys."""

    def __init__(self, key_path: Path, allowed_signers: Path, workspace: Path):
        self.workspace = workspace.resolve()
        self.key_path = Path(key_path).absolute()
        self.allowed_signers = Path(allowed_signers).absolute()
        self._check_ci()

    def _check_ci(self):
        if (os.environ.get('GITHUB_ACTIONS') != 'true'
                or os.environ.get('GITHUB_REF') != 'refs/heads/main'
                or os.environ.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch')
                or not re.fullmatch('[0-9a-f]{40}', os.environ.get('GITHUB_SHA', ''))):
            raise ContractError('candidate-signing-trusted-main-ci-required')
        temp = os.environ.get('RUNNER_TEMP')
        if not temp:
            raise ContractError('candidate-signing-temp-required')
        root = Path(temp).resolve()
        for path in (self.key_path, self.allowed_signers):
            cursor = path
            while cursor != cursor.parent:
                if cursor.is_symlink() or getattr(cursor, 'is_junction', lambda: False)():
                    raise ContractError('candidate-signing-key-link')
                cursor = cursor.parent
            resolved = path.resolve()
            if (not path.is_file() or root not in resolved.parents or resolved == self.workspace
                    or self.workspace in resolved.parents):
                raise ContractError('candidate-signing-external-key-required')
        lines = self.allowed_signers.read_text(encoding='utf-8').splitlines()
        if len(lines) != 1 or not re.fullmatch(re.escape(FACTORY_EMAIL) + r' ssh-ed25519 [A-Za-z0-9+/]+={0,2}', lines[0]):
            raise ContractError('candidate-signing-single-factory-trust-required')

    def sign(self, history, tree, parent, message):
        self._check_ci()
        if history.workspace.root != self.workspace:
            raise ContractError('candidate-signing-workspace-binding')
        commit = history._git('-c', 'gpg.format=ssh', '-c', 'user.signingKey='+str(self.key_path),
                              'commit-tree', '-S', tree, '-p', parent, data=message).decode().strip()
        self.verify(history, commit)
        return commit

    def verify(self, history, commit):
        self._check_ci()
        if history.workspace.root != self.workspace or not re.fullmatch('[0-9a-f]{40}', commit):
            raise ContractError('candidate-signing-commit-binding')
        try:
            history._git('-c', 'gpg.format=ssh', '-c', 'gpg.ssh.allowedSignersFile='+str(self.allowed_signers),
                         'verify-commit', commit)
        except subprocess.CalledProcessError as exc:
            raise ContractError('candidate-signature-unverified') from exc
        return True
