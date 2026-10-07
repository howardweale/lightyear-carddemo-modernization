"""Freeze public Git bytes for an extraction proposal. Never executes Docker."""
import argparse
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
    selected = {n for n in names if n.startswith('src/') and n.endswith('.py')}
    selected.update(n for n in names if n.startswith('tools/b06_image_artifacts/') and n.endswith('.py'))
    selected.update(n for n in ('tools/__init__.py','tests/__init__.py') if n in names)
    selected.update(('tests/test_b06_image_artifacts.py',
                     'tools/ms94_b06_qualification_worker.py','tools/ms94_b06_admission.py'))
    check(selected <= set(names), 'source-closure-missing')
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
