"""Verify newly quoted commit references against explicit, machine-checkable claims.

Only added lines are checked; a filename date cannot exempt a new claim.
Unchanged historical bytes stay untouched. Git metadata and blobs are read only.
"""
import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CLAIMS = 'docs/factory/commit-claims-2026-10-17.json'
ROLE_CORRECTIONS = 'docs/factory/commit-claim-role-corrections-2026-10-18.json'
GENERATED_STATUS = ('docs/factory/current-status.json', 'docs/factory/current-status.md')
REF = re.compile(r'(?<![A-Za-z0-9])([0-9a-f]{7,40})(?![A-Za-z0-9])')


def git(root,*args):
    return subprocess.check_output(['git',*args],cwd=root)


def resolve(root,reference):
    if not re.fullmatch(r'[0-9a-f]{7,40}',reference):raise ValueError('record-commit-reference')
    try:return git(root,'rev-parse','--verify',reference+'^{commit}').decode().strip()
    except subprocess.CalledProcessError as error:raise ValueError('record-commit-unresolved:'+reference) from error


def validate_claim(root,claim):
    commit=resolve(root,claim['reference'])
    if commit!=claim['commit']:raise ValueError('record-commit-identity')
    role=claim['role']
    if role in ('source','publication'):
        prefix='source' if role=='source' else 'publication'
        path=claim[prefix+'_path']
        if path.startswith('/') or '..' in path.split('/') or ':' in path:raise ValueError('record-source-path')
        mode=git(root,'ls-tree',commit,'--',path).decode()
        if not mode.startswith(('100644 blob ','100755 blob ')):raise ValueError('record-source-regular-blob')
        if sha256(git(root,'show',commit+':'+path)).hexdigest()!=claim[prefix+'_sha256']:
            raise ValueError('record-commit-source-mismatch')
    elif role=='merge':
        parents=git(root,'show','-s','--format=%P',commit).decode().split()
        if len(parents)!=2 or parents!=claim['parents'] or parents[1]!=claim['head_commit']:
            raise ValueError('record-commit-merge-parents')
        message=git(root,'show','-s','--format=%B',commit).decode()
        if not re.search(r'#'+str(int(claim['pr']))+r'\b',message):raise ValueError('record-commit-merge-pr')
    elif role=='ancestor':
        descendant=resolve(root,claim['descendant'])
        try:git(root,'merge-base','--is-ancestor',commit,descendant)
        except subprocess.CalledProcessError as error:raise ValueError('record-commit-not-ancestor') from error
    else:raise ValueError('record-commit-claim-role')
    return commit


def references(lines, *, record=''):
    lines = list(lines)
    hashes = set(re.findall(r'(?<![A-Za-z0-9])[0-9a-f]{64}(?![A-Za-z0-9])', record+'\n'+'\n'.join(lines)))
    result = set()
    for line in lines:
        for match in REF.finditer(line):
            ref = match[1]
            if not re.search('[a-f]', ref):
                continue
            before = line[:match.start()]
            # Explicit hash labels identify abbreviations without guessing from
            # unrelated words elsewhere on a line containing several claims.
            hash_label = re.search(r'(?:sha-?256|checksum|digest|content[ _-]hash)(?:[ _-]prefix)?["\'`:= \t]*$', before, re.I)
            commit_label = re.search(r'(?:commit|revision|head|ancestor|parent)["\'`:= \t]*$', before, re.I)
            known_hash_prefix = len(ref) <= 12 and any(h.startswith(ref) for h in hashes)
            if hash_label or (known_hash_prefix and not commit_label):
                continue
            result.add(ref)
    return result


def claim_manifests(root):
    """Read every claim registry, including later and non-date-specific files."""
    root=Path(root);manifests={}
    for path in sorted((root/'docs/factory').glob('commit-claims-*.json')):
        data=json.loads(path.read_bytes())
        if not isinstance(data,dict) or not isinstance(data.get('claims'),list):
            raise ValueError('record-commit-claims-schema')
        if any(not isinstance(row,dict) for row in data['claims']):
            raise ValueError('record-commit-claims-schema')
        manifests[path.relative_to(root).as_posix()]=data['claims']
    return manifests


def correction_manifests(root):
    """Bind each correction's preparation date to its own dated filename."""
    root=Path(root);manifests={}
    for path in sorted((root/'docs/factory').glob('commit-claim-role-corrections-*.json')):
        match=re.fullmatch(r'commit-claim-role-corrections-(20\d\d-\d\d-\d\d)\.json',path.name)
        if not match:raise ValueError('record-role-correction-date')
        try:prepared_on=date.fromisoformat(match[1]).isoformat()
        except ValueError as error:raise ValueError('record-role-correction-date') from error
        data=json.loads(path.read_bytes())
        if (not isinstance(data,dict) or data.get('schema')!='record-commit-role-corrections/1'
                or data.get('prepared_on')!=prepared_on or not isinstance(data.get('corrections'),list)):
            raise ValueError('record-role-correction-schema')
        if any(not isinstance(row,dict) for row in data['corrections']):
            raise ValueError('record-role-correction-schema')
        manifests[path.relative_to(root).as_posix()]=data['corrections']
    return manifests


def current_claims(root):
    """Apply only hash-bound source-to-publication role corrections.

    Historical registries stay byte-identical. A correction cannot change
    the referenced commit, record, path or blob hash or create a new claim.
    """
    claims=[claim for rows in claim_manifests(root).values() for claim in rows]
    seen=set()
    for rows in correction_manifests(root).values():
        for row in rows:
            key=(row['record'],row['reference'])
            if key in seen:raise ValueError('record-role-correction-duplicate')
            seen.add(key)
            matches=[i for i,c in enumerate(claims) if (c['record'],c['reference'])==key]
            if len(matches)!=1:raise ValueError('record-role-correction-missing')
            index=matches[0];old=claims[index]
            raw=json.dumps(old,sort_keys=True,separators=(',',':')).encode()
            if sha256(raw).hexdigest()!=row['previous_claim_sha256'] or old['role']!='source':
                raise ValueError('record-role-correction-binding')
            wanted={k:v for k,v in old.items() if k not in ('role','source_path','source_sha256')}
            wanted.update(role='publication',publication_path=old['source_path'],publication_sha256=old['source_sha256'])
            if row['replacement']!=wanted:raise ValueError('record-role-correction-changes-evidence')
            validate_claim(root,wanted);claims[index]=wanted
    return claims


def render_generated_status(root):
    """Use the existing evidence-verifying renderer, without writing outputs."""
    from tools.release_status_records import inputs, load, render
    paths = tuple(inputs(root))
    before = generated_input_blobs(root, paths)
    view, text = render(load(root))
    if tuple(inputs(root)) != paths or generated_input_blobs(root, paths) != before:
        raise ValueError('record-generated-input-changed')
    return {
        GENERATED_STATUS[0]: (json.dumps(view, indent=2)+'\n').encode('utf-8'),
        GENERATED_STATUS[1]: text.encode('utf-8'),
    }


def generated_input_blobs(root, paths):
    """Bind discovered renderer inputs to committed regular files."""
    blobs = {}
    for name in paths:
        if not isinstance(name, str):
            raise ValueError('record-generated-input-path')
        path = Path(name)
        if (path.is_absolute() or ':' in name
                or '\\' in name or '..' in path.parts or path.as_posix() != name):
            raise ValueError('record-generated-input-path')
        entry = git(root, 'ls-tree', '-z', 'HEAD', '--', name).split(b'\0')
        if len(entry) != 2 or not entry[0].startswith((b'100644 blob ', b'100755 blob ')):
            raise ValueError('record-generated-input-uncommitted')
        if entry[0].split(b'\t', 1)[1].decode() != name:
            raise ValueError('record-generated-input-path')
        file = root/path
        if any(p.is_symlink() for p in [file, *file.parents] if p != root.parent):
            raise ValueError('record-generated-input-link')
        blob = git(root, 'show', 'HEAD:'+name)
        if file.read_bytes() != blob:
            raise ValueError('record-generated-input-uncommitted')
        blobs[name] = sha256(blob).hexdigest()
    return blobs


def validate_generated_status(root):
    """Generated identifiers are valid only within the exact verified projection.

    This does not authorize a status PR: check_status_pr independently enforces
    the bot identity, source branch and two-output-only policy.
    """
    head = git(root, 'rev-parse', 'HEAD')
    if git(root, 'status', '--porcelain=v1', '--untracked-files=no').strip():
        raise ValueError('record-generated-dirty-inputs')
    expected = render_generated_status(root)
    if set(expected) != set(GENERATED_STATUS):
        raise ValueError('record-generated-output-set')
    for name in GENERATED_STATUS:
        entry = git(root, 'ls-tree', '-z', 'HEAD', '--', name)
        if not entry.startswith(b'100644 blob ') or entry.count(b'\0') != 1:
            raise ValueError('record-generated-output-mode')
        if entry.split(b'\t', 1)[1][:-1].decode() != name:
            raise ValueError('record-generated-output-path')
        if git(root, 'show', 'HEAD:'+name) != expected[name]:
            raise ValueError('record-generated-output-mismatch:'+name)
    if (git(root, 'rev-parse', 'HEAD') != head
            or git(root, 'status', '--porcelain=v1', '--untracked-files=no').strip()):
        raise ValueError('record-generated-input-changed')


def check(root,base):
    root=Path(root)
    names=git(root,'diff','--name-only','--diff-filter=ACMR',base,'HEAD','--','docs/factory','docs/milestones').decode().splitlines()
    changed=git(root,'diff','--no-renames','--name-only','-z',base,'HEAD','--',*GENERATED_STATUS).split(b'\0')
    if any(changed):validate_generated_status(root)
    manifests=set(claim_manifests(root)) | set(correction_manifests(root))
    claims=current_claims(root)
    rows=[]
    for name in names:
        if name in manifests or name in GENERATED_STATUS:continue
        patch=git(root,'diff','--unified=0',base,'HEAD','--',name).decode('utf-8')
        added=[line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
        record=git(root,'show','HEAD:'+name).decode('utf-8',errors='replace') if added else ''
        refs=references(added,record=record)
        for ref in sorted(refs):
            resolve(root,ref)
            matches=[c for c in claims if c['record']==name and c['reference']==ref]
            if len(matches)!=1:raise ValueError('record-commit-claim-required:'+name+':'+ref)
            rows.append(dict(record=name,reference=ref,commit=validate_claim(root,matches[0])))
    # A modified claims file must not introduce an invalid assertion even when
    # the corresponding prose did not change in the same patch.
    if manifests.intersection(names):
        for claim in claims:validate_claim(root,claim)
    from tools.operational_claims import check as check_operational_claims
    check_operational_claims(root, base)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',default='.')
    parser.add_argument('--base',required=True);args=parser.parse_args()
    print(json.dumps(check(args.root,args.base),indent=2))
