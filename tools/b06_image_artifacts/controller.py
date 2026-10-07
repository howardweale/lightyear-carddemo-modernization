"""One Tower-approved image extraction; never a native or model launch.

No Docker command is reachable before exact publication, snapshot, window and
fresh Tower authorization checks. A started output directory is never reused.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from lightyear_calibration.contracts import canonical, digest, read_json, verify
from lightyear_control_tower.status_export import atomic_new
from lightyear_control_tower.verification import verify_decision
from .extract import LIMITS, verify_catalogue

IMAGE = 'sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300'
KIND = 'campaign-authorization'
SCOPE = 'ms94-b06'
EXTRACTOR = 'tools/b06_image_artifacts/extract.py'


def check(value, reason):
    if not value: raise ValueError(reason)


def utc(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    check(dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0, 'utc-required')
    return dt


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_snapshot(root, plan):
    root = Path(root).resolve(); verify(plan)
    m = read_json(root/'snapshot.json'); verify(m)
    check(m['content_sha256'] == plan['snapshot_sha256'], 'snapshot-hash')
    check(m['schema'] == 'b06-image-extraction-snapshot/1' and m['model_calls'] == 0, 'snapshot-kind')
    for name, expected in m['files_sha256'].items():
        p = root/name
        check(not Path(name).is_absolute() and '..' not in Path(name).parts and
              p.resolve().is_relative_to(root) and not any(v.is_symlink() for v in (p,*p.parents)), 'snapshot-path')
        check(sha(p) == expected, 'snapshot-file-changed')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    check(actual == set(m['files_sha256']) | {'snapshot.json'}, 'snapshot-extra-files')
    core = read_json(root/'core.json'); verify(core)
    check(core['content_sha256'] == plan['core_sha256'] and core['image'] == IMAGE and
          core['native_pairs'] == core['model_calls'] == core['target_jvm_executions'] == 0,
          'extraction-only-plan')
    check(core['maximum_extraction_seconds'] == 900 and core['cleanup_reserve_seconds'] == 600 and
          core['container_count'] == 1 and core['retries'] == 0, 'extraction-limits')
    check(core.get('catalogue_schema') == 'b06-image-artifact-catalogue/2' and
          core.get('extraction_limits') == LIMITS, 'catalogue-limits-not-bound')
    check(EXTRACTOR in m['files_sha256'], 'extractor-missing')
    return m, core


def request(plan, commit):
    verify(plan); check(re.fullmatch('[a-f0-9]{40}', commit), 'public-commit')
    artifacts = {
        'campaign': {'id': plan['id'], 'purpose': 'offline-image-artifact-extraction'},
        'plan': plan, 'declaration': {'native_pairs': 0, 'model_calls': 0,
              'target_jvm_executions': 0, 'database_containers': 0, 'network': 'none',
              'only_owned_cleanup': True, 'five_path_census_authorized': False},
        'limits': {'containers': 1, 'extraction_seconds': 900, 'cleanup_reserve_seconds': 600,
                   'window_seconds': 1800, 'retries': 0},
        'public_commit': {'commit': commit}, 'snapshot': {'sha256': plan['snapshot_sha256']},
        'window': plan['window']}
    bound = {k: hashlib.sha256(canonical(v)).hexdigest() for k,v in artifacts.items()}
    evidence = {k: 'evidence/b06/image-artifacts/'+v+'.json' for k,v in bound.items()}
    value = {'schema': 'tower-request/1', 'scope': SCOPE, 'kind': KIND,
             'bound': bound, 'evidence': evidence, 'proposed_by': 'b06-image-artifact-preparation',
             'workload': plan['id'],
             'summary': 'One offline pinned-image artifact extraction, NOT a smoke run. '
                        'No databases, target JVM, native pairs, network or models. '
                        'One owned container; 15 minutes extraction plus 10 minutes cleanup reserve. '
                        'Window '+plan['window']['not_before_utc']+' to '+plan['window']['deadline_utc']+
                        '; latest start '+plan['window']['latest_start_utc']+'. '
                        'No retry. Five-path census requires another decision. Operator review; not independent attestation.'}
    value['id'] = 'b06-image-'+digest(value)
    return value, {**bound, 'request': digest(value)}, artifacts


def write_request(repository, plan, commit):
    value, bound, artifacts = request(plan, commit)
    for name, artifact in artifacts.items():
        p = Path(repository)/value['evidence'][name]
        if p.exists(): check(p.read_bytes() == canonical(artifact), 'review-evidence-changed')
        else: atomic_new(p, artifact)
    p = Path(repository)/'work/control-tower/requests'/SCOPE/(value['id']+'.json')
    if p.exists(): check(p.read_bytes() == canonical(value), 'review-request-changed')
    else: atomic_new(p, value)
    return value['id'], bound


def authorize(plan, commit, reader, now, campaign_public):
    check(reader is not None and reader.key != campaign_public and
          hashlib.sha256(reader.key).hexdigest() == plan['tower_public_key_sha256'], 'tower-key')
    _, bound, _ = request(plan, commit)
    proof = reader.get(KIND, bound, now)
    check(proof is not None, 'tower-decision-required')
    journal = proof['journal']
    check(abs((now-utc(journal['exported_at'])).total_seconds()) < 60, 'tower-history-stale')
    verify_decision(proof, reader.key, KIND, bound, scope=SCOPE, outcomes={'authorized'},
                    expected_head=journal['journal_head_sha256'], now=now)
    return proof


def publication(repository, root, plan, commit, ref):
    repository, root = Path(repository), Path(root)
    def git(*args):
        return subprocess.check_output(['git','-C',str(repository),*args], stderr=subprocess.PIPE, timeout=60)
    check(ref == plan.get('public_ref') and re.fullmatch(r'refs/heads/codex/[a-z0-9][a-z0-9-]*', ref), 'publication-ref')
    check(git('remote','get-url','origin').decode().strip() ==
          'https://github.com/howardweale/lightyear-carddemo-modernization.git', 'publication-repository')
    refs = git('ls-remote','origin',ref).decode().split()
    check(refs == [commit,ref], 'public-commit-not-present')
    manifest, _ = verify_snapshot(root, plan)
    for local, public in plan['public_files'].items():
        check(git('cat-file','blob',commit+':'+public) == (root/local).read_bytes(), 'public-bytes-differ')
    check(set(plan['public_files']) == set(manifest['files_sha256']) | {'snapshot.json'}, 'public-file-closure')
    check(git('cat-file','blob',commit+':'+plan['public_plan_path']) == canonical(plan), 'public-plan-differs')


def execute(root, plan, output, commit, reader, signer, *, public_verified=False, clock=None, docker=None):
    """Dependency injection supports offline guard tests; CLI supplies real checks."""
    root, output = Path(root).resolve(), Path(output).resolve()
    manifest, core = verify_snapshot(root, plan)
    check(public_verified, 'verified-publication-required')
    now = clock or (lambda: datetime.now(timezone.utc))
    w = plan['window']; a,b,latest = map(utc,(w['not_before_utc'],w['deadline_utc'],w['latest_start_utc']))
    check((b-a).total_seconds() == 1800 and (b-latest).total_seconds() == 1500 and a <= now() <= latest,
          'outside-or-late-extraction-window')
    check(not output.exists() and not output.is_relative_to(root), 'output-reuse-or-frozen-output')
    proof = authorize(plan, commit, reader, now(), signer.public)
    check(shutil.disk_usage(output.parent).free >= 16*1024**3, 'insufficient-output-space')
    output.mkdir(exist_ok=False)
    atomic_new(output/'tower-authorization.json', proof)
    def signed(name, value): atomic_new(output/name, signer.sign(value))
    signed('started.json', {'schema':'b06-image-extraction-start/1', 'plan_sha256':plan['content_sha256'],
           'snapshot_sha256':plan['snapshot_sha256'],'decision_sha256':proof['decision_sha256'],
           'public_commit':commit,'real_utc':now().isoformat(),'model_calls':0,'native_pairs':0})
    started = time.monotonic(); commands = []
    def command(*args, timeout=60, allow_failure=False):
        check(now() < b, 'extraction-hard-deadline')
        timeout = min(timeout, max(1,(b-now()).total_seconds()))
        commands.append(list(args))
        if docker is None:
            result = subprocess.run(['docker',*map(str,args)], capture_output=True, timeout=timeout)
        else: result = docker(*args, timeout=timeout)
        if not allow_failure: check(result.returncode == 0, 'docker-command-failed-'+args[0])
        return result
    name = plan['id']; label = 'lightyear.b06.artifacts='+name
    check(re.fullmatch('b06-image-[a-z0-9-]+',name), 'owned-resource-name')
    created = False; failure = None; cleaned = False; catalogue_hash = None
    try:
        check(not command('ps','-q').stdout.strip(), 'active-container-overlap')
        check(not command('ps','-a','-q','--filter','name=^/'+name+'$').stdout.strip(), 'owned-name-already-exists')
        image = json.loads(command('image','inspect',IMAGE).stdout)[0]
        check(image['Id'] == IMAGE, 'image-identity')
        check(not image.get('Config', {}).get('Volumes'), 'image-anonymous-volumes-forbidden')
        source = root/EXTRACTOR
        check(sha(source) == manifest['files_sha256'][EXTRACTOR], 'extractor-changed')
        # Set before create: preserve and clean a partially successful Docker create.
        created = True
        command('create','--name',name,'--label',label,'--network','none','--read-only',
                '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64',
                '--memory','2g','--cpus','1','--env','PYTHONDONTWRITEBYTECODE=1',
                '--mount','type=bind,src='+str(source)+',dst=/extract.py,readonly',
                '--mount','type=bind,src='+str(output)+',dst=/evidence',
                '--entrypoint','python3',IMAGE,'-B','/extract.py')
        inspect = json.loads(command('container','inspect',name).stdout)[0]
        check(inspect['Image'] == IMAGE and inspect['Config']['Labels'].get('lightyear.b06.artifacts') == name,
              'created-container-ownership')
        check(inspect['HostConfig']['NetworkMode'] == 'none' and inspect['HostConfig']['ReadonlyRootfs'] is True and
              len(inspect['Mounts']) == 2 and not inspect['HostConfig'].get('PortBindings'), 'container-isolation')
        atomic_new(output/'container-inspection.json', inspect)
        remaining = (b-now()).total_seconds()-600
        check(remaining >= 900, 'cleanup-reserve-lost-before-start')
        result = command('start','--attach',name, timeout=900, allow_failure=True)
        (output/'extract.stdout').write_bytes(result.stdout); (output/'extract.stderr').write_bytes(result.stderr)
        state = json.loads(command('container','inspect',name).stdout)[0]['State']
        check(result.returncode == 0 and not state['Running'] and state['ExitCode'] == 0, 'extractor-failed')
        path = output/'catalogue/catalogue.json'; catalogue = read_json(path)
        check(catalogue['schema'] == 'b06-image-artifact-catalogue/2' and catalogue['model_calls'] ==
              catalogue['native_pairs'] == catalogue['target_jvm_executions'] == 0, 'catalogue-kind')
        replay = verify_catalogue(output/'catalogue', catalogue)
        atomic_new(output/'catalogue-replay.json', replay)
        catalogue_hash = sha(path)
    except BaseException as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            (output/'timeout.stdout').write_bytes(exc.stdout or b'')
            (output/'timeout.stderr').write_bytes(exc.stderr or b'')
        failure = type(exc).__name__+': '+str(exc)
        print('B06 artifact extraction failed; preserve output; no retry.', flush=True)
    finally:
        if created:
            try:
                ids = command('ps','-a','-q','--filter','label='+label).stdout.decode().split()
                check(len(ids) <= 1, 'ambiguous-owned-resource')
                for identity in ids:
                    info = json.loads(command('container','inspect',identity).stdout)[0]
                    check(info['Name'] == '/'+name and info['Image'] == IMAGE and
                          info['Config']['Labels'].get('lightyear.b06.artifacts') == name, 'cleanup-ownership')
                    command('rm','--force',info['Id'],timeout=90)
                check(not command('ps','-a','-q','--filter','label='+label).stdout.strip() and
                      not command('ps','-a','-q','--filter','name=^/'+name+'$').stdout.strip(), 'cleanup-not-absent')
                cleaned = True
            except BaseException as exc:
                failure = (failure or '')+'; cleanup: '+type(exc).__name__+': '+str(exc)
        else: cleaned = True
        unchanged = False
        try:
            verify_snapshot(root, plan)
            unchanged = True
        except BaseException as exc:
            failure = (failure or '')+'; snapshot: '+type(exc).__name__+': '+str(exc)
        atomic_new(output/'docker-commands.json',commands)
        signed('report.json', {'schema':'b06-image-extraction-report/1','passed':failure is None and cleaned,
               'failure':failure,'plan_sha256':plan['content_sha256'],'snapshot_sha256':plan['snapshot_sha256'],
               'catalogue_sha256':catalogue_hash,'image':IMAGE,'owned_cleanup_verified':cleaned,
               'frozen_hashes_unchanged':unchanged,
               'elapsed_seconds':round(time.monotonic()-started,3),'finished_real_utc':now().isoformat(),
               'model_calls':0,'native_pairs':0,'target_jvm_executions':0,'five_path_census_authorized':False,
               'review':'operator review; not independent attestation'})
    check(failure is None and cleaned, 'extraction-failed-preserved')


def main():
    p = argparse.ArgumentParser()
    for name in ('root','plan','repository','output','public-commit','authority','tower-key','credential'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--ref',default='refs/heads/codex/b06-observer-v2-preparation')
    p.add_argument('--tower-url',default='http://127.0.0.1:8766')
    args = p.parse_args(); root = Path(args.root).resolve()
    check(Path.cwd().resolve() == root and Path(__file__).resolve().is_relative_to(root), 'frozen-cwd-imports-required')
    plan = read_json(Path(args.plan)); verify_snapshot(root, plan)
    publication(args.repository,root,plan,args.public_commit,args.ref)
    from tools.ms94_b06_qualification_worker import existing_signer
    from lightyear_control_tower.b06 import DecisionReader
    from lightyear_control_tower.client import ConsoleClient
    signer = existing_signer(Path(args.authority))
    reader = DecisionReader(ConsoleClient(args.tower_url), Path(args.credential).read_text(encoding='utf-8-sig').strip(),
                            Path(args.tower_key).read_bytes())
    execute(root,plan,args.output,args.public_commit,reader,signer,public_verified=True)


if __name__ == '__main__': main()
