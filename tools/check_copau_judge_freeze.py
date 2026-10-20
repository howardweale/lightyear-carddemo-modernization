"""Fail closed on frozen verifier changes; Git metadata and archive bytes only."""
import argparse
from hashlib import sha256
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

MANIFEST='docs/factory/copau-factory-judge-freeze-2026-10-18.json'
GUARDS=(MANIFEST,'tools/check_copau_judge_freeze.py','tests/test_copau_judge_freeze.py',
        '.github/workflows/copau-factory-judge.yml', '.github/CODEOWNERS')
AMENDMENT='docs/factory/copau-factory-judge-freeze-amendment-2026-10-20.json'
L2_SOURCE='b6fe569169588f42027a2854a268dbd400f11c60'
L2_PATH='src/lightyear_data/carddemo/update_edits.py'
EXTRA_REQUIRED=('factory/carddemo-web/runtime/receipt.py', '.github/workflows/carddemo-web.yml',
                'factory/carddemo-web/service/pom.xml')
JAVA_TEST_ROOT='factory/carddemo-web/service/src/test/'


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


def amended_manifest(manifest, amendment, read_source, java_tests):
    """Apply only the reviewed L2 exception and exact additional source bindings."""
    if amendment.get('schema') != 'copau-factory-judge-amendment/1':
        raise ValueError('freeze-amendment-schema')
    source = amendment.get('main_source', '')
    if not re.fullmatch('[0-9a-f]{40}', source):
        raise ValueError('freeze-amendment-source')
    effective = json.loads(json.dumps(manifest))
    by_path = {row['path']: row for row in effective['files']}
    change = amendment.get('existing_authorized_change', {})
    if change.get('path') != L2_PATH or change.get('source_commit') != L2_SOURCE:
        raise ValueError('freeze-amendment-exception-scope')
    if L2_PATH not in by_path or change.get('old_sha256') != by_path[L2_PATH]['sha256']:
        raise ValueError('freeze-amendment-old-binding')
    digest = sha256(read_source(L2_SOURCE, L2_PATH)).hexdigest()
    if change.get('sha256') != digest or sha256(read_source(source, L2_PATH)).hexdigest() != digest:
        raise ValueError('freeze-amendment-L2-binding')
    by_path[L2_PATH]['sha256'] = digest
    rows = amendment.get('files', [])
    paths = [row['path'] for row in rows]
    if not java_tests or len(paths) != len(set(paths)) or set(paths) != set(EXTRA_REQUIRED) | set(java_tests):
        raise ValueError('freeze-amendment-inventory')
    for row in rows:
        path = row['path']
        digest = sha256(read_source(source, path)).hexdigest()
        if row.get('sha256') != digest:
            raise ValueError('freeze-amendment-source-binding:' + path)
        if path in by_path:
            if by_path[path]['sha256'] != digest:
                raise ValueError('freeze-amendment-unapproved-rebind:' + path)
        else:
            effective['files'].append(dict(path=path, sha256=digest))
    return effective


def audit(root,base,*,bootstrap_reviewed_main=False):
    def git(*args):return subprocess.check_output(['git',*args],cwd=root)
    def exists(ref,path):return subprocess.run(['git','cat-file','-e',ref+':'+path],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if not re.fullmatch('[0-9a-f]{40}',base):raise ValueError('freeze-base-identity')
    has_baseline = exists(base,MANIFEST)
    if bootstrap_reviewed_main:
        if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'push'
                or os.environ.get('GITHUB_REF') != 'refs/heads/main'
                or os.environ.get('GITHUB_SHA') != git('rev-parse','HEAD').decode().strip()):
            raise ValueError('freeze-bootstrap-main-only')
    if not has_baseline and not bootstrap_reviewed_main:
        raise ValueError('freeze-trusted-baseline-missing')
    if has_baseline:
        # A PR cannot rewrite/delete the manifest or weaken its own guard.
        controls = GUARDS + ((AMENDMENT,) if exists(base,AMENDMENT) else ())
        for path in controls:
            if not exists('HEAD',path) or git('show',base+':'+path)!=git('show','HEAD:'+path):
                raise ValueError('freeze-control-changed:'+path)
        raw=git('show',base+':'+MANIFEST)
    else:raw=git('show','HEAD:'+MANIFEST)
    manifest=json.loads(raw)
    source=manifest['source_commit']
    subprocess.check_call(['git','merge-base','--is-ancestor',source,'HEAD'],cwd=root)
    # The bound source commit must actually contain every original frozen blob.
    verify(manifest,lambda p:git('show',source+':'+p))
    effective = manifest
    amendment_ref = base if exists(base,AMENDMENT) else 'HEAD' if not has_baseline else None
    if amendment_ref is None and exists('HEAD',AMENDMENT):
        raise ValueError('freeze-amendment-untrusted')
    if amendment_ref is not None:
        amendment = json.loads(git('show',amendment_ref+':'+AMENDMENT))
        if amendment.get('original_manifest_sha256') != sha256(raw).hexdigest():
            raise ValueError('freeze-amendment-original-seal')
        origin = amendment['main_source']
        for ancestor in (origin, L2_SOURCE):
            subprocess.check_call(['git','merge-base','--is-ancestor',ancestor,base],cwd=root)
        def tests(ref):
            return {p for p in git('ls-tree','-r','--name-only',ref,'--',JAVA_TEST_ROOT).decode().splitlines() if p.endswith('.java')}
        java_tests = tests(origin)
        if tests('HEAD') != java_tests:
            raise ValueError('freeze-amendment-test-inventory-changed')
        effective = amended_manifest(manifest,amendment,lambda ref,p:git('show',ref+':'+p),java_tests)
    result=verify(effective,lambda p:git('show','HEAD:'+p))
    if amendment_ref is not None:
        result.update(amendment_sha256=sha256(git('show',amendment_ref+':'+AMENDMENT)).hexdigest(),
                      amendment_source=amendment['main_source'],recorded_L2_exception=L2_SOURCE)
    result.update(manifest_sha256=sha256(raw).hexdigest(),state='frozen',new_unfreeze_exception_accepted=False)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--base',required=True)
    p.add_argument('--bootstrap-reviewed-main',action='store_true')
    a=p.parse_args();print(json.dumps(audit(a.root,a.base,bootstrap_reviewed_main=a.bootstrap_reviewed_main),indent=2))
