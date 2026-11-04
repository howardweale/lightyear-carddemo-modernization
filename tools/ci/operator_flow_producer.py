"""CI-only native public-fixture producer proposal; not full rehearsal.

Exercises disposable signing, raw HTTP export, native journal/decision checks,
independent public handoff at actual E. Does NOT exercise remote
publication, global nonce admission, OCI/controller admission or model calls.
A passing component cannot release any real signing pack.
"""
import hashlib,json,os,shutil,subprocess,sys,threading,time,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tools.ci.operator_flow_native_inputs import live_producer_identity,prepare_native_documents
from tools.ci.operator_flow_ci_prerequisite import require_prior_component
from tools.ci.operator_flow_producer_pr import read_approval
from tools.ci.operator_flow_candidate import verify_candidate
from tools.ci.operator_flow_metadata import PREFIX
from tools.ci.operator_flow_tree_guards import current_main,check_tree_composition

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
    approval=read_approval()
    executable=approval['executable']
    producer=live_producer_identity(source,executable,approval=approval)
    validation_run=str(approval['validation_run_id'])
    prior_ci=require_prior_component(executable,producer['run_id'],validation_run)
    expected_main=current_main(approval['expected_main'])
    metadata=source/'.git'
    if (not metadata.is_dir() or metadata.is_symlink() or metadata.is_junction()
            or (metadata/'commondir').exists() or (metadata/'objects/info/alternates').exists()
            or (metadata/'objects/info/http-alternates').exists()):
        raise SystemExit('producer-independent-source-required')
    handoff=temporary/'operator-flow-public-handoff'
    if handoff.exists():raise SystemExit('producer-handoff-already-exists')
    base=temporary/('operator-native-producer-'+uuid.uuid4().hex);base.mkdir()
    repo=base/'repository'
    candidate_root=base/'metadata-verification'
    candidate_trust=base/'candidate-public-trust'
    # Freeze commit identity inputs before signing, not from proof timestamps.
    commit_epoch=int(datetime.now(timezone.utc).timestamp())
    runtime=base/'runtime';data=base/'factory';data.mkdir()
    pack=base/'fixture-inputs';pack.mkdir()
    output=base/'operator-output'
    report_path=temporary/'operator-flow-producer-timings.json'
    if report_path.exists():raise SystemExit('component-report-already-exists')
    stages=[];service=None;http=None;started=time.perf_counter()
    report={'fixture_only':True,'full_route_passed':False,'real_pack_ready':False,
        'prior_component_ci':prior_ci,'sample_count':0,'remote_publication_measured':False,'nonce_admission_measured':False,
        'complete_signature_to_execution_ready_minutes':None,'stages':stages,
        'omitted':['remote publication and final guards','global nonce and OCI/controller admission',
                   'full admission/remote failure matrix','CI queue/setup and real human decision time']}
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
        from tools.factory_install.journal_head import verified_head
        def prepare_static():
            # Independent no-hardlinks checkout at the actual published E.
            # No synthetic repository, fabricated inputs or local executable commit.
            command(['git','clone','--no-hardlinks',str(source),str(repo)])
            git(repo,'checkout','--detach',executable)
            if git(repo,'rev-parse','HEAD')!=executable or git(repo,'status','--porcelain=v1','--untracked-files=all'):
                raise RuntimeError('producer-independent-E-changed')
            command(['git','-c','core.autocrlf=false','clone','--no-hardlinks',str(source),str(candidate_root)])
            git(candidate_root,'config','core.autocrlf','false')
            git(candidate_root,'checkout','--detach',executable)
            if git(candidate_root,'status','--porcelain=v1','--untracked-files=all'):
                raise RuntimeError('candidate-preparation-dirty-E')
            report['presign_tree_observation']=check_tree_composition(candidate_root,executable,executable,expected_main)
            candidate_trust.mkdir()
            runtime.mkdir()
            shutil.copytree(Path(sys.base_prefix),runtime/'python',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            app=runtime/'app';app.mkdir()
            for name in ('src','tools'):shutil.copytree(repo/name,app/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            inventory=[{'path':str(p),'sha256':digest(p)} for p in sorted(app.rglob('*')) if p.is_file()]
            write(pack/'runtime-inventory.json',canonical({'complete':True,'files':inventory}))
        measure('non-proof-static-preparation',prepare_static)
        if live_producer_identity(source,executable,approval=approval)!=producer:
            raise RuntimeError('producer-changed-before-fixture-keys')
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
        nonce_sha256=hashlib.sha256(('disposable-operator-rehearsal:'+str(uuid.uuid4())).encode()).hexdigest()
        unsigned=measure('native-unsigned-public-fixture',lambda:prepare_native_documents(repo,executable,
            {'start':sign_start.isoformat(),'end':end.isoformat()},nonce_sha256))
        for name,raw in unsigned.items():write(pack/name,raw)
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
            if live_producer_identity(source,executable,approval=approval)!=producer:
                raise RuntimeError('producer-changed-before-decision')
            if require_prior_component(executable,producer['run_id'],validation_run)!=prior_ci:
                raise RuntimeError('prior-component-ci-changed')
            current_main(expected_main)
            if not sign_start<=datetime.now(timezone.utc)<sign_end:
                raise RuntimeError('prior-ci-recheck-overran-signing-window')
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
        current_head=verified_head(data,pack/'public.pem')
        write(candidate_trust/'public.pem',(pack/'public.pem').read_bytes())
        write(candidate_trust/'trust.json',canonical(dict(scope='factory',public_key='public.pem',journal_head_sha256=current_head)))
        metadata={PREFIX+'plan.json':(pack/'plan.json').read_bytes(),
                  PREFIX+'contract.json':(pack/'contract.json').read_bytes(),PREFIX+'proof.json':proof_path.read_bytes()}
        candidate=measure('metadata-finalization-and-native-candidate-verification',
            lambda:verify_candidate(candidate_root,executable,metadata,commit_epoch,candidate_trust/'trust.json'))
        if (candidate['decision_sha256']!=event['content_sha256'] or candidate['nonce_sha256']!=nonce_sha256
                or candidate['journal_head_sha256']!=current_head
                or verified_head(data,pack/'public.pem')!=current_head or digest(proof_path)!=proof_hash):
            raise RuntimeError('candidate-original-proof-trust-or-case-changed')
        report['metadata_candidate']=candidate
        report['candidate_tree_observation']=measure('candidate-full-tree-and-actual-main-merge',
            lambda:check_tree_composition(candidate_root,executable,candidate['commit'],expected_main,metadata))
        current_main(expected_main)

        if live_producer_identity(source,executable,approval=approval)!=producer:
            raise RuntimeError('producer-identity-changed')
        if git(repo,'rev-parse','HEAD')!=executable or git(repo,'status','--porcelain=v1','--untracked-files=all'):
            raise RuntimeError('producer-E-mutated')
        # This is public producer evidence, NOT independent authority by itself.
        # Consumer must authenticate original producer run/workflow/E/artifact.
        handoff.mkdir()
        for name,path in (('plan.json',pack/'plan.json'),('contract.json',pack/'contract.json'),
                          ('proof.json',proof_path),('public.pem',pack/'public.pem')):
            write(handoff/name,path.read_bytes())
        write(handoff/'trust.json',canonical(dict(scope='factory',public_key='public.pem',journal_head_sha256=current_head)))
        if verified_head(data,pack/'public.pem')!=current_head or digest(proof_path)!=proof_hash:
            raise RuntimeError('producer-original-trust-or-proof-changed')
        report.update(producer=producer,fixture_only=True,producer_stage_passed=True,
            consumer_workflow='.github/workflows/operator-flow-consumer.yml',
            decision_sha256=event['content_sha256'],nonce_sha256=nonce_sha256,
            public_handoff_hashes={p.name:digest(p) for p in sorted(handoff.iterdir())},
            signature_to_public_handoff_seconds=time.perf_counter()-signature_tick,
            sample_count=0,full_route_passed=False,real_pack_ready=False)
        write(handoff/'producer.json',canonical(report))
        return 0
    finally:
        report['total_component_elapsed_seconds']=time.perf_counter()-started
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        if http is not None:http.shutdown();http.server_close()
        if service is not None:service.close()
        write(report_path,canonical(report))
        # Proposed upload is the explicit public handoff allowlist plus timings.
        # Never upload runtime, authority, private key, credentials or data tree.

if __name__=='__main__':
    raise SystemExit(main())
