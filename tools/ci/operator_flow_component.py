"""CI-only actual operator-wrapper component rehearsal.

Exercises disposable signing, raw HTTP export, native journal/decision checks,
local metadata publication and native plan preflight. Does NOT exercise remote
publication, global nonce admission, OCI/controller admission or model calls.
A passing component cannot release any real signing pack.
"""
import hashlib,json,os,shutil,subprocess,sys,threading,time,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def write(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)
def command(args,*,cwd=None):
    result=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=300)
    if result.returncode:raise RuntimeError('fixture-command-refused:'+Path(str(args[0])).name)
    return result.stdout.strip()
def git(root,*args):return command(['git','-C',str(root),*args])

def main():
    # All disposable key/service/wrapper operations are below this CI boundary.
    if (sys.platform!='win32' or os.environ.get('GITHUB_ACTIONS')!='true'
            or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted'
            or os.environ.get('GITHUB_REPOSITORY')!='howardweale/lightyear-carddemo-modernization'):
        raise SystemExit('disposable-operator-rehearsal-ci-only')
    source=Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    temporary=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    for root in (source,temporary):
        if any(x.lower()=='onedrive' for x in root.parts) or "'" in str(root):
            raise SystemExit('disposable-rehearsal-root-refused')
        if any(p.is_symlink() or p.is_junction() for p in (root,*root.parents)):
            raise SystemExit('disposable-rehearsal-redirect-refused')
    base=temporary/('operator-flow-'+uuid.uuid4().hex);base.mkdir()
    repo=base/'repository';repo.mkdir()
    runtime=base/'runtime';data=base/'factory';data.mkdir()
    pack=base/'fixture-inputs';pack.mkdir()
    output=base/'operator-output'
    report_path=temporary/'operator-flow-component-timings.json'
    if report_path.exists():raise SystemExit('component-report-already-exists')
    stages=[];service=None;http=None;started=time.perf_counter()
    report={'fixture_only':True,'full_route_passed':False,'real_pack_ready':False,
        'sample_count':0,'remote_publication_measured':False,'nonce_admission_measured':False,
        'complete_signature_to_execution_ready_minutes':None,'stages':stages,
        'omitted':['remote publication and final guards','global nonce and OCI/controller admission',
                   'full admission/remote failure matrix (wrapper-only refusals covered)','CI queue/setup and real human decision time']}
    def measure(name,action):
        began=datetime.now(timezone.utc);tick=time.perf_counter()
        row={'stage':name,'started_at':began.isoformat(),'status':'running'};stages.append(row)
        try:
            result=action();row['status']='passed';return result
        except BaseException:
            row['status']='failed';raise
        finally:
            row['finished_at']=datetime.now(timezone.utc).isoformat()
            row['elapsed_seconds']=time.perf_counter()-tick
            row['elapsed_minutes']=row['elapsed_seconds']/60
    try:
        from lightyear_control_tower.console import ConsoleService,provision
        from lightyear_control_tower.server import create_server
        from lightyear_factory.model_admission import FactoryModelAdmission
        from tools.factory_install.journal_head import verified_head
        def prepare_static():
            # Independent fixture checkout and interpreter mirror. No production
            # runtime, authority, data path, remote, secret or approval variable.
            git(repo,'init','--initial-branch=fixture')
            git(repo,'config','user.name','Disposable CI Fixture')
            git(repo,'config','user.email','fixture@invalid.example')
            git(repo,'config','core.autocrlf','false')
            for name in ('src','tools'):
                shutil.copytree(source/name,repo/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            inputs={}
            for name in ('scope','freeze','workspace','execution_policy'):
                relative='docs/factory/fixture/'+name+'.json';raw=canonical({'fixture_only':True,'input':name})
                write(repo/relative,raw);inputs[name]={'path':relative,'sha256':hashlib.sha256(raw).hexdigest()}
            git(repo,'add','--all');git(repo,'commit','-m','Disposable executable and public fixture inputs')
            executable=git(repo,'rev-parse','HEAD')
            runtime.mkdir()
            shutil.copytree(Path(sys.base_prefix),runtime/'python',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            app=runtime/'app';app.mkdir()
            for name in ('src','tools'):shutil.copytree(repo/name,app/name)
            inventory=[{'path':str(p),'sha256':digest(p)} for p in sorted(app.rglob('*')) if p.is_file()]
            write(pack/'runtime-inventory.json',canonical({'complete':True,'files':inventory}))
            return executable,inputs
        executable,inputs=measure('non-proof-static-preparation',prepare_static)
        authority=base/'authority'/'authority.json'
        credential_path=provision(authority,'factory','ci-fixture','Disposable CI actor')
        service=ConsoleService(data,authority)
        service.grant_roles('ci-fixture',['operator','campaign-authorizer'],
            reason='Disposable CI rehearsal only; never real approval',workloads=['factory:factory'])
        token=service.login(credential_path.read_text().strip())['token']
        write(pack/'public.pem',service.public_key)
        http=create_server(service,port=0)
        if http.server_port in (8768,8769):raise RuntimeError('reserved-port-refused')
        threading.Thread(target=http.serve_forever,daemon=True).start()
        url='http://127.0.0.1:'+str(http.server_port)
        sign_start=datetime.now(timezone.utc)+timedelta(minutes=2)
        sign_end=sign_start+timedelta(minutes=5);end=sign_start+timedelta(hours=1)
        caps=dict(max_attempts=1,max_elapsed_seconds=60,max_model_calls=1,max_model_tokens=1000,
                  max_repair_loops=1,cost_cap_microusd=1000000)
        order=SimpleNamespace(content_sha256='a'*64,max_attempts=1,max_elapsed_seconds=60,
                              max_model_calls=1,max_model_tokens=1000,max_model_cost_usd=1)
        plan=dict(schema='factory-build-plan/1',work_order_sha256=order.content_sha256,
            executable_commit=executable,bound_inputs=inputs,caps=caps,
            roles={r:{'provider':'openai','model':'gpt-4.1-2025-04-14'} for r in ('planner','builder','analyst')},
            drill_admission={'case_id':'human-clean-control'})
        plan['content_sha256']=hashlib.sha256(canonical(plan)).hexdigest()
        contract=dict(schema='factory-contract/1',kind='engineering-run-approval',program='factory',
            sources=[dict(row,commit=executable) for row in inputs.values()],
            details=dict(executable_commit=executable,request_seal=plan['content_sha256'],
                observer_sha256='b'*64,class_hashes={'fixture':'c'*64},
                window={'start':sign_start.isoformat(),'end':end.isoformat()},caps=caps))
        write(pack/'plan.json',canonical(plan));write(pack/'contract.json',canonical(contract))
        paths={'plan':pack/'plan.json','contract':pack/'contract.json','public-key':pack/'public.pem',
            'python':runtime/'python/python.exe','entry':runtime/'app/tools/factory_install/entry.py',
            'journal-head':runtime/'app/tools/factory_install/journal_head.py',
            'runtime-source-inventory':pack/'runtime-inventory.json'}
        manifest=dict(repository=str(repo),output_directory=str(output),case_id='human-clean-control',ready=True,
            executable_commit=executable,contract_sha256=digest(pack/'contract.json'),
            runtime_root=str(runtime),factory_root=str(data),factory_url=url,
            signing_window={'start':sign_start.isoformat(),'end':sign_end.isoformat()},
            execution_window={'start':sign_end.isoformat(),'end':end.isoformat()},
            files=[{'label':k,'path':str(v),'sha256':digest(v)} for k,v in paths.items()])
        manifest_path=pack/'manifest.json';write(manifest_path,canonical(manifest))
        template_path=source/'tests/fixtures/operator_flow/fixed-wrapper.ps1.txt'
        original=template_path.read_bytes()
        if hashlib.sha256(original).hexdigest()!='0f087c5a2b05c5a79c66b1f3f044df444e38fda4d61d079010965ea9f5d5a0e2':
            raise RuntimeError('reviewed-template-changed')
        wrapper=original.decode()
        replacements={
            '__REPOSITORY_ROOT__':str(repo),
            '__RUNTIME_ROOT__':str(runtime),
            '__FACTORY_ROOT__':str(data),
            '__FACTORY_URL__':url,
            '__CASE_ID__':'human-clean-control','<UNSET_REVIEWED_MANIFEST_SHA256>':digest(manifest_path)}
        for old,new in replacements.items():
            if old not in wrapper:raise RuntimeError('fixture-render-anchor-missing')
            wrapper=wrapper.replace(old,new)
        rendered=pack/'fixed-wrapper.ps1';write(rendered,wrapper.encode())
        report['template_sha256']=hashlib.sha256(original).hexdigest()
        report['rendered_wrapper_sha256']=digest(rendered)
        def stage(name,*extra):
            return command(['pwsh','-NoProfile','-NonInteractive','-File',str(rendered),
                            '-Stage',name,'-Manifest',str(manifest_path),*map(str,extra)])
        measure('pre-sign-preflight',lambda:stage('Preflight'))
        measure('pre-sign-import',lambda:stage('Prepare'))
        # Wait only inside disposable CI; a late preparation fails, never rebinds.
        remaining=(sign_start-datetime.now(timezone.utc)).total_seconds()
        if remaining<=0:raise RuntimeError('preparation-overran-fixed-fixture-window')
        time.sleep(remaining)
        def sign():
            item=service.review(token,'factory-'+manifest['contract_sha256'])
            return service.decide(token,dict(item_id=item['id'],bound=item['bound'],outcome='approve',
                reason='Disposable CI fixture only; not Howard approval',
                previous_decision_sha256=(item['latest_decision'] or {}).get('content_sha256'),request_id=str(uuid.uuid4())))
        event=measure('disposable-sign',sign);signature_tick=time.perf_counter()
        proof_path=output/'human-proof-bundle.json'
        export_text=measure('actual-wrapper-export-and-native-verify',
            lambda:stage('ExportAndVerify','-Proof',proof_path,'-CredentialFile',credential_path,
                         '-DecisionSha256',event['content_sha256']))
        begin=export_text.index('{');stop=export_text.rindex('}')+1
        summary=json.loads(export_text[begin:stop])
        if summary['status']!='verified-decision-only' or summary['execution_authorized'] is not False:
            raise RuntimeError('wrapper-summary-refused')
        report['wrapper_observation']={k:summary[k] for k in ('stage_elapsed_seconds','decision_to_verified_seconds',
            'export_started_at','export_finished_at','export_elapsed_seconds','verification_started_at',
            'verification_finished_at','verification_elapsed_seconds')}
        report['export_and_verify_separately_monotonic']=True
        proof_hash=digest(proof_path)
        published=base/'metadata-publication'
        def publish_local():
            command(['git','clone','--no-hardlinks',str(repo),str(published)])
            git(published,'config','user.name','Disposable CI Fixture')
            git(published,'config','user.email','fixture@invalid.example')
            git(published,'config','core.autocrlf','false')
            names=('docs/factory/fixture/plan.json','docs/factory/fixture/proof.json','docs/factory/fixture/contract.json')
            for name,path in zip(names,(pack/'plan.json',proof_path,pack/'contract.json')):
                write(published/name,path.read_bytes())
            git(published,'add','--',*names);git(published,'commit','-m','Disposable exact plan contract proof metadata')
            changed=set(git(published,'diff','--name-only',executable,'HEAD').splitlines())
            if changed!=set(names):raise RuntimeError('fixture-publication-not-metadata-only')
            bare=base/'publication.git'
            command(['git','init','--bare',str(bare)])
            git(published,'push',str(bare),'HEAD:refs/heads/fixture')
            head=git(published,'rev-parse','HEAD')
            if git(bare,'rev-parse','refs/heads/fixture')!=head:raise RuntimeError('fixture-publish-readback')
            return names
        names=measure('local-bare-metadata-publication',publish_local)
        def preflight():
            admission=FactoryModelAdmission(published,*names,public_key=service.public_key,
                trusted_head=lambda:verified_head(data,pack/'public.pem'))
            observed=admission.verify_plan(order)
            if observed['provider_verified'] is not False:raise RuntimeError('unexpected-provider-authority')
            return observed
        measure('native-plan-preflight-only-NOT-context-admission',preflight)
        if digest(proof_path)!=proof_hash:raise RuntimeError('proof-mutated')
        report['signature_to_component_finish_seconds']=time.perf_counter()-signature_tick
        # Negative cases run the actual sealed fixture wrapper and native
        # verifier. No substituted verifier/API, production key, or real pack.
        refusal_rows=[];report['wrapper_refusals']=refusal_rows
        def refuse(name,expected,*extra):
            before_head=verified_head(data,pack/'public.pem')
            before_hash=digest(proof_path)
            def exercise():
                result=subprocess.run(['pwsh','-NoProfile','-NonInteractive','-File',str(rendered),
                    '-Manifest',str(manifest_path),*map(str,extra)],capture_output=True,text=True,timeout=300)
                text=result.stdout+'\n'+result.stderr
                if result.returncode==0 or expected not in text:
                    raise RuntimeError('expected-wrapper-refusal-not-observed:'+name)
                # Do not retain arbitrary command output or credential-bearing
                # exceptions. Only the fixed expected marker and return code.
                refusal_rows.append(dict(case=name,expected_marker=expected,returncode=result.returncode))
            measure('wrapper-refusal-'+name,exercise)
            if digest(proof_path)!=before_hash or verified_head(data,pack/'public.pem')!=before_head:
                raise RuntimeError('read-only-refusal-mutated-originals:'+name)
        # Positive read-only VerifyExport covers the second supported operator
        # entry and nested Boolean summary without another login/export.
        before_verify_head=verified_head(data,pack/'public.pem')
        measure('actual-wrapper-read-only-verify',lambda:stage('VerifyExport','-Proof',proof_path))
        if verified_head(data,pack/'public.pem')!=before_verify_head:
            raise RuntimeError('read-only-verification-mutated-head')
        bare=output/'bare-event-negative.json';write(bare,canonical(event))
        refuse('bare-event','Bare events are not proof bundles.',
               '-Stage','VerifyExport','-Proof',bare)
        malformed=output/'malformed-negative.json';write(malformed,b'{')
        refuse('malformed-json','ConvertFrom-Json','-Stage','VerifyExport','-Proof',malformed)
        tampered=json.loads(proof_path.read_bytes())
        signature=tampered['journal']['signature']['value']
        if type(signature) is not str or not signature:
            raise RuntimeError('native-journal-signature-format-changed')
        tampered['journal']['signature']['value']=('A' if signature[0]!='A' else 'B')+signature[1:]
        bad_signature=output/'signature-negative.json';write(bad_signature,canonical(tampered))
        refuse('journal-signature','Native command refused',
               '-Stage','VerifyExport','-Proof',bad_signature)
        refuse('duplicate-export','Export already exists; stop, do not overwrite or retry.',
               '-Stage','ExportAndVerify','-Proof',proof_path,
               '-CredentialFile',credential_path,'-DecisionSha256',event['content_sha256'])
        # Positive component latency is captured before deliberate negative
        # stale-head and expiry waits. None is complete admission readiness.
        report['positive_component_sample_count']=1
        # Keep the checkout at the exact executable for stale-head verification:
        # local publication is in a different fixture clone, not this source.
        service.login(credential_path.read_text().strip())
        refuse('stale-journal-head','Native command refused',
               '-Stage','VerifyExport','-Proof',proof_path)
        def wait_for_fixture_expiry():
            delay=(sign_end-datetime.now(timezone.utc)).total_seconds()
            if delay>0:time.sleep(delay+0.1)
        measure('deliberate-negative-expiry-wait-NOT-proof-tail',wait_for_fixture_expiry)
        refuse('expired-signing-window','Outside reviewed signing/verification window. Stop.',
               '-Stage','VerifyExport','-Proof',proof_path)
        report['operator_component_passed']=True
        report['sample_count']=1
        report['full_route_passed']=False
        report['real_pack_ready']=False
        return 0
    finally:
        report['total_component_elapsed_seconds']=time.perf_counter()-started
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        if http is not None:http.shutdown();http.server_close()
        if service is not None:service.close()
        write(report_path,canonical(report))
        # Upload ONLY this timing report. No credentials, private key, authority
        # folder, data snapshot, proof bundle, session material or fixture tree.

if __name__=='__main__':
    raise SystemExit(main())
