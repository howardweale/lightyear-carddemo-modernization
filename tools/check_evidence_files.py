"""Keep new large files and proof archives out of PR trees."""
import json
import os
from pathlib import Path
import re
import subprocess

LIMIT = 5_000_000
GRANDFATHER_HEAD = '37332f3d9d694387960ca0595acf7fdb2918224a'
GRANDFATHER_ROOT = 'docs/modernization/carddemo-account-evidence-2026-10-19/'


def check(rows, grandfather):
    for row in rows:
        path, size, blob = row['path'], row['bytes'], row['blob']
        if grandfather.get(path) == (blob, size):
            continue
        if size > LIMIT:
            raise ValueError('New or changed file exceeds 5 MB; retain it as a Release asset: ' + path)
        if not path.startswith('docs/milestones/') and (path.lower().endswith('.zip') or path.rsplit('/',1)[-1].lower() == 'mutations.xml'):
            raise ValueError('Proof archives/mutations.xml belong in Release assets: ' + path)
        if (path.startswith('docs/modernization/carddemo-proof-summary-') or
                path.startswith('docs/factory/evidence-retention-') and '-carddemo-run' in path) and size >= 50_000:
            raise ValueError('CardDemo publication metadata must be under 50 KB: ' + path)


def git(*args, input=None):
    return subprocess.check_output(['git', *args], input=input)


def inventory(base, head):
    if not all(re.fullmatch(r'[0-9a-f]{40}', value) for value in (base, head)):
        raise ValueError('Expected exact base and head commits')
    names = git('diff', '--no-renames', '--name-only', '--diff-filter=ACMT', '-z', base+'...'+head, '--').split(b'\0')
    names = [name.decode('utf-8') for name in names if name]
    if not names:return []
    rows = []
    # Read metadata from Git objects, never follow a working-tree symlink.
    for entry in git('ls-tree', '-rlz', head, '--', *names).split(b'\0'):
        if not entry:continue
        meta, name = entry.split(b'\t',1); mode, kind, blob, size = meta.decode().split()
        if kind == 'blob':rows.append(dict(path=name.decode(),blob=blob,bytes=int(size)))
    return rows


def grandfather():
    data=json.loads(Path('tools/ci_evidence_grandfather.json').read_bytes())
    if data['source_commit'] != GRANDFATHER_HEAD:raise ValueError('Grandfather source changed')
    result={}
    for row in data['files']:
        path=row['path']
        if not path.startswith(GRANDFATHER_ROOT) or path in result:raise ValueError('Grandfather path')
        entry=git('ls-tree','-l',GRANDFATHER_HEAD,'--',path).decode().strip()
        meta,actual=entry.split('\t',1);_,kind,blob,size=meta.split()
        if kind!='blob' or actual!=path or blob!=row['blob'] or int(size)!=row['bytes']:
            raise ValueError('Grandfather must match the exact pre-policy published blob')
        result[path]=(blob,int(size))
    return result


def main():
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr=event.get('pull_request')
    if pr is None:
        print('Evidence size policy: no PR diff on this event.');return
    check(inventory(pr['base']['sha'],pr['head']['sha']),grandfather())
    print('New tracked evidence policy passed; unchanged historical files preserved.')


if __name__=='__main__':main()
