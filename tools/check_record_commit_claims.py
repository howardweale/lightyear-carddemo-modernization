"""Verify newly quoted commit references against explicit, machine-checkable claims.

Only changed lines in current/new records are checked. Preserved records dated
before the policy start stay untouched. Git metadata and blobs are read only.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

START = '2026-10-17'
CLAIMS = 'docs/factory/commit-claims-2026-10-17.json'
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
    if role=='source':
        path=claim['source_path']
        if path.startswith('/') or '..' in path.split('/') or ':' in path:raise ValueError('record-source-path')
        mode=git(root,'ls-tree',commit,'--',path).decode()
        if not mode.startswith(('100644 blob ','100755 blob ')):raise ValueError('record-source-regular-blob')
        if sha256(git(root,'show',commit+':'+path)).hexdigest()!=claim['source_sha256']:
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


def references(lines):
    return {m[1] for line in lines for m in REF.finditer(line) if re.search('[a-f]',m[1])}


def check(root,base):
    root=Path(root)
    names=git(root,'diff','--name-only','--diff-filter=ACMR',base,'HEAD','--','docs/factory','docs/milestones').decode().splitlines()
    manifests={p.as_posix():json.loads((root/p).read_bytes())['claims']
               for p in sorted(path.relative_to(root) for path in (root/'docs/factory').glob('commit-claims-*.json'))
               if re.fullmatch(r'commit-claims-(?:[a-z0-9]+-)*20\d\d-\d\d-\d\d\.json',p.name)}
    claims=[claim for rows in manifests.values() for claim in rows]
    rows=[]
    for name in names:
        if name in manifests:continue
        dates=re.findall(r'20\d\d-\d\d-\d\d',Path(name).name)
        if dates and max(dates)<START:continue
        patch=git(root,'diff','--unified=0',base,'HEAD','--',name).decode('utf-8')
        refs=references(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
        for ref in sorted(refs):
            resolve(root,ref)
            matches=[c for c in claims if c['record']==name and c['reference']==ref]
            if len(matches)!=1:raise ValueError('record-commit-claim-required:'+name+':'+ref)
            rows.append(dict(record=name,reference=ref,commit=validate_claim(root,matches[0])))
    # A modified claims file must not introduce an invalid assertion even when
    # the corresponding prose did not change in the same patch.
    for name in names:
        if name in manifests:
            for claim in manifests[name]:validate_claim(root,claim)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',default='.')
    parser.add_argument('--base',required=True);args=parser.parse_args()
    print(json.dumps(check(args.root,args.base),indent=2))
