"""Detached local journey orchestration with signed decisions and unconditional cleanup."""
from __future__ import annotations
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time
import uuid

from .contracts import canonical, read_json, require, seal, verify
from .journey_order import (ORDER,RUNS,LANES,CASES,COMMANDS,UNCLAIMED,archived,load_order,
                           make_plan,validate_plan,factory_order,save,file_hash,classify)
from lightyear_factory.agents import LocalAgentSet
from lightyear_workflow.campaign_engine import Signer
from lightyear_workflow.campaign_journals import signed_append, check
from lightyear_workflow.run_store import RunStore, utcnow
from lightyear_workflow.run_index import RunIndex
from lightyear_workflow.convergence import INDEX_RELATIVE
from lightyear_control_tower.decisions import verify_envelope
from lightyear_execution.journey_network import InternalOnlyNetwork

CONFIG=Path('work/ms87/local-runtime.json')
CONTROL=Path('work/ms87/operator')


class JourneySigner(Signer):
    def __init__(self,root):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        folder=root/CONTROL;folder.mkdir(parents=True,exist_ok=True)
        private=folder/'authority.key.pem';public=folder/'authority.public.pem'
        if not private.exists():
            key=Ed25519PrivateKey.generate()
            data=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
            with os.fdopen(os.open(private,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:f.write(data)
            public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        self.key=serialization.load_pem_private_key(private.read_bytes(),password=None);self.public=public.read_bytes()
        require(verify_envelope(self.sign({'probe':'journey-authority'}),self.public),'Journey key pair differs')


def docker(*args,timeout=120,input=None,check_code=True):
    p=subprocess.run(['docker',*map(str,args)],input=input,capture_output=True,timeout=timeout)
    if check_code and p.returncode:
        raise RuntimeError('Docker operation failed: '+str(args[:2])+': '+p.stderr.decode(errors='replace')[:500])
    return p


def inspect(kind,name):
    return json.loads(docker(kind,'inspect',name).stdout)[0]


def inventory(root):
    order=load_order(root)
    info=json.loads(docker('info','--format','{{json .}}').stdout)
    ids={lane:inspect('image',x['image_digest'])['Id'] for lane,x in order['environment']['engines'].items()}
    return {'memory_bytes':info['MemTotal'],'free_bytes':shutil.disk_usage(root).free,'images':ids}


def read_local(root):
    value=read_json(root/CONFIG)
    require(inspect('image',value['runner_image'])['Id']==value['runner_image'],'Prepared runner image missing')
    require(inspect('volume',value['postgresql_seed_volume'])['Name']==value['postgresql_seed_volume'],'Checkpoint volume missing')
    return value


def run_folder(root,name):
    InternalOnlyNetwork(name)
    result=root/RUNS/name
    require(not any(p.is_symlink() for p in (result,*result.parents)),'Symbolic run path')
    return result


def approval(root,plan):
    signer=JourneySigner(root);path=root/CONTROL/'approvals'/(plan['declaration_sha256']+'.json')
    if not path.exists():return None
    value=read_json(path)
    require(verify_envelope(value,signer.public) and value['declaration_sha256']==plan['declaration_sha256']
            and value['action_kind']=='approve-declaration','Declaration approval signature differs')
    return value


def cancelled(run):
    path=run/'cancel-request.json'
    if not path.exists():return False
    root=run.parents[len(RUNS.parts)]
    request=read_json(path)
    key=(root/CONTROL/'authority.public.pem').read_bytes()
    require(verify_envelope(request,key) and request['run_id']==run.name and request['action']=='cancel', 'Invalid signed cancellation')
    return True


class JourneyAbort(RuntimeError):
    def __init__(self,code):self.code=code;super().__init__(code)


class LocalRunner:
    def __init__(self,root,run,plan,emit):
        self.root,self.run,self.plan,self.emit=root,run,plan,emit
        self.owner=run.name;self.label='lightyear.journey='+self.owner
        self.resources=[];self.retained=[];self.password=None;self.deadline=time.monotonic()+plan['declaration']['policy']['max_elapsed_seconds']

    def checkpoint(self,stage):
        if cancelled(self.run):raise JourneyAbort('cancelled')
        if time.monotonic()>=self.deadline:raise JourneyAbort('timeout')
        for path,expected in self.plan['implementation_sha256'].items():
            if file_hash(self.root/path)!=expected:
                self.emit('intervention',{'reason':'implementation-changed','path':path})
                raise JourneyAbort('scope-boundary')
        for name,expected in self.plan.get('inputs_sha256',{}).items():
            require(file_hash(self.run/'inputs'/name)==expected,'Pinned run input changed')
        self.emit('stage',{'stage':stage})

    def owned(self,kind):
        flags=['-a'] if kind=='container' else []
        return docker(kind,'ls',*flags,'-q','--filter','label='+self.label).stdout.decode().split()

    def remember(self,kind,name):
        self.resources.append({'kind':kind,'name':name})
        save(self.run/'resources.json',{'resources':self.resources})

    def prepare(self,case,attempt):
        self.checkpoint('prepare:'+case)
        prefix=self.owner+'-'+case+'-'+str(attempt);self.network=prefix+'-net'
        docker(*InternalOnlyNetwork(self.owner).create_args(self.network));self.remember('network',self.network)
        self.password=secrets.token_hex(24)
        order=self.plan['declaration'];self.names={lane:prefix+'-'+lane for lane in LANES}
        images={lane:order['environment']['engines'][lane]['image_digest'] for lane in LANES}
        self.volume=prefix+'-pgdata'
        docker('volume','create','--label',self.label,self.volume);self.remember('volume',self.volume)
        copier=prefix+'-copy'
        docker('run','--name',copier,'--label',self.label,'--network','none','--entrypoint','sh',
               '--mount',f'type=volume,src={self.plan["local"]["postgresql_seed_volume"]},dst=/source,readonly',
               '--mount',f'type=volume,src={self.volume},dst=/destination',images['postgresql'],
               '-c','cd /source && tar cf - . | tar xf - -C /destination',timeout=180)
        docker('rm',copier)
        for lane in LANES:
            args=['create','--name',self.names[lane],'--label',self.label,'--label','lightyear.case='+case,
                  '--network',self.network,'--network-alias',lane,'--memory','6g' if lane=='oracle' else '2g',
                  '--cpus','2','--security-opt','no-new-privileges']
            if lane=='postgresql':args+=['--mount',f'type=volume,src={self.volume},dst=/var/lib/postgresql/data']
            docker(*args,images[lane]);self.remember('container',self.names[lane]);docker('start',self.names[lane])
        self.runner=prefix+'-runner'
        docker('create','--name',self.runner,'--label',self.label,'--network',self.network,'--memory','8g','--cpus','4',
               '--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/secrets:rw,noexec,nosuid,size=268435456',
               '--mount',f'type=bind,src={self.root / "src"},dst=/verifier/src,readonly',
               '--mount',f'type=bind,src={self.run},dst=/output',self.plan['local']['runner_image'])
        self.remember('container',self.runner);docker('start',self.runner)
        policy=InternalOnlyNetwork(self.owner)
        policy.verify(inspect('network',self.network),[inspect('container',x) for x in [*self.names.values(),self.runner]])
        # No host ports, no second network, and no route to the public Internet.
        result=docker('exec',self.runner,'python','-c',
                      'import socket; s=socket.socket(); s.settimeout(2); r=s.connect_ex(("1.1.1.1",443)); s.close(); assert r != 0; print("no-public-egress")')
        self.emit('isolation',{'case':case,'network':self.network,'internal':True,'published_ports':False,
                               'public_egress_probe_blocked':True})
        self.rotate_passwords()
        folder=self.run/'cases'/case/str(attempt);folder.mkdir(parents=True,exist_ok=False)
        for lane in LANES:
            self.checkpoint('prepare-lane:'+case+':'+lane)
            self.worker('prepare',{'lane':lane,'output':self.inside(folder/'baseline'/lane),
                                  'expected_version':order['environment']['engines'][lane]['expected_version']},timeout=1800)
        self.emit('entry-prepared',{'case':case,'attempt':attempt})
        return folder

    def rotate_passwords(self):
        for lane,name in self.names.items():
            for attempt in range(120):
                self.check_cancel()
                if lane=='oracle':
                    script=("whenever sqlerror exit failure\nconnect / as sysdba\nalter session set container=FREEPDB1;\n"
                            f'alter user adempiere identified by "{self.password}";\nexit\n').encode()
                    p=docker('exec','-i','--user','oracle',name,'sqlplus','-s','/nolog',input=script,check_code=False,timeout=30)
                else:
                    p=docker('exec','-i',name,'psql','-X','-v','ON_ERROR_STOP=1','-U','adempiere','-d','idempiere',
                             input=(f"ALTER ROLE adempiere PASSWORD '{self.password}';\n").encode(),check_code=False,timeout=30)
                if p.returncode==0:
                    try:self.worker('probe',{'lane':lane},timeout=15);break
                    except Exception:pass
                time.sleep(2)
            else:raise JourneyAbort('container-start')

    def check_cancel(self):
        if cancelled(self.run):raise JourneyAbort('cancelled')
        if time.monotonic()>=self.deadline:raise JourneyAbort('timeout')

    def inside(self,path):return '/output/'+path.relative_to(self.run).as_posix()

    def worker(self,command,payload,timeout):
        """Only generated secrets cross stdin; neither CLI nor evidence contains them."""
        args=['docker','exec','-i',self.runner,'python','-m','lightyear_calibration.journey_worker',command]
        process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        start=time.monotonic();data=canonical({**payload,'password':self.password})
        try:
            while True:
                try:
                    out,err=process.communicate(input=data,timeout=1);break
                except subprocess.TimeoutExpired:
                    data=None;self.check_cancel()
                    if time.monotonic()-start>=timeout:raise JourneyAbort('timeout')
            if process.returncode:
                safe=(out+err).decode(errors='replace').replace(self.password,'[redacted]')
                save(self.run/'worker-failures'/(uuid.uuid4().hex+'.json'),{
                    'command':command,'lane':payload.get('lane'),'output':payload.get('output'),
                    'exit_code':process.returncode,'diagnostic':safe[-6000:]})
                raise RuntimeError('Native worker failed: '+safe[-1500:])
            return json.loads(out)
        finally:
            if process.poll() is None:
                process.kill();process.communicate()
                # Killing docker exec alone leaves its child running. Stop the
                # owning container immediately, then let unconditional cleanup run.
                docker('kill',self.runner,check_code=False)

    def execute(self,case,folder):
        self.checkpoint('execute:'+case)
        if case=='diagnostic-first-only':h={'test':'LightyearOperationsTest','sha256':self.plan['diagnostic_harness_sha256'],'file':'diagnostic.java'}
        else:
            h=next(x for x in self.plan['declaration']['application']['harnesses'] if x['id']==case)
            h={**h,'file':case+'.java'}
        for lane in LANES:
            self.checkpoint('execute-lane:'+case+':'+lane)
            result=self.worker('execute',{'lane':lane,'output':self.inside(folder/'execution'/lane),
                               'harness':'/output/inputs/'+h['file'],'harness_sha256':h['sha256'],'test':h['test'],
                               'source_commit':self.plan['declaration']['application']['source_commit'],'timeout_seconds':1200},timeout=1250)
            self.emit('native-execution',{'case':case,'lane':lane,'execution_sha256':result['content_sha256'],'exit_code':result['exit_code']})
            if result['exit_code']==124:raise JourneyAbort('timeout')
            expected=1 if case=='diagnostic-first-only' and lane=='oracle' else 0
            if result['exit_code']!=expected:raise JourneyAbort('known-finding-changed' if case=='diagnostic-first-only' else 'harness-exception')
            self.worker('capture',{'lane':lane,'output':self.inside(folder/'after'/lane)},timeout=1800)

    def gate(self,command):
        definition=next(g for g in self.plan['declaration']['acceptance']['gates'] if g['command'][3]==command)
        args=[sys.executable,'-m','lightyear_calibration.journey_order',command,'--run',str(self.run)]
        output=self.run/'gate-logs'/(command+'.log');output.parent.mkdir(exist_ok=True)
        with output.open('wb') as stream:
            process=subprocess.Popen(args,cwd=self.root,stdout=stream,stderr=subprocess.STDOUT,
                env={**os.environ,'PYTHONPATH':str(self.root/'src'),'PYTHONUTF8':'1'})
            started=time.monotonic()
            try:
                while process.poll() is None:
                    self.check_cancel()
                    if time.monotonic()-started>=definition['timeout_seconds']:raise JourneyAbort('timeout')
                    try:process.wait(timeout=1)
                    except subprocess.TimeoutExpired:pass
            finally:
                if process.poll() is None:process.kill();process.wait()
        require(process.returncode==0,'Gate failed: '+command)
        result=read_json(self.run/'gates'/(command+'.json'));verify(result)
        require(result['passed'] is True and result['plan_sha256']==self.plan['content_sha256'],'Gate result differs')
        return result

    def cleanup(self,retain=False):
        retained=['cases/'] if retain and (self.run/'cases').exists() else [];errors=[]
        containers=self.owned('container')
        for cid in containers:
            try:
                info=inspect('container',cid);name=info['Name'].lstrip('/')
                docker('stop','--time','2' if name.endswith('-runner') else '30',cid,timeout=45,check_code=False)
                if retain and name.endswith('-oracle'):
                    # Export only filesystem data, never image Config/Env secrets.
                    target=self.run/'retained'/(name+'.tar');target.parent.mkdir(exist_ok=True)
                    docker('export','--output',target,cid,timeout=600)
                    retained.append(str(target.relative_to(self.run)))
                docker('rm','-f',cid,timeout=60)
            except Exception as exc:errors.append(type(exc).__name__)
        for nid in self.owned('network'):
            try:docker('network','rm',nid)
            except Exception as exc:errors.append(type(exc).__name__)
        for vid in self.owned('volume'):
            if retain or 'docker-volume:'+vid in self.retained:retained.append('docker-volume:'+vid)
            else:
                try:docker('volume','rm',vid)
                except Exception as exc:errors.append(type(exc).__name__)
        self.password=None
        self.retained=sorted(set(self.retained+retained))
        remaining=self.owned('container');networks=self.owned('network')
        return {'complete':not errors and not remaining and not networks,'remaining_containers':remaining,
                'remaining_networks':networks,'credentials_destroyed':not remaining,
                'retained_data':self.retained,'errors':errors}


def append_decision(root,plan,kind,reason,cases,run_id):
    value=JourneySigner(root).sign({'artifact_type':'lightyear-journey-decision-request','id':uuid.uuid4().hex,
          'action_kind':kind,'action_class':'approval-required','owner_role':'business-owner',
          'declaration_sha256':plan['declaration_sha256'],'run_id':run_id,'reason':reason,'affected_cases':cases,'at':utcnow()})
    save(root/CONTROL/'requests'/(value['id']+'.json'),value)
    return value


def timestamp_acknowledged(root,plan):
    folder=root/CONTROL/'decisions'
    if not folder.exists():return False
    signer=JourneySigner(root)
    for p in folder.glob('*.json'):
        v=read_json(p)
        if verify_envelope(v,signer.public) and v.get('declaration_sha256')==plan['declaration_sha256'] and v.get('action_kind')=='accept-contract-equivalence' and v.get('outcome')=='retain-open-finding':return True
    return False


def execute_run(root,run,runner_type=LocalRunner):
    plan=read_json(run/'plan.json');verify(plan);signer=JourneySigner(root)
    auth=read_json(run/'authorization.json')
    require(verify_envelope(auth,signer.public) and auth['plan']['plan_sha256']==plan['content_sha256'],'Invalid run authorization')
    validate_plan(root,plan,read_local(root),inventory(root))
    store=RunStore(run/'journal')
    require(not store.events(),'Run already started; recovery or resume is required')
    def emit(kind,payload):
        body={k:v for k,v in payload.items() if k not in ('signature','content_sha256')}
        return signed_append(store,signer,auth,kind,body,'journey')
    runner=runner_type(root,run,plan,emit);status='failed';error=None;requests=[]
    selected={case:ref['attempt'] for case,ref in auth.get('case_references',{}).items()};cleanup=None
    schedule=auth.get('cases_to_execute',list(CASES))
    require(set(schedule)|set(selected)==set(CASES) and not set(schedule)&set(selected),'Resume case partition invalid')
    def interrupted(*_):raise JourneyAbort('cancelled')
    previous_signals={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM)}
    emit('started',{'declaration_sha256':plan['declaration_sha256'],'builder':'idle','model_calls':0,
                    'human_interventions_outside_designed_stops':0})
    try:
        for case in schedule:
            for attempt in range(1,plan['declaration']['policy']['max_attempts']+1):
                emit('round',{'case':case,'attempt':attempt})
                try:
                    folder=runner.prepare(case,attempt);runner.execute(case,folder)
                    selected[case]=attempt;save(run/'selected-attempts.json',selected)
                    emit('result',{'case':case,'attempt':attempt,'boundary':{'model_calls':0}})
                    clean=runner.cleanup(retain=False);emit('pair-cleanup',clean)
                    require(clean['complete'],'Cleanup failure')
                    break
                except Exception as exc:
                    code=exc.code if isinstance(exc,JourneyAbort) else ('entry-state-mismatch' if 'entry' in str(exc).lower() or 'starting rows' in str(exc) else 'harness-exception')
                    message=str(exc)
                    if getattr(runner,'password',None):message=message.replace(runner.password,'[redacted]')
                    emit('attempt-exception',{'case':case,'attempt':attempt,**classify(code),
                                             'error_type':type(exc).__name__,'diagnostic':message[-1500:]})
                    clean=runner.cleanup(retain=True);emit('pair-cleanup',clean)
                    require(clean['complete'],'Cleanup failure')
                    if not classify(code)['retryable'] or attempt==plan['declaration']['policy']['max_attempts']:raise
        runner.checkpoint('verify')
        from .journey_verify import verify_gate
        # Check expected faults before outcomes so a disappearing fault is a
        # designed decision stop, never an accidental promotion to passing.
        for command in ['verify-entry','verify-known-findings','verify-differences','verify-outcomes','verify-footprint']:
            try:
                result=runner.gate(command);emit('gate',{'command':command,'receipt_sha256':result['content_sha256'],'passed':True})
            except JourneyAbort:
                raise
            except Exception as exc:
                code='known-finding-changed' if command=='verify-known-findings' else 'unknown-difference' if command=='verify-differences' else 'entry-state-mismatch' if command=='verify-entry' else 'gate-failed'
                raise JourneyAbort(code) from exc
        status='reproduced-with-known-findings'
        if not timestamp_acknowledged(root,plan):
            requests.append(append_decision(root,plan,'accept-contract-equivalence','Oracle loses the declared fractional shipment time. Acknowledge it as open for replay or require remediation; boundary equivalence stays false.',['boundary'],run.name))
            status='halted-for-decision'
    except Exception as exc:
        code=exc.code if isinstance(exc,JourneyAbort) else 'cleanup-failure' if 'Cleanup' in str(exc) else 'execution-failure'
        error={'classification':code,'exception_type':type(exc).__name__}
        analysis=LocalAgentSet().analyze_failure(factory_order(plan['declaration']),{'gates':[{'id':code,'status':'failed'}]},1)
        emit('exception',{**error,'failure_analysis':analysis})
        if classify(code)['action']:
            requests.append(append_decision(root,plan,classify(code)['action'],code,list(CASES),run.name));status='halted-for-decision'
    finally:
        # Decisions never hold a live database. Cancellation also reaches this
        # finalizer. Abrupt process death is handled by the detached watchdog.
        cleanup=runner.cleanup(retain=error is not None)
        signed=signer.sign({'artifact_type':'lightyear-journey-cleanup','run_id':run.name,'plan_sha256':plan['content_sha256'],'at':utcnow(),**cleanup})
        save(run/'cleanup.json',signed);emit('cleanup',signed)
        if not cleanup['complete']:status='failed';error={'classification':'cleanup-failure'}
        for request in requests:emit('blocked',{'reason':'human-decision-required','request':request})
        gate_ok=False
        if cleanup['complete']:
            from .journey_verify import verify_gate
            result=verify_gate(run,'verify-cleanup');emit('gate',{'command':'verify-cleanup','passed':True,'receipt_sha256':result['content_sha256']});gate_ok=True
        receipt=signer.sign({'artifact_type':'lightyear-native-journey-run','run_id':run.name,
                    'plan_sha256':plan['content_sha256'],'declaration_sha256':plan['declaration_sha256'],
                    'status':status,'reason':'human-decision-required' if status=='halted-for-decision' else status,
                    'known_findings_reproduced':error is None and len(selected)==3,
                    'bounded_operations_equivalence':error is None and len(selected)==3,
                    'model_calls':0,'human_interventions_outside_designed_stops':sum(e['type']=='intervention' for e in store.events()),
                    'executed_cases':schedule,'inherited_cases':sorted(set(CASES)-set(schedule)),
                    'unattended_run':cleanup['complete'] and error is None and not any(e['type']=='intervention' for e in store.events()),
                    'cleanup_sha256':signed['content_sha256'],'requests':[x['id'] for x in requests],
                    'error':error,'cloud_resources_started':False,**UNCLAIMED})
        emit('halted',receipt);save(run/'receipt.json',receipt)
        try:events=check(store.events(),auth,signer.public,'journey')
        finally:store.close()
        archive=run/(run.name+'.json.gz');archive.write_bytes(gzip.compress(canonical({'events':events}),mtime=0))
        RunIndex(root/INDEX_RELATIVE).record(run.name,'idempiere','ms86-journeys',events,archive)
        save(run/'journal.json',events)
        for sig,handler in previous_signals.items():signal.signal(sig,handler)
    return receipt


def spawn(root,run):
    kwargs={'cwd':root,'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,
            'env':{**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONUTF8':'1'}}
    if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.DETACHED_PROCESS|subprocess.CREATE_NO_WINDOW
    else:kwargs['start_new_session']=True
    p=subprocess.Popen([sys.executable,'-m','lightyear_calibration.journey_runtime','execute',str(root),str(run)],**kwargs)
    save(run/'process.json',{'pid':p.pid,'started_at':utcnow()})
    subprocess.Popen([sys.executable,'-m','lightyear_calibration.journey_runtime','watch',str(root),str(run),str(p.pid)],**kwargs)
    return p.pid


def dispatch_command(root,args):
    command=args.command;signer=JourneySigner(root)
    if command in ('plan','approve','start'):
        local=read_local(root);plan=make_plan(root,local,inventory(root));save(root/'work/ms87/plan.json',plan)
    if command=='plan':
        return {'plan_sha256':plan['content_sha256'],'declaration_sha256':plan['declaration_sha256'],
                'approved':approval(root,plan) is not None,'plan_file':'work/ms87/plan.json',
                'resources':plan['resources'],'cases':plan['cases'],'model_calls':0,'cloud_resources':False}
    if command=='approve':
        require(args.plan_sha256==plan['content_sha256'],'Approval requires the exact current plan')
        require(args.actor and args.reason and len(args.reason)>=10,'Named operator and authorization reason required')
        result=signer.sign({'artifact_type':'lightyear-journey-declaration-approval','action_kind':'approve-declaration',
              'actor':args.actor,'roles':{r:args.actor for r in ('business-owner','claim-owner','engineering')},
              'reason':args.reason,'at':utcnow(),'declaration_sha256':plan['declaration_sha256'],
              'reviewed_plan_sha256':plan['content_sha256'],'authority':'local operator countersignature, not independent attestation'})
        save(root/CONTROL/'approvals'/(plan['declaration_sha256']+'.json'),result);return result
    if command=='start':
        require(args.plan_sha256==plan['content_sha256'],'Stale plan digest refused')
        accepted=approval(root,plan);require(accepted is not None,'human-decision-required: approve-declaration')
        for p in (root/RUNS).glob('journey-*'):
            require((p/'receipt.json').exists() and read_json(p/'cleanup.json')['complete'],'Another run is active or needs cleanup recovery')
        run=run_folder(root,'journey-'+uuid.uuid4().hex);run.mkdir(parents=True,exist_ok=False)
        save(run/'plan.json',plan);(run/'authority.public.pem').write_bytes(signer.public)
        inputs=archived(root)
        for h in plan['declaration']['application']['harnesses']:inputs[h['id']+'.java']=(root/h['file']).read_bytes()
        (run/'inputs').mkdir()
        for name,data in inputs.items():(run/'inputs'/name).write_bytes(data)
        auth=signer.sign({'record_type':'native-journey-authorization','run_id':run.name,
                         'plan':{'plan_sha256':plan['content_sha256']},'approval_sha256':accepted['content_sha256'],'at':utcnow()})
        save(run/'authorization.json',auth);pid=spawn(root,run)
        return {'run_id':run.name,'pid':pid,'status':'dispatched','run_path':str(run)}
    require(args.run is not None,'Run path required');run=args.run.resolve()
    require(run.parent==(root/RUNS).resolve(),'Unknown journey run directory');InternalOnlyNetwork(run.name)
    if command=='status':
        if (run/'receipt.json').exists():return read_json(run/'receipt.json')
        events=RunStore(run/'journal',read_only=True).events()
        return {'run_id':run.name,'status':'running','latest':events[-1] if events else None}
    if command=='cancel':
        request=signer.sign({'action':'cancel','run_id':run.name,'actor':args.actor,'at':utcnow()});save(run/'cancel-request.json',request);return request
    if command=='recover':return recover(root,run)
    if command=='decision':
        request=read_json(root/CONTROL/'requests'/(args.decision_id+'.json'))
        require(verify_envelope(request,signer.public) and request['run_id']==run.name,'Unknown decision request')
        require(args.actor and args.reason and len(args.reason)>=10,'Decision requires named operator and reason')
        require(request['action_kind']=='accept-contract-equivalence' and args.outcome=='retain-open-finding',
                'Only retain-open-finding is supported; semantic acceptance requires a new reviewed declaration')
        value=signer.sign({'artifact_type':'lightyear-journey-human-decision','request_sha256':request['content_sha256'],
             'declaration_sha256':request['declaration_sha256'],'action_kind':request['action_kind'],
             'actor':args.actor,'reason':args.reason,'outcome':args.outcome,'at':utcnow(),'affected_cases':request['affected_cases']})
        save(root/CONTROL/'decisions'/(request['id']+'.json'),value);return value
    if command=='resume':
        old=read_json(run/'receipt.json');plan=read_json(run/'plan.json')
        require(verify_envelope(old,signer.public) and old['status']=='halted-for-decision','Only a signed decision halt can resume')
        validate_plan(root,plan,read_local(root),inventory(root))
        clean=read_json(run/'cleanup.json')
        require(verify_envelope(clean,signer.public) and clean['content_sha256']==old['cleanup_sha256'] and clean['complete'],'Resume requires signed complete parent cleanup')
        parent_auth=read_json(run/'authorization.json')
        require(verify_envelope(parent_auth,signer.public),'Parent authorization differs')
        require(not parent_auth.get('case_references'),'Resume of an inherited run requires a fresh full replay')
        affected=set()
        for request_id in old['requests']:
            request=read_json(root/CONTROL/'requests'/(request_id+'.json'))
            decision=read_json(root/CONTROL/'decisions'/(request_id+'.json'))
            require(verify_envelope(request,signer.public) and verify_envelope(decision,signer.public) and decision['request_sha256']==request['content_sha256'],'Every decision must be recorded before resume')
            require(decision['outcome']=='retain-open-finding','Unsupported resume decision')
            affected.update(request['affected_cases'])
        require(affected and affected<=set(CASES),'Invalid affected cases')
        selected=read_json(run/'selected-attempts.json')
        child=run_folder(root,'journey-'+uuid.uuid4().hex);child.mkdir()
        save(child/'plan.json',plan);(child/'authority.public.pem').write_bytes(signer.public)
        shutil.copytree(run/'inputs',child/'inputs')
        references={case:{'run_id':run.name,'receipt_sha256':old['content_sha256'],'attempt':selected[case]}
                    for case in CASES if case not in affected}
        auth=signer.sign({'record_type':'native-journey-authorization','run_id':child.name,
             'plan':{'plan_sha256':plan['content_sha256']},'parent_receipt_sha256':old['content_sha256'],
             'case_references':references,'cases_to_execute':[c for c in CASES if c in affected],'at':utcnow()})
        save(child/'authorization.json',auth);pid=spawn(root,child)
        return {'run_id':child.name,'pid':pid,'status':'resumed','affected_cases':sorted(affected),'run_path':str(child)}
    raise ValueError('Unknown journey command')


def recover(root,run,*,manual=True):
    plan=read_json(run/'plan.json');verify(plan);signer=JourneySigner(root)
    auth=read_json(run/'authorization.json')
    require(verify_envelope(auth,signer.public) and auth['run_id']==run.name
            and auth['plan']['plan_sha256']==plan['content_sha256'],'Recovery authorization invalid')
    runner=LocalRunner(root,run,plan,lambda *_:None)
    cleaned=runner.cleanup(retain=True)
    result=signer.sign({'artifact_type':'lightyear-journey-cleanup','run_id':run.name,'plan_sha256':plan['content_sha256'],
                        'recovery':True,'at':utcnow(),**cleaned})
    save(run/'recovery-cleanup.json',result)
    if not (run/'receipt.json').exists():
        try:store=RunStore(run/'journal')
        except ValueError:return result  # Active engine still owns its finalizer.
        try:
            events=check(store.events(),auth,signer.public,'journey')
            def emit(kind,payload):
                return signed_append(store,signer,auth,kind,{k:v for k,v in payload.items() if k not in ('signature','content_sha256')},'journey')
            if not events:emit('started',{'recovery_before_start':True,'model_calls':0})
            if not events or events[-1]['type']!='halted':
                emit('intervention' if manual else 'automatic-recovery',{'reason':'worker-interrupted','manual':manual})
                emit('cleanup',result);save(run/'cleanup.json',result)
                receipt=signer.sign({'artifact_type':'lightyear-native-journey-run','run_id':run.name,
                    'plan_sha256':plan['content_sha256'],'declaration_sha256':plan['declaration_sha256'],
                    'status':'failed','reason':'interrupted-recovered' if cleaned['complete'] else 'cleanup-failure',
                    'known_findings_reproduced':False,'bounded_operations_equivalence':False,'model_calls':0,
                    'human_interventions_outside_designed_stops':int(manual),'unattended_run':False,
                    'cleanup_sha256':result['content_sha256'],'error':{'classification':'worker-interrupted'},
                    'requests':[],'cloud_resources_started':False,**UNCLAIMED})
                emit('halted',receipt);save(run/'receipt.json',receipt)
            events=check(store.events(),auth,signer.public,'journey')
        finally:store.close()
        archive=run/(run.name+'.json.gz');archive.write_bytes(gzip.compress(canonical({'events':events}),mtime=0))
        RunIndex(root/INDEX_RELATIVE).record(run.name,'idempiere','ms86-journeys',events,archive)
        save(run/'journal.json',events)
    return result


def main():
    root=Path(sys.argv[2]);run=Path(sys.argv[3]);command=sys.argv[1]
    if command=='execute':
        try:execute_run(root,run)
        except BaseException as exc:
            save(run/'engine-error.json',{'exception_type':type(exc).__name__,'message':str(exc)[:1000]})
            recover(root,run,manual=False)
    elif command=='watch':
        pid=int(sys.argv[4]);deadline=time.monotonic()+read_json(run/'plan.json')['declaration']['policy']['max_elapsed_seconds']+120
        while not (run/'receipt.json').exists() and time.monotonic()<deadline:
            if not process_alive(pid):break
            time.sleep(5)
        if not (run/'receipt.json').exists():recover(root,run,manual=False)


def process_alive(pid):
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return False
        try:
            code=wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except OSError:return False


if __name__=='__main__':main()
