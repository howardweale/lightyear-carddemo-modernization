"""Exclusive local intent for a separately approved disposable publication.

No approval, preflight, remote write, retry, signer, nonce or model authority.
The actual host caller must run original preservation and all native guards.
An existing or partial intent is never repaired, resumed, overwritten or deleted.
"""
import hashlib,os,re,stat
from pathlib import Path

def _require(ok,code):
    if not ok:raise ValueError(code)

def _root(root):
    root=Path(root)
    _require(root.is_absolute() and root.resolve(strict=True)==root and root.is_dir(),'intent-absolute-root')
    for part in (root,*root.parents):
        _require(not part.is_symlink() and not getattr(part.lstat(),'st_file_attributes',0)&0x400
            and 'onedrive' not in str(part).lower(),'intent-root-reparse-or-original')
    return root

def _binding(executable,metadata_head,request_sha256,branch_ref):
    _require(all(type(x) is str and re.fullmatch('[0-9a-f]{40}',x) for x in (executable,metadata_head))
        and executable!=metadata_head,'intent-exact-E-M')
    _require(type(request_sha256) is str and re.fullmatch('[0-9a-f]{64}',request_sha256),'intent-exact-requests')
    _require(type(branch_ref) is str and re.fullmatch('refs/heads/codex/[A-Za-z0-9_-]+',branch_ref),
        'intent-exact-codex-ref')
    return ('DISPOSABLE PUBLICATION INTENT; NOT APPROVAL OR QUALIFICATION\n'
        'repository=howardweale/lightyear-carddemo-modernization\nE='+executable+
        '\nM='+metadata_head+'\nrequests_sha256='+request_sha256+'\nref='+branch_ref+'\n').encode('ascii')

def _stable_read(path):
    before=path.lstat()
    _require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and not path.is_symlink()
        and not getattr(before,'st_file_attributes',0)&0x400 and 0<before.st_size<=2048,'intent-file-shape')
    def identity(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    with path.open('rb') as stream:
        opened=os.fstat(stream.fileno());raw=stream.read(2049);after=os.fstat(stream.fileno())
    final=path.lstat()
    # Windows path-stat and handle-stat can expose different ctime values.
    # Preserve each API's complete before/after identity including ctime;
    # compare common device/inode/size/mtime across the two APIs.
    _require(identity(before)==identity(final) and identity(opened)==identity(after)
        and identity(before)[:-1]==identity(opened)[:-1]
        and len(raw)==before.st_size,'intent-file-changed')
    return raw

def verify_intent(root,*,executable,metadata_head,request_sha256,branch_ref):
    expected=_binding(executable,metadata_head,request_sha256,branch_ref)
    root=_root(root);path=root/'operator-publication-intent.txt'
    _require(_stable_read(path)==expected,'intent-binding-changed')
    return hashlib.sha256(expected).hexdigest()

def reserve_intent(root,*,executable,metadata_head,request_sha256,branch_ref):
    expected=_binding(executable,metadata_head,request_sha256,branch_ref)
    root=_root(root);path=root/'operator-publication-intent.txt'
    # O_EXCL through xb is the one-shot boundary; no existence-check race.
    # File fsync is not a claim of directory/power-loss durability on every OS.
    with path.open('xb') as stream:
        stream.write(expected);stream.flush();os.fsync(stream.fileno())
    return verify_intent(root,executable=executable,metadata_head=metadata_head,
        request_sha256=request_sha256,branch_ref=branch_ref)


# Pure scope comparison data, never approval, a reusable receipt or a schema.
def operation_scope(intent_root, executable_root, metadata_root, trust_path, empty_hooks, *, values, reviewer_run_id, reviewer_job_id, pr_number, base, tested_merge, branch_ref, expected_request_sha256, expected_main_protection_sha256, expected_main_rules_sha256, expected_java_fence_sha256, expected_posttran_inventory_sha256):
    _require(type(values) is dict and set(values) == set(('executable', 'metadata_head', 'producer_run_id', 'artifact_id', 'archive_sha256', 'plan_sha256', 'decision_sha256', 'journal_head_sha256', 'public_key_sha256', 'nonce_sha256', 'commit_epoch')), 'host-one-shot-exact-public-inputs')
    _require(all((type(values[k]) is int and 0 < values[k] < 10 ** 20 for k in ('producer_run_id', 'artifact_id', 'commit_epoch'))), 'host-one-shot-public-integer-types')
    _require(all((type(values[k]) is str and re.fullmatch('[0-9a-f]{40}', values[k]) for k in ('executable', 'metadata_head'))) and all((type(values[k]) is str and re.fullmatch('[0-9a-f]{64}', values[k]) for k in ('archive_sha256', 'plan_sha256', 'decision_sha256', 'journal_head_sha256', 'public_key_sha256', 'nonce_sha256'))), 'host-one-shot-public-digest-types')
    public = tuple(((k, type(values[k]).__name__, values[k]) for k in ('executable', 'metadata_head', 'producer_run_id', 'artifact_id', 'archive_sha256', 'plan_sha256', 'decision_sha256', 'journal_head_sha256', 'public_key_sha256', 'nonce_sha256', 'commit_epoch')))
    identity = dict(reviewer_run_id=reviewer_run_id, reviewer_job_id=reviewer_job_id, pr_number=pr_number)
    _require(all((type(v) is int and 0 < v < 10 ** 20 for v in identity.values())), 'host-one-shot-reviewer-integer-types')
    commits = dict(base=base, tested_merge=tested_merge)
    _require(all((type(v) is str and re.fullmatch('[0-9a-f]{40}', v) for v in commits.values())), 'host-one-shot-reviewer-commit-types')
    digests = dict(expected_request_sha256=expected_request_sha256, expected_main_protection_sha256=expected_main_protection_sha256, expected_main_rules_sha256=expected_main_rules_sha256, expected_java_fence_sha256=expected_java_fence_sha256, expected_posttran_inventory_sha256=expected_posttran_inventory_sha256)
    _require(all((type(v) is str and re.fullmatch('[0-9a-f]{64}', v) for v in digests.values())), 'host-one-shot-independent-guard-digests')
    _require(type(branch_ref) is str and re.fullmatch('refs/heads/codex/[A-Za-z0-9_-]+', branch_ref), 'host-one-shot-exact-branch')
    paths = dict(intent_root=intent_root, executable_root=executable_root, metadata_root=metadata_root, trust_path=trust_path, empty_hooks=empty_hooks)
    _require(all((type(v) in (str, type(Path())) and Path(v).is_absolute() for v in paths.values())), 'host-one-shot-bound-path-types')
    wanted = (('values', public), ('identity', tuple(sorted(identity.items()))), ('commits', tuple(sorted(commits.items()))), ('digests', tuple(sorted(digests.items()))), ('branch_ref', branch_ref), ('paths', tuple(((k, str(Path(v))) for k, v in sorted(paths.items())))))
    return wanted
