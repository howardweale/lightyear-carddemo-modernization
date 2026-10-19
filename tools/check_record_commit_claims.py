"""Verify newly quoted commit references against explicit, machine-checkable claims.

Only added lines are checked; a filename date cannot exempt a new claim.
Unchanged historical bytes stay untouched. Git metadata and blobs are read only.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

CLAIMS = 'docs/factory/commit-claims-2026-10-17.json'
ROLE_CORRECTIONS = 'docs/factory/commit-claim-role-corrections-2026-10-18.json'
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


def current_claims(root):
    """Apply only hash-bound source-to-publication role corrections.

    The historical registry stays byte-identical. A correction cannot change
    the referenced commit, record, path or blob hash or create a new claim.
    """
    root=Path(root);path=root/CLAIMS
    claims=json.loads(path.read_bytes())['claims'] if path.is_file() else []
    correction=root/ROLE_CORRECTIONS
    if not correction.exists():return claims
    data=json.loads(correction.read_bytes())
    if data.get('schema')!='record-commit-role-corrections/1' or data.get('prepared_on')!='2026-10-18':
        raise ValueError('record-role-correction-schema')
    seen=set()
    for row in data['corrections']:
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


def check(root,base):
    root=Path(root)
    names=git(root,'diff','--name-only','--diff-filter=ACMR',base,'HEAD','--','docs/factory','docs/milestones').decode().splitlines()
    claims=current_claims(root)
    rows=[]
    for name in names:
        if name in (CLAIMS,ROLE_CORRECTIONS):continue
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
    if CLAIMS in names or ROLE_CORRECTIONS in names:
        for claim in claims:validate_claim(root,claim)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',default='.')
    parser.add_argument('--base',required=True);args=parser.parse_args()
    print(json.dumps(check(args.root,args.base),indent=2))
