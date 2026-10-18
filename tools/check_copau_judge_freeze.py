"""Fail closed on frozen verifier changes; Git metadata and archive bytes only."""
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

MANIFEST='docs/factory/copau-factory-judge-freeze-2026-10-18.json'
GUARDS=(MANIFEST,'tools/check_copau_judge_freeze.py','tests/test_copau_judge_freeze.py',
        '.github/workflows/copau-factory-judge.yml')


def verify(manifest,read):
    if manifest.get('schema')!='copau-factory-judge-freeze/1':raise ValueError('freeze-schema')
    if not re.fullmatch('[0-9a-f]{40}',manifest.get('source_commit','')):raise ValueError('freeze-source')
    paths={}
    for row in manifest['files']:
        path=row['path'];parts=PurePosixPath(path)
        if parts.is_absolute() or '..' in parts.parts or '\\' in path or ':' in path or path in paths:
            raise ValueError('freeze-path')
        raw=read(path)
        if sha256(raw).hexdigest()!=row['sha256']:raise ValueError('frozen-path-changed:'+path)
        paths[path]=raw
    required=('src/lightyear_data/carddemo/reference_screens.py',
              'factory/carddemo-web/runtime/prove_slice.py','src/lightyear_data/carddemo/screens.py',
              'src/lightyear_data/carddemo/codec.py','factory/copau/judge/mutation-policy.json',
              'factory/copau/judge/service-pom.xml','docs/factory/copau-factory-scope-2026-10-18.json')
    if any(p not in paths for p in required):raise ValueError('freeze-incomplete-inventory')
    members=manifest.get('expected_state_members',[])
    if not members:raise ValueError('freeze-missing-expected-state')
    archives={};seen=set()
    for row in members:
        key=(row['archive'],row['path'])
        if key in seen:raise ValueError('freeze-duplicate-member')
        seen.add(key)
        if row['archive'] not in paths:raise ValueError('freeze-unbound-archive')
        if row['archive'] not in archives:archives[row['archive']]=zipfile.ZipFile(io.BytesIO(paths[row['archive']]))
        if sha256(archives[row['archive']].read(row['path'])).hexdigest()!=row['sha256']:
            raise ValueError('freeze-expected-state-changed')
    return dict(files=len(paths),expected_members=len(members),source_commit=manifest['source_commit'])


def audit(root,base):
    def git(*args):return subprocess.check_output(['git',*args],cwd=root)
    def exists(ref,path):return subprocess.run(['git','cat-file','-e',ref+':'+path],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if not re.fullmatch('[0-9a-f]{40}',base):raise ValueError('freeze-base-identity')
    if exists(base,MANIFEST):
        # A PR cannot rewrite/delete the manifest or weaken its own guard.
        for path in GUARDS:
            if not exists('HEAD',path) or git('show',base+':'+path)!=git('show','HEAD:'+path):
                raise ValueError('freeze-control-changed:'+path)
        raw=git('show',base+':'+MANIFEST)
    else:raw=git('show','HEAD:'+MANIFEST)
    manifest=json.loads(raw)
    source=manifest['source_commit']
    subprocess.check_call(['git','merge-base','--is-ancestor',source,'HEAD'],cwd=root)
    # The bound source commit must actually contain every original frozen blob.
    verify(manifest,lambda p:git('show',source+':'+p))
    result=verify(manifest,lambda p:git('show','HEAD:'+p))
    result.update(manifest_sha256=sha256(raw).hexdigest(),state='frozen',exception_accepted=False)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--base',required=True)
    a=p.parse_args();print(json.dumps(audit(a.root,a.base),indent=2))
