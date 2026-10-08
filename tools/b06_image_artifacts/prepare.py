"""Freeze public Git bytes for an extraction proposal. Never executes Docker."""
import argparse
import ast
import importlib.util
from datetime import timedelta
import hashlib
from pathlib import Path
import subprocess

from lightyear_calibration.contracts import canonical, seal
from .controller import IMAGE, ENTRYPOINT, check, utc, verify_snapshot
from .extract import LIMITS


def prepare(repository, commit, snapshot, public, start, tower_key,
            public_ref='refs/heads/codex/b06-image-inventory-r1'):
    repository, snapshot, public = map(Path, (repository, snapshot, public))
    check(not snapshot.exists() and not public.exists(), 'freeze-output-already-exists')
    def git(*args):
        return subprocess.check_output(['git','-C',str(repository),*args], timeout=60)
    check(git('rev-parse',commit).decode().strip() == commit, 'full-source-commit-required')
    names = git('ls-tree','-r','--name-only',commit).decode().splitlines()
    selected = {n for n in names if n.startswith('tools/b06_image_artifacts/') and n.endswith('.py')}
    selected.update(('tests/test_b06_image_artifacts.py',
                     'tools/ms94_b06_qualification_worker.py','tools/ms94_b06_admission.py'))
    # Static repository import closure, including relative imports and package
    # initializers. External distributions are environment bindings, not src/.
    files=set(names);seen=set();queue=list(selected)
    def include(module):
        path=module.replace('.','/')
        for prefix in ('','src/'):
            for candidate in (prefix+path+'.py',prefix+path+'/__init__.py'):
                if candidate in files and candidate not in selected:
                    selected.add(candidate);queue.append(candidate)
        parts=module.split('.')
        for count in range(1,len(parts)):
            for prefix in ('','src/'):
                candidate=prefix+'/'.join(parts[:count])+'/__init__.py'
                if candidate in files and candidate not in selected:
                    selected.add(candidate);queue.append(candidate)
    while queue:
        name=queue.pop()
        if name in seen:continue
        check(name in files,'source-closure-missing');seen.add(name)
        module=name.removeprefix('src/').removesuffix('.py').replace('/','.')
        package=module.removesuffix('.__init__') if module.endswith('.__init__') else module.rpartition('.')[0]
        tree=ast.parse(git('cat-file','blob',commit+':'+name))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for alias in node.names:include(alias.name)
            elif isinstance(node,ast.ImportFrom):
                target=importlib.util.resolve_name('.'*node.level+(node.module or ''),package) if node.level else node.module
                if target:
                    include(target)
                    for alias in node.names:
                        if alias.name!='*':include(target+'.'+alias.name)
    check(selected <= files,'source-closure-missing')
    snapshot.mkdir(parents=True, exist_ok=False); public.mkdir(parents=True, exist_ok=False)
    hashes = {}; mapping = {}
    for name in sorted(selected):
        raw = git('cat-file','blob',commit+':'+name)
        path = snapshot/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest(); mapping[name] = name
    core = seal({'schema':'b06-image-extraction-core/1','source_commit':commit,'image':IMAGE,
        'native_pairs':0,'model_calls':0,'target_jvm_executions':0,'database_containers':0,
        'network':'none','container_count':1,'retries':0,'maximum_extraction_seconds':900,
        'operation':'inventory-only','catalogue_schema':'b06-image-inventory/1','class_bytes_copied':0,
        'cleanup_reserve_seconds':600,'entrypoint':ENTRYPOINT,
        'artifact_roots':['/application','/root/.m2'],'jdk':'resolved image java executable parent',
        'purpose':'Inventory paths, sizes, entry counts and hashes; no class copies or runtime admission.',
        'raw_artifacts_public':False,'five_path_census_authorized':False})
    raw=canonical(core); (snapshot/'core.json').write_bytes(raw); (public/'core.json').write_bytes(raw)
    hashes['core.json']=hashlib.sha256(raw).hexdigest()
    manifest=seal({'schema':'b06-image-extraction-snapshot/1','model_calls':0,'files_sha256':hashes})
    raw=canonical(manifest); (snapshot/'snapshot.json').write_bytes(raw); (public/'snapshot.json').write_bytes(raw)
    prefix=public.resolve().relative_to(repository.resolve()).as_posix()
    mapping.update({'core.json':prefix+'/core.json','snapshot.json':prefix+'/snapshot.json'})
    at=utc(start)
    plan=seal({'schema':'b06-image-extraction-plan/1','id':'b06-image-inventory-r1',
        'public_ref':public_ref,
        'core_sha256':core['content_sha256'],'snapshot_sha256':manifest['content_sha256'],
        'public_plan_path':prefix+'/plan.json','public_files':mapping,
        'tower_public_key_sha256':hashlib.sha256(Path(tower_key).read_bytes()).hexdigest(),
        'window':{'not_before_utc':at.isoformat(),'latest_start_utc':(at+timedelta(minutes=5)).isoformat(),
                  'deadline_utc':(at+timedelta(minutes=30)).isoformat()},
        'review':'operator review; not independent attestation',
        'run_authorized':False,'requires_exact_tower_decision':True})
    (public/'plan.json').write_bytes(canonical(plan)); verify_snapshot(snapshot, plan)
    return plan


def main():
    p=argparse.ArgumentParser()
    for n in ('repository','commit','snapshot','public','start','tower-key'): p.add_argument('--'+n, required=True)
    p.add_argument('--public-ref',default='refs/heads/codex/b06-image-inventory-r1')
    a=p.parse_args()
    v=prepare(a.repository,a.commit,a.snapshot,a.public,a.start,a.tower_key,public_ref=a.public_ref)
    print('plan='+v['content_sha256']+' snapshot='+v['snapshot_sha256'])


if __name__=='__main__': main()
