"""Proposed disposable native consumer, gated by exact external fixture approval.

Never adopt expectations from the proof or producer report. No fake API,
context registration, verifier replacement, retry, or old-nonce resumption.
The approved fixture uses the unchanged shared native tag namespace; enabling
this workflow requires explicit approval of that durable effect and exact nonce.
Successful native public-fixture execution is not strict case qualification.
"""
from datetime import datetime,timezone
from hashlib import sha256
import json,os,re,stat,subprocess,time
from pathlib import Path
from tools.ci.operator_flow_handoff import fetch_producer_handoff,strict_json,require,REPOSITORY

WORKFLOW='.github/workflows/operator-flow-consumer.yml'
METADATA={name:'docs/factory/p5-human-clean-control/'+name for name in
          ('plan.json','contract.json','proof.json')}
HASH_FIELDS={'plan_sha256','decision_sha256','journal_head_sha256','public_key_sha256','nonce_sha256','archive_sha256'}
APPROVAL_FIELDS=HASH_FIELDS|{'metadata_head','executable','producer_run_id','artifact_id',
                            'fixture_only','allow_shared_nonce_consumption'}

def parse_approval(raw):
    require(type(raw) is str and 0<len(raw.encode())<=8192,'consumer-exact-approval-required')
    row=strict_json(raw)
    require(type(row) is dict and set(row)==APPROVAL_FIELDS,'consumer-approval-fields')
    require(all(type(row[k]) is str and re.fullmatch('[0-9a-f]{64}',row[k]) for k in HASH_FIELDS)
        and all(type(row[k]) is str and re.fullmatch('[0-9a-f]{40}',row[k]) for k in ('metadata_head','executable')),
        'consumer-approval-hashes')
    require(row['metadata_head']!=row['executable'] and
        all(type(row[k]) is int and 0<row[k]<10**20 for k in ('producer_run_id','artifact_id')),
        'consumer-approval-identity')
    require(row['fixture_only'] is True and row['allow_shared_nonce_consumption'] is True,
        'consumer-explicit-fixture-tag-scope')
    return row

def git(root,*args):
    result=subprocess.run(['git','--no-optional-locks','-C',str(root),*args],capture_output=True,timeout=45)
    require(result.returncode==0,'consumer-git-refused')
    return result.stdout

def clean_root(root):
    require(root.is_absolute() and root.resolve(strict=True)==root,'consumer-source-absolute')
    for path in (root,*root.parents):
        info=path.lstat()
        require(not path.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400
            and 'onedrive' not in str(path).lower(),'consumer-source-path')
    require((root/'.git').is_dir() and not (root/'.git').is_symlink(),'consumer-independent-git')
    require(not (root/'.git/objects/info/alternates').exists(),'consumer-no-alternates')
    common=Path(git(root,'rev-parse','--git-common-dir').decode().strip())
    if not common.is_absolute():common=root/common
    require(common.resolve(strict=True)==(root/'.git').resolve(strict=True),'consumer-no-shared-git')
    require(not git(root,'status','--porcelain=v1','--untracked-files=all'),'consumer-clean-source')

def check_metadata(root,approval,files):
    from lightyear_factory.model_admission import _bounded_regular_bytes
    clean_root(root);head=approval['metadata_head'];executable=approval['executable']
    require(git(root,'rev-parse','HEAD').decode().strip()==head,'consumer-exact-M')
    require(git(root,'rev-list','--parents','-n','1',head).decode().split()==[head,executable],
        'consumer-single-metadata-parent-E')
    changed=git(root,'diff','--no-renames','--name-only','-z',executable,head).decode().split('\0')
    require(set(changed[:-1])==set(METADATA.values()) and changed[-1]=='','consumer-only-three-metadata-paths')
    for name,path in METADATA.items():
        original=_bounded_regular_bytes(root/path,2097152,'consumer-committed-metadata')
        require(original==files[name]==git(root,'show',head+':'+path),'consumer-byte-exact-published-handoff')

def check_public_expectations(approval,files):
    trust=strict_json(files['trust.json']);report=strict_json(files['producer.json'])
    require(trust==dict(scope='factory',public_key='public.pem',journal_head_sha256=approval['journal_head_sha256'])
        and sha256(files['public.pem']).hexdigest()==approval['public_key_sha256'],'consumer-independent-key-head')
    # These joins do not verify a signature. The native verifier below must pass.
    require(report.get('decision_sha256')==approval['decision_sha256']
        and report.get('nonce_sha256')==approval['nonce_sha256']
        and report.get('consumer_workflow')==WORKFLOW,'consumer-producer-exact-case')
    candidate=report.get('metadata_candidate')
    require(type(candidate) is dict and candidate.get('parent')==approval['executable']
        and candidate.get('commit')==approval['metadata_head'] and candidate.get('native_candidate_verified') is True
        and all(candidate.get(key)==approval[key] for key in ('plan_sha256','decision_sha256','journal_head_sha256','nonce_sha256')),
        'consumer-original-candidate-binding')
    # Provenance join only: independent approval and native verification remain mandatory.

def check_native_review(approval,review):
    verified=review['verified_model_admission'];binding=review['drill_binding']
    require(all(verified.get(field)==approval[expected] for field,expected in
        (('executable_commit','metadata_head'),('plan_sha256','plan_sha256'),
         ('decision_sha256','decision_sha256'),('trusted_journal_head','journal_head_sha256'))),
        'consumer-native-independent-bindings')
    require(binding['nonce_sha256']==approval['nonce_sha256'] and binding['case_id']=='human-clean-control'
        and binding['ci']==dict(repository=REPOSITORY,workflow_ref=REPOSITORY+'/'+WORKFLOW+'@'+approval['executable'],
                                job='operator-consumer',run_attempt=1),'consumer-native-exact-case-ci')

def write_new(path,raw):
    with path.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())

def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_EVENT_NAME')=='pull_request'
        and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY and os.environ.get('GITHUB_JOB')=='operator-consumer'
        and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','consumer-ci-only')
    approval=parse_approval(os.environ.get('OPERATOR_REHEARSAL_APPROVAL_JSON',''))
    root=Path.cwd();temp=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    require(not temp.is_relative_to(root.resolve(strict=True)),'consumer-external-evidence')
    report=dict(fixture_only=True,consumer_stage_passed=False,full_route_passed=False,real_pack_ready=False,
        sample_count=0,complete_route_minutes=None,metadata_head=approval['metadata_head'],
        executable=approval['executable'],approval_sha256=sha256(json.dumps(approval,sort_keys=True).encode()).hexdigest(),
        started_at=datetime.now(timezone.utc).isoformat(),stages=[])
    def measure(name,operation):
        start=datetime.now(timezone.utc).isoformat();tick=time.perf_counter()
        result=operation()
        report['stages'].append(dict(name=name,started_at=start,finished_at=datetime.now(timezone.utc).isoformat(),
                                    elapsed_seconds=time.perf_counter()-tick))
        return result
    try:
        expected={key:approval[key] for key in ('executable','producer_run_id','artifact_id','archive_sha256')}
        files,observed=measure('original-producer-handoff',lambda:fetch_producer_handoff(expected))
        check_public_expectations(approval,files)
        measure('exact-metadata-source',lambda:check_metadata(root,approval,files))
        trust_dir=temp/'operator-consumer-public-trust';trust_dir.mkdir()
        for name in ('public.pem','trust.json'):write_new(trust_dir/name,files[name])
        from lightyear_factory.contracts import WorkOrder
        from lightyear_factory.model_admission import FactoryModelAdmission
        from lightyear_execution.contracts import ExecutionPolicy
        from lightyear_execution.tower_drill_admission import verify_human_drill_plan
        from lightyear_execution.tower_drill_context import _workflow_source
        from lightyear_execution.tower_drill_reservation import _GitHubAPI,_ci_identity
        from tools.ci.p5_human_positive import main as original_positive
        trust=FactoryModelAdmission.from_external_trust(root,METADATA['plan.json'],
            METADATA['proof.json'],METADATA['contract.json'],trust_dir/'trust.json')
        order_path=root/'tests/fixtures/p5_public/human-clean-control/work-order.json'
        policy_path=root/'docs/factory/p5-human-clean-control/execution-policy.json'
        order=WorkOrder.load(order_path);policy=ExecutionPolicy.load(policy_path)
        review=measure('native-proof-chain-plan',lambda:verify_human_drill_plan(trust,order,policy))
        check_native_review(approval,review)
        report['workflow_source']=_workflow_source(root,review,os.environ)
        report['original_consumer']=_ci_identity(review['drill_binding'],approval['metadata_head'],_GitHubAPI(),os.environ)
        report['original_producer']=observed
        # Existing native positive entry repeats proof/runtime/public output/
        # isolation preflight, then calls the original CLI exactly once. The CLI
        # alone consumes and grants the original context; no synthesized receipt.
        runs=temp/'operator-consumer-evidence'
        require(not runs.exists(),'consumer-fresh-evidence-only')
        arguments=['--source-root',str(root),'--work-order',str(order_path),'--execution-policy',str(policy_path),
            '--factory-plan',METADATA['plan.json'],'--factory-contract',METADATA['contract.json'],
            '--factory-approval',METADATA['proof.json'],'--factory-trust',str(trust_dir/'trust.json'),
            '--public-output-plan','docs/factory/p5-human-clean-control/public-outputs.json',
            '--public-isolation-plan','docs/factory/p5-human-clean-control/public-isolation.json',
            '--runs-root',str(runs),'--execution-runtime','docker']
        # Persist the original intent before any admission call. Failure refuses.
        write_new(temp/'operator-consumer-intent.json',json.dumps(dict(metadata_head=approval['metadata_head'],
            nonce_sha256=approval['nonce_sha256'],consumer=report['original_consumer'],
            at=datetime.now(timezone.utc).isoformat()),sort_keys=True).encode())
        result=measure('original-native-public-admission-and-controller',lambda:original_positive(arguments))
        require(result==0,'consumer-original-positive-refused')
        require(verify_human_drill_plan(trust,order,policy)==review,'consumer-final-native-trust-changed')
        check_metadata(root,approval,files)
        report.update(consumer_stage_passed=True,positive_receipt_sha256=sha256((runs/'positive-ci.json').read_bytes()).hexdigest(),
            consumer_completed_at=datetime.now(timezone.utc).isoformat(),
            qualification='Public disposable fixture only; no strict real-case acceptance',
            timing_limit='Producer and consumer UTC observations are cross-run; no subtraction of independent monotonic clocks. '
                         'Publisher guards/queue/negative matrix and complete-route bound remain required.')
        return 0
    finally:
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        write_new(temp/'operator-flow-consumer-report.json',(json.dumps(report,sort_keys=True)+'\n').encode())

if __name__=='__main__':raise SystemExit(main())
