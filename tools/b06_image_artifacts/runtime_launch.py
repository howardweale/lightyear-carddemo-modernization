"""Fresh, separately Tower-authorized runtime-closure producer. Never auto-run.

Unlike inventory-only authority this explicitly starts a no-database test JVM,
compiles its pinned probes and extracts the pinned runtime image with jimage.
"""
import hashlib,json,re,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
from lightyear_calibration.contracts import verify,canonical,digest
from lightyear_control_tower.status_export import atomic_new
from lightyear_control_tower.verification import verify_decision
from .controller import IMAGE,check,utc
from .runtime_producer import produce

REQUIRED={'runtime_closure.py','runtime_launch.py','runtime_producer.py','runtime_worker.py','runtime_inventory.py','resolved_runtime.py','tycho_runtime.py','transient_sources.py','application_identity.py','runtime_capture.py','bundle_content.py','archive.py',
          'B06RuntimeCatalogAgent.java','B06RuntimeCatalogTest.java','RuntimeClosureAgent.java','ms94_b06_observed_worker.py'}

def validate(root,plan):
    verify(plan);root=Path(root).resolve()
    check(plan['schema'] in ('b06-runtime-closure-plan/1','b06-runtime-closure-plan/2') and plan['image']==IMAGE,'runtime-plan-required')
    check(plan['model_calls']==plan['native_pairs']==plan['database_containers']==0,'runtime-only-scope')
    check(plan['retries']==0 and plan['network']=='none','runtime-isolation')
    check(0<plan['maximum_runtime_seconds']<=3000 and plan['cleanup_reserve_seconds']==600,'runtime-limits')
    files=plan['files_sha256'];check(REQUIRED<=set(files),'runtime-source-closure')
    check(all(isinstance(n,str) and not Path(n).is_absolute() and '..' not in Path(n).parts for n in files),'runtime-source-path')
    check(all(re.fullmatch('[a-f0-9]{64}',v) for v in files.values()),'runtime-source-hash')
    for name,expected in files.items():
        p=root/name;check(not p.is_symlink() and p.resolve().is_relative_to(root),'runtime-snapshot-path')
        check(hashlib.sha256(p.read_bytes()).hexdigest()==expected,'runtime-snapshot-changed')
    check(digest(files)==plan['snapshot_sha256'],'runtime-snapshot-binding')
    check({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}==set(files),'runtime-snapshot-extra-files')
    check(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==files['runtime_launch.py'],'runtime-host-launcher-changed')
    from . import runtime_producer
    check(hashlib.sha256(Path(runtime_producer.__file__).read_bytes()).hexdigest()==files['runtime_producer.py'],'runtime-host-producer-changed')
    from tools.ms94_b06_observed_worker import maven_arguments
    check(plan.get('measured_maven_arguments')==maven_arguments(),'runtime-measured-launch-binding')
    check(hashlib.sha256(Path(__file__).parents[1].joinpath('ms94_b06_observed_worker.py').read_bytes()).hexdigest()==files['ms94_b06_observed_worker.py'],'runtime-measured-worker-binding')
    return root

def request(plan,commit,*,window=None,practice=None):
    frozen=plan.get('schema')=='b06-runtime-closure-plan/2'
    if frozen:
        check(isinstance(practice,dict) and practice.get('passed') is True and all(practice.get('checks',{}).get(k) is True for k in ('census','source_only','application_content','tycho','warning_baseline','frozen_bytes','cleanup')),'frozen-practice-six-checks-required-before-Tower-request')
        check(all(practice.get(k)==plan.get(k) for k in ('source_commit','snapshot_sha256')) and practice.get('plan_sha256')==plan['content_sha256'],'frozen-practice-plan-binding')
        check(isinstance(window,dict) and set(window)=={'not_before_utc','latest_start_utc','deadline_utc'},'authorization-window-required')
        check(utc(window['not_before_utc'])<=utc(window['latest_start_utc']) and (utc(window['deadline_utc'])-utc(window['latest_start_utc'])).total_seconds()>=plan['maximum_runtime_seconds']+plan['cleanup_reserve_seconds'],'authorization-window-reserve')
    else:window=plan['window']
    verify(plan);check(re.fullmatch('[a-f0-9]{40}',commit),'full-public-commit')
    artifacts=dict(campaign=plan['id'],plan=plan,declaration=dict(runtime_only=True,models=0,native_pairs=0),
        limits=dict(seconds=plan['maximum_runtime_seconds'],cleanup=600,retries=0),snapshot=plan['snapshot_sha256'],
        window=window,public_commit=commit)
    if frozen:artifacts['practice']=practice
    bindings={k:digest(v) for k,v in artifacts.items()}
    value=dict(schema='tower-request/1',scope='ms94-b06',kind='campaign-authorization',bound=bindings,
        evidence={k:'evidence/b06/runtime-closure/'+v+'.json' for k,v in bindings.items()},
        proposed_by='b06-runtime-closure-preparation',workload=plan['id'],
        summary='One network-free runtime-closure container; offline probe compilation, no-database Tycho/Equinox test JVM and jimage extraction. '
          'No native pairs, models or databases; no retry. 2700 seconds runtime plus 600 seconds cleanup reserve. '
          'Window '+window['not_before_utc']+' to '+window['deadline_utc']+'. '
          'Latest start '+window['latest_start_utc']+'. Five-path census is not authorized. Operator review; not independent attestation.')
    value['id']='b06-runtime-'+digest(value)
    return value,{**bindings,'request':digest(value)},artifacts


def bound(plan,commit,**kwargs):
    return request(plan,commit,**kwargs)[1]


def write_request(repository,plan,commit):
    value,bindings,artifacts=request(plan,commit)
    for name,artifact in artifacts.items():
        p=Path(repository)/value['evidence'][name]
        if p.exists():check(p.read_bytes()==canonical(artifact),'runtime-review-evidence-changed')
        else:atomic_new(p,artifact)
    p=Path(repository)/'work/control-tower/requests/ms94-b06'/(value['id']+'.json')
    if p.exists():check(p.read_bytes()==canonical(value),'runtime-request-changed')
    else:atomic_new(p,value)
    return value['id'],bindings


def publication(repository,root,plan,commit):
    def git(*args):return subprocess.check_output(['git','-C',str(repository),*args],timeout=60)
    check(re.fullmatch('[a-f0-9]{40}',commit),'full-public-commit')
    ref=plan['public_ref'];check(re.fullmatch('refs/heads/codex/[a-z0-9-]+',ref),'runtime-public-ref')
    check(git('remote','get-url','origin').decode().strip()=='https://github.com/howardweale/lightyear-carddemo-modernization.git','runtime-repository')
    check(git('ls-remote','origin',ref).decode().split()==[commit,ref],'runtime-public-commit')
    check(set(plan['public_files'])==set(plan['files_sha256']),'runtime-public-closure')
    for local,remote in plan['public_files'].items():check(git('cat-file','blob',commit+':'+remote)==(root/local).read_bytes(),'runtime-public-bytes')
    check(git('cat-file','blob',commit+':'+plan['public_plan_path'])==canonical(plan),'runtime-public-plan')

def execute(repository,root,plan,output,commit,reader,signer,*,practice_directory=None,authorization_window=None):
    root=validate(root,plan);output=Path(output).resolve();publication(repository,root,plan,commit)
    kwargs={}
    if plan['schema']=='b06-runtime-closure-plan/2':
        from .frozen_runtime import verify_practice
        kwargs=dict(window=authorization_window,practice=verify_practice(root,plan,practice_directory))
    now=datetime.now(timezone.utc);w=authorization_window if kwargs else plan['window'];deadline=utc(w['deadline_utc'])
    check(utc(w['not_before_utc'])<=now<=utc(w['latest_start_utc']) and (deadline-now).total_seconds()>=plan['maximum_runtime_seconds']+600,'runtime-window')
    check(hashlib.sha256(reader.key).hexdigest()==plan['tower_public_key_sha256'] and reader.key!=signer.public,'runtime-distinct-tower-authority')
    bindings=bound(plan,commit,**kwargs);proof=reader.get('campaign-authorization',bindings,now)
    check(proof is not None and abs((now-utc(proof['journal']['exported_at'])).total_seconds())<60,'runtime-fresh-tower-decision')
    verify_decision(proof,reader.key,'campaign-authorization',bindings,scope='ms94-b06',outcomes={'authorized'},expected_head=proof['journal']['journal_head_sha256'],now=now)
    check(not output.exists() and not output.is_relative_to(root),'runtime-fresh-output')
    output.mkdir();atomic_new(output/'tower-authorization.json',proof)
    name=plan['id'];check(re.fullmatch('b06-runtime-[a-z0-9-]+',name),'runtime-owned-name');label='lightyear.b06.runtime='+name
    commands=[];started=time.monotonic();created=False;failure=None;cleaned=False;resolution=None; pending=None
    def docker(*args,timeout=60,allow_failure=False):
        remaining=(deadline-datetime.now(timezone.utc)).total_seconds();check(remaining>0,'runtime-hard-deadline')
        commands.append(list(args));r=subprocess.run(['docker',*map(str,args)],capture_output=True,timeout=min(timeout,remaining))
        if not allow_failure:check(r.returncode==0,'runtime-docker-'+args[0])
        return r
    atomic_new(output/'started.json',signer.sign(dict(schema='b06-runtime-start/1',plan_sha256=plan['content_sha256'],snapshot_sha256=plan['snapshot_sha256'],decision_sha256=proof['decision_sha256'],model_calls=0)))
    try:
        check(not docker('ps','-q').stdout.strip(),'runtime-active-container-overlap')
        check(not docker('ps','-a','-q','--filter','name=^/'+name+'$').stdout.strip(),'runtime-owned-name-exists')
        image=json.loads(docker('image','inspect',IMAGE).stdout)[0]
        check(image['Id']==IMAGE and not image.get('Config',{}).get('Volumes'),'runtime-image')
        results=output/'results';results.mkdir()
        created=True
        docker('create','--name',name,'--label',label,'--network','none','--cap-drop','ALL','--security-opt','no-new-privileges',
          '--memory','8g','--cpus','2','--pids-limit','256','--mount','type=bind,src='+str(root)+',dst=/source,readonly',
          '--mount','type=bind,src='+str(results)+',dst=/results','--entrypoint','python3',IMAGE,'-B','/source/runtime_worker.py')
        r=docker('start','--attach',name,timeout=plan['maximum_runtime_seconds'],allow_failure=True)
        (output/'stdout').write_bytes(r.stdout);(output/'stderr').write_bytes(r.stderr)
        check(r.returncode==0,'runtime-worker-failed')
        state=json.loads(docker('container','inspect',name).stdout)[0]
        check(not state['State']['Running'] and state['State']['ExitCode']==0,'runtime-worker-state')
        from .runtime_worker import launch_arguments
        measured,closure=launch_arguments()
        check(json.loads((results/'measured-command.json').read_bytes())==measured==plan['measured_maven_arguments'],'runtime-measured-command-changed')
        check(json.loads((results/'command.json').read_bytes())==closure,'runtime-closure-command-changed')
        inventory=json.loads((results/'measured-inventory.json').read_bytes())
        raw=(results/'worker-observation.json').read_bytes();config=(results/'effective-config.ini').read_bytes();surefire=(results/'effective-surefire.properties').read_bytes()
        fork_command=(results/'fork-command.json').read_bytes()
        expected=dict(fork_command_sha256=hashlib.sha256(fork_command).hexdigest(),measured_command_sha256=hashlib.sha256((results/'measured-command.json').read_bytes()).hexdigest(),closure_command_sha256=hashlib.sha256((results/'command.json').read_bytes()).hexdigest(),probe_sha256=plan['files_sha256']['RuntimeClosureAgent.java'],image=IMAGE,java_sha256=plan['java_sha256'],plan_sha256=plan['content_sha256'],tower_decision_sha256=proof['decision_sha256'])
        h=lambda b:hashlib.sha256(b).hexdigest()
        from .transient_sources import copies_at,catalogue
        copies=copies_at(json.loads(raw),results)
        check(catalogue((results/'runtime-catalogue.tsv').read_bytes())==inventory['runtime_catalogue'],'runtime-catalogue-changed')
        from .application_identity import copies_at as application_copies_at
        application_copies=application_copies_at(json.loads(raw),results)
        pending=(raw,config,surefire,inventory,expected,fork_command,copies,application_copies)
    except BaseException as ex:
        failure=type(ex).__name__+': '+str(ex);print('B06 runtime closure failed; preserve output; no retry.',flush=True)
    finally:
        try:
            if created:
                ids=docker('ps','-a','-q','--filter','label='+label).stdout.decode().split();check(len(ids)<=1,'runtime-cleanup-ambiguous')
                for identity in ids:
                    item=json.loads(docker('container','inspect',identity).stdout)[0]
                    check(item['Name']=='/'+name and item['Image']==IMAGE and item['Config']['Labels'].get('lightyear.b06.runtime')==name,'runtime-cleanup-ownership')
                    docker('rm','--force',identity)
                check(not docker('ps','-a','-q','--filter','label='+label).stdout.strip(),'runtime-cleanup-not-absent')
            cleaned=True;validate(root,plan)
            if failure is None and pending is not None:
                raw,config,surefire,inventory,expected,fork_command,copies,application_copies=pending
                receipt=signer.sign(dict(schema='b06-runtime-launch-receipt/6',passed=True,bindings=expected,cleanup_passed=True,
                   outputs={'fork-command':h(fork_command),'observation':h(raw),'config.ini':h(config),'surefire.properties':h(surefire),'inventory':h(json.dumps(inventory,sort_keys=True).encode())}))
                resolution=produce(raw,config,surefire,inventory,receipt,signer.public,expected,fork_command=fork_command,transient_copies=copies,application_copies=application_copies)
                atomic_new(output/'runtime-launch-receipt.json',receipt);atomic_new(output/'resolved-runtime.json',resolution)
        except BaseException as ex:failure=(failure or '')+'; cleanup/snapshot: '+str(ex)
        report=signer.sign(dict(schema='b06-runtime-terminal/1',passed=failure is None and cleaned,cleanup_passed=cleaned,failure=failure,
           elapsed_seconds=time.monotonic()-started,plan_sha256=plan['content_sha256'],snapshot_sha256=plan['snapshot_sha256'],commands=commands,
           resolution_sha256=digest(resolution) if resolution else None,model_calls=0,native_pairs=0))
        atomic_new(output/'report.json',report)
    return report


def main():
    import argparse
    p=argparse.ArgumentParser()
    for name in ('root','plan','repository','output','public-commit','authority','tower-key','credential'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--practice-directory');p.add_argument('--authorization-window')
    p.add_argument('--tower-url',default='http://127.0.0.1:8766')
    a=p.parse_args();root=Path(a.root).resolve()
    check(Path.cwd().resolve()==root and Path(__file__).resolve().is_relative_to(root),'frozen-cwd-imports-required')
    plan=json.loads(Path(a.plan).read_bytes());validate(root,plan)
    # Verify public bytes before opening the existing signer or operator session.
    publication(a.repository,root,plan,a.public_commit)
    from tools.ms94_b06_qualification_worker import existing_signer
    from lightyear_control_tower.b06 import DecisionReader
    from lightyear_control_tower.client import ConsoleClient
    signer=existing_signer(a.authority)
    reader=DecisionReader(ConsoleClient(a.tower_url),Path(a.credential).read_text(encoding='utf-8-sig').strip(),Path(a.tower_key).read_bytes())
    result=execute(a.repository,root,plan,a.output,a.public_commit,reader,signer,practice_directory=a.practice_directory,authorization_window=json.loads(Path(a.authorization_window).read_bytes()) if a.authorization_window else None)
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
