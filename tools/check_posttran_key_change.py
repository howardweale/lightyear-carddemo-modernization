"""Read-only verification of the original executable plus a public-key replacement."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

RECORD = 'docs/factory/posttran-key-change-2026-10-23'
ORIGINAL = 'e4c6845ee9dd5ebc4eb4b3001cc7cde6fc70414b'
PLAN = 'docs/factory/posttran-phase2-plan-2026-10-16.json'
KEY = 'docs/factory/factory-authority.public.pem'
SEAL = 'bcccc1d3b05922108cbb6017abfe124b2fa4779613af0f20a5b43fd99c317126'
PEM = '658ba69010237ebc143a1e6d2c519f7d2adb1843993bc171c1d015e7b86b0c8a'

# Canonical JSON digest of the committed preservation record at
# 008cf01d3497f9ef5a964f1915171d622afdb969; original compiler pins unchanged.
PRESERVED_PROVENANCE = 'ac92a82742ed27f61ddcbe87a27df8821558a15c8d535ab743c281d04183c35e'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def inspect(root):
    root = Path(root)
    record = json.loads((root / RECORD / 'amendment.json').read_bytes())
    request = json.loads((root / RECORD / 'unsigned-request.json').read_bytes())
    pem = (root / RECORD / 'authority.public.pem').read_bytes()
    require(record['original_executable'] == ORIGINAL, 'original-executable')
    head = record['executable_commit']
    require(len(head) == 40 and all(c in '0123456789abcdef' for c in head), 'exact-executable')
    require(git(root, 'show', '-s', '--format=%P', head).decode().strip() == ORIGINAL, 'original-parent')
    changes = git(root, 'diff', '--name-only', ORIGINAL, head).decode().splitlines()
    require(changes == [KEY], 'key-only-tree')
    require(sha(pem) == PEM == record['new_pem_sha256'], 'posted-public-key')
    require(git(root, 'show', head + ':' + KEY) == pem, 'executable-key')
    require(sha(git(root, 'show', ORIGINAL + ':' + KEY)) == record['old_pem_sha256'], 'old-key')
    raw = git(root, 'show', head + ':' + PLAN)
    require(raw == git(root, 'show', ORIGINAL + ':' + PLAN), 'original-plan-bytes')
    plan = json.loads(raw)
    seal = sha(json.dumps({k:v for k,v in plan.items() if k != 'content_sha256'},
                          sort_keys=True, separators=(',', ':')).encode())
    require(seal == SEAL == plan['content_sha256'] == record['plan_seal'], 'original-seal')
    require(sha(raw) == record['plan_file_sha256'], 'plan-file-hash')
    require(len(plan['bound_files']) == 182 and KEY not in plan['bound_files'], 'bound-inventory')
    for path, expected in {**plan['bound_files'], **plan['candidate_files']}.items():
        require(sha(git(root, 'show', head + ':' + path)) == expected, 'bound-file')
    require(plan['generation_attempt'] == 1 and plan['retries'] == plan['model_calls'] == 0
            and plan['candidate_repair_authorized'] is False, 'one-attempt-no-repair')
    details = request['details']
    require(details['executable_commit'] == head and details['request_seal'] == SEAL, 'request-binding')
    require(details['caps'] == {'attempts':1, 'runs':1}, 'request-caps')
    require(details['observer_sha256'] == plan['bound_files']['.github/workflows/posttran-phase2.yml'], 'observer')
    require(details['class_hashes'] == dict(Candidate=plan['candidate_files']['spec/mainframe/posttran-independent/attempt-1/PosttranCandidate.java'],
            Provenance=plan['candidate_files']['spec/mainframe/posttran-independent/attempt-1/provenance.json'],
            CompilerImageArchive=plan['twin']['image_archive_sha256']), 'class-hashes')
    require(request['sources'] == [dict(path=PLAN, sha256=sha(raw), commit=head)], 'request-sources')
    require(details['window']['end'] == '2026-10-29T14:46:00+00:00', 'deadline')
    require(record['reservation_ref'] == 'refs/tags/posttran-phase2-consumed-' + SEAL, 'same-attempt-namespace')
    return record, plan


def image_check(record, plan, provenance, archive):
    require(provenance.get('schema') == 'posttran-compiler-preservation/1', 'archived-provenance-schema')
    require(sha(json.dumps(provenance, sort_keys=True, separators=(',', ':')).encode())
            == PRESERVED_PROVENANCE, 'archived-provenance')
    require(provenance['preservation_only'] is True
            and provenance['execution_authorized'] is False, 'preservation-only')
    metadata = provenance['original_artifact']
    require(metadata['id'] == record['compiler_artifact_id'], 'image-id')
    require(metadata['workflow_run']['id'] == plan['preparation_run']
            and metadata['workflow_run']['head_sha'] == plan['preparation_head'], 'image-provenance')
    require(metadata['name'] == plan['compiler_image_artifact'], 'image-name')
    retrieved = datetime.fromisoformat(provenance['retrieved_at'].replace('Z', '+00:00'))
    expires = datetime.fromisoformat(metadata['expires_at'].replace('Z', '+00:00'))
    require(retrieved < expires, 'retrieved-before-original-expiry')
    require(Path(archive).is_file(), 'archived-copy-missing')
    require(Path(archive).stat().st_size == metadata['size_in_bytes'], 'archive-size')
    digest = hashlib.sha256()
    with Path(archive).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    require(digest.hexdigest() == record['compiler_zip_sha256']
            and metadata['digest'] == 'sha256:' + digest.hexdigest(), 'archive-digest')
    with zipfile.ZipFile(archive) as z:
        require(z.namelist().count('compiler-image.tar') == 1, 'image-member')
        digest = hashlib.sha256()
        with z.open('compiler-image.tar') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''):
                digest.update(chunk)
    require(digest.hexdigest() == plan['twin']['image_archive_sha256'], 'image-bytes')
    return {'artifact_id':metadata['id'], 'image_sha256':digest.hexdigest(),
            'expires_at':metadata['expires_at'], 'source':'preserved-archive',
            'preservation_provenance_sha256':PRESERVED_PROVENANCE,
            'retrieved_at':provenance['retrieved_at']}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--artifact-metadata', type=Path)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    record, plan = inspect(args.root)
    require(bool(args.artifact_metadata) == bool(args.archive), 'paired-artifact-inputs')
    report = dict(executable_commit=record['executable_commit'], plan_seal=SEAL,
                  bound_files=182, changed_paths=[KEY], execution_authorized=False)
    if args.archive:
        report['compiler'] = image_check(record, plan, json.loads(args.artifact_metadata.read_bytes()), args.archive)
    print(json.dumps(report, sort_keys=True))
