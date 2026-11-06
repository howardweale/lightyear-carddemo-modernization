"""CI-only local metadata preparation and original native publication review.

Both independent checkouts must start at E; external public trust is prepared.
Only the separate temporary checkout receives local metadata objects/files.
No caller API/verifier/clock, CLI, remote publisher, reservation or controller. Returned objects retain every
original false authority/readiness flag. Full publisher guards remain owed.
"""
import os,re
from pathlib import Path
from tools.ci.operator_flow_handoff import fetch_producer_handoff,_original_producer,REPOSITORY
from tools.ci.operator_flow_consumer import (clean_root,check_metadata,
    check_public_expectations,check_native_review,HASH_FIELDS)
from tools.ci.operator_flow_metadata import PREFIX,require
from tools.ci.operator_flow_publication_reconstruction import reconstruct_publication_objects


REVIEW_WORKFLOW='.github/workflows/operator-flow-publication-review.yml'
REVIEW_JOB='operator-publication-review'
REVIEW_LABEL='operator-rehearsal-publication-review'


def _reviewer_relationships(event,run,workflow,listing,live,executable,run_id,merge):
    # Untrusted record relationships only. The public reader constructs the
    # original GET-only API and obtains these records itself.
    require(type(event) is dict and event.get('action')=='labeled'
        and event.get('label',{}).get('name')==REVIEW_LABEL
        and event.get('repository',{}).get('full_name')==REPOSITORY,'reviewer-event')
    number=event.get('number');pr=event.get('pull_request')
    require(type(number) is int and 0<number<10**20
        and type(run_id) is int and 0<run_id<10**20
        and all(type(x) is str and re.fullmatch('[0-9a-f]{40}',x) for x in (executable,merge)),
        'reviewer-expectations')
    bases=[]
    for value in (pr,live):
        require(type(value) is dict and type(value.get('number')) is int and value['number']==number
            and value.get('state')=='open' and value.get('head',{}).get('sha')==executable
            and value.get('head',{}).get('repo',{}).get('full_name')==REPOSITORY
            and value.get('base',{}).get('repo',{}).get('full_name')==REPOSITORY
            and value.get('base',{}).get('ref')=='main'
            and value.get('merge_commit_sha')==merge,'reviewer-current-pr')
        base=value['base'].get('sha')
        require(type(base) is str and re.fullmatch('[0-9a-f]{40}',base),'reviewer-base')
        bases.append(base)
    require(bases[0]==bases[1],'reviewer-base-changed')
    require(type(run) is dict and type(run.get('id')) is int and run['id']==run_id
        and run.get('event')=='pull_request' and run.get('status')=='in_progress'
        and type(run.get('run_attempt')) is int and run['run_attempt']==1
        and run.get('head_sha')==executable
        and run.get('repository',{}).get('full_name')==REPOSITORY
        and run.get('head_repository',{}).get('full_name')==REPOSITORY
        and type(run.get('workflow_id')) is int and run['workflow_id']>0,'reviewer-original-run')
    require(type(workflow) is dict and type(workflow.get('id')) is int
        and workflow['id']==run['workflow_id'] and workflow.get('path')==REVIEW_WORKFLOW,
        'reviewer-original-workflow')
    require(type(listing) is dict and type(listing.get('jobs')) is list
        and type(listing.get('total_count')) is int and listing['total_count']==len(listing['jobs'])==1,
        'reviewer-complete-single-job')
    job=listing['jobs'][0]
    require(type(job) is dict and type(job.get('id')) is int and job['id']>0
        and type(job.get('run_id')) is int and job['run_id']==run_id
        and job.get('head_sha')==executable and job.get('name')==REVIEW_JOB
        and job.get('status')=='in_progress'
        and ('run_attempt' not in job or type(job['run_attempt']) is int and job['run_attempt']==1),
        'reviewer-original-job')
    return dict(pr=number,run=run_id,job=job['id'],workflow=workflow['id'],
        executable=executable,tested_merge=merge,base=bases[0])


def _review_current_identity(root,executable):
    from hashlib import sha256
    from lightyear_factory.model_admission import _bounded_regular_bytes
    from lightyear_execution.tower_drill_reservation import _GitHubAPI
    from tools.ci.operator_flow_consumer import git
    from tools.ci.operator_flow_handoff import strict_json
    env=os.environ
    require(env.get('GITHUB_ACTIONS')=='true' and env.get('GITHUB_REPOSITORY')==REPOSITORY
        and env.get('GITHUB_EVENT_NAME')=='pull_request' and env.get('GITHUB_JOB')==REVIEW_JOB
        and env.get('GITHUB_RUN_ATTEMPT')=='1' and env.get('RUNNER_ENVIRONMENT')=='github-hosted',
        'reviewer-ci-only')
    run_text=env.get('GITHUB_RUN_ID','');merge=env.get('GITHUB_SHA','');revision=env.get('GITHUB_WORKFLOW_SHA','')
    require(re.fullmatch('[1-9][0-9]{0,19}',run_text)
        and all(re.fullmatch('[0-9a-f]{40}',v) for v in (executable,merge,revision)),'reviewer-ci-shapes')
    require(Path(env.get('GITHUB_WORKSPACE','')).resolve(strict=True)==root,'reviewer-original-checkout')
    event_path=Path(env.get('GITHUB_EVENT_PATH',''))
    require(event_path.is_absolute(),'reviewer-event-path')
    raw=_bounded_regular_bytes(event_path,1048576,'reviewer-event-file');event=strict_json(raw)
    number=event.get('number')
    require(type(number) is int and 0<number<10**20,'reviewer-pr-number')
    ref='refs/pull/'+str(number)+'/merge'
    require(env.get('GITHUB_REF')==ref and env.get('GITHUB_WORKFLOW_REF')==REPOSITORY+'/'+REVIEW_WORKFLOW+'@'+ref,
        'reviewer-original-workflow-ref')
    clean_root(root)
    require(git(root,'rev-parse','HEAD').decode().strip()==executable,'reviewer-source-E')
    api=_GitHubAPI();prefix='/repos/'+REPOSITORY
    run=api.request('GET',prefix+'/actions/runs/'+run_text)
    require(type(run.get('workflow_id')) is int and run['workflow_id']>0,'reviewer-workflow-id')
    workflow=api.request('GET',prefix+'/actions/workflows/'+str(run['workflow_id']))
    listing=api.request('GET',prefix+'/actions/runs/'+run_text+'/attempts/1/jobs?per_page=100')
    live=api.request('GET',prefix+'/pulls/'+str(number))
    observed=_reviewer_relationships(event,run,workflow,listing,live,executable,int(run_text),merge)
    require(git(root,'rev-list','--parents','-n','1',merge).decode().split()==[merge,observed['base'],executable],
        'reviewer-tested-merge-parents')
    def workflow_bytes(commit):
        ref=commit+':'+REVIEW_WORKFLOW;size=git(root,'cat-file','-s',ref).decode().strip()
        require(re.fullmatch('[1-9][0-9]{0,6}',size) and int(size)<=262144,'reviewer-workflow-size')
        value=git(root,'show',ref)
        require(len(value)==int(size),'reviewer-workflow-bytes')
        return value
    original=workflow_bytes(executable)
    require(workflow_bytes(revision)==original and workflow_bytes(merge)==original,
        'reviewer-runner-workflow-mismatch')
    require(_bounded_regular_bytes(event_path,1048576,'reviewer-event-file')==raw,'reviewer-event-changed')
    clean_root(root)
    require(git(root,'rev-parse','HEAD').decode().strip()==executable,'reviewer-source-changed')
    return dict(observed,workflow_revision=revision,workflow_sha256=sha256(original).hexdigest(),
        event_sha256=sha256(raw).hexdigest())


def _materialize_review_checkout(executable_root,metadata_root,files,*,executable,metadata_head,commit_epoch):
    """Local disposable checkout primitive; no proof or publication authority.

    Production invokes this only after original current reviewer/producer
    observations. Inert component bytes may exercise it without becoming proof.
    Failure leaves the one-shot intent and partial clone; never retry or repair.
    """
    from tools.ci.operator_flow_consumer import git,METADATA
    from tools.ci.operator_flow_metadata import prepare_candidate
    require(os.environ.get('GITHUB_ACTIONS')=='true','review-checkout-ci-only')
    executable_root=Path(executable_root);metadata_root=Path(metadata_root)
    temporary=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    require(metadata_root.is_absolute() and metadata_root.resolve(strict=True)==metadata_root
        and metadata_root!=temporary and metadata_root.is_relative_to(temporary)
        and not metadata_root.is_relative_to(executable_root)
        and not executable_root.is_relative_to(metadata_root),'review-checkout-separate-temporary')
    clean_root(executable_root);clean_root(metadata_root)
    require(git(executable_root,'rev-parse','HEAD').decode().strip()==executable
        and git(metadata_root,'rev-parse','HEAD').decode().strip()==executable,'review-checkout-exact-E')
    require(git(metadata_root,'rev-parse','--abbrev-ref','HEAD').decode().strip()=='HEAD'
        and git(metadata_root,'config','--get','core.autocrlf').decode().strip()=='false',
        'review-checkout-prepared-detached')
    intent=metadata_root/'.git/operator-review-materialization-intent.txt'
    hooks=metadata_root/'.git/operator-review-empty-hooks'
    require(not intent.exists() and not hooks.exists(),'review-checkout-one-shot')
    metadata={path:files[name] for name,path in METADATA.items()}
    # The unchanged original builder checks exact clean E, independent Git,
    # fixed new paths and complete object construction without writing objects.
    candidate=prepare_candidate(metadata_root,executable,metadata,commit_epoch)
    require(candidate['commit']==metadata_head,'review-checkout-exact-M')
    for path in (metadata_root/'.git').rglob('*'):
        require(not path.is_symlink() and not getattr(path.lstat(),'st_file_attributes',0)&0x400,
            'review-checkout-metadata-reparse')
        if path.is_file():require(path.stat().st_nlink==1,'review-checkout-no-hardlinked-metadata')
    # No new authority schema; fixed text is a local non-reusable intent only.
    text=('DISPOSABLE LOCAL METADATA PREPARATION; NO AUTHORITY\nE='+executable+'\nM='+metadata_head+'\n').encode()
    with intent.open('xb') as stream:stream.write(text);stream.flush();os.fsync(stream.fileno())
    hooks.mkdir()
    import subprocess
    for oid,(kind,body) in candidate['objects'].items():
        result=subprocess.run(['git','--no-optional-locks','-C',str(metadata_root),'-c','core.hooksPath='+str(hooks),
            'hash-object','-w','-t',kind,'--stdin'],input=body,capture_output=True,timeout=45)
        require(result.returncode==0 and result.stdout.decode().strip()==oid,'review-checkout-object-readback')
    # Only three fixed NEW files. No checkout, filter, hook, remote or branch
    # command is used. Original E files stay in place byte-for-byte.
    for relative,body in metadata.items():
        path=metadata_root/relative
        require(path.parent.is_dir() and not path.exists()
            and all(not p.is_symlink() and not getattr(p.lstat(),'st_file_attributes',0)&0x400
                for p in (path.parent,*path.parent.parents)),'review-checkout-new-metadata-path')
        with path.open('xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
    require(not list(hooks.iterdir()) and not hooks.is_symlink(),'review-checkout-empty-hooks')
    git(metadata_root,'-c','core.hooksPath='+str(hooks),'read-tree',metadata_head)
    git(metadata_root,'-c','core.hooksPath='+str(hooks),'update-ref','--no-deref','HEAD',metadata_head,executable)
    check_metadata(metadata_root,dict(metadata_head=metadata_head,executable=executable),files)
    require(git(metadata_root,'rev-parse','--abbrev-ref','HEAD').decode().strip()=='HEAD'
        and intent.read_bytes()==text,'review-checkout-final-intent')
    clean_root(executable_root)
    require(git(executable_root,'rev-parse','HEAD').decode().strip()==executable,'review-checkout-source-changed')
    return candidate


def _independent_expectations(*,executable,metadata_head,producer_run_id,artifact_id,
        archive_sha256,plan_sha256,decision_sha256,journal_head_sha256,public_key_sha256,
        nonce_sha256,commit_epoch):
    # Internal function arguments, not a new serialized approval or variable.
    values=dict(executable=executable,metadata_head=metadata_head,producer_run_id=producer_run_id,
        artifact_id=artifact_id,archive_sha256=archive_sha256,plan_sha256=plan_sha256,
        decision_sha256=decision_sha256,journal_head_sha256=journal_head_sha256,
        public_key_sha256=public_key_sha256,nonce_sha256=nonce_sha256)
    require(all(type(values[k]) is str and re.fullmatch('[0-9a-f]{64}',values[k]) for k in HASH_FIELDS)
        and all(type(v) is str and re.fullmatch('[0-9a-f]{40}',v) for v in (executable,metadata_head))
        and executable!=metadata_head,'publication-review-independent-hashes')
    require(all(type(v) is int and 0<v<10**20 for v in (producer_run_id,artifact_id))
        and type(commit_epoch) is int and 1<=commit_epoch<10**11,'publication-review-independent-identities')
    return values


def _prepared_trust(executable_root,metadata_root,trust_path,files):
    from lightyear_factory.model_admission import _bounded_regular_bytes
    trust_path=Path(trust_path)
    require(trust_path.is_absolute() and trust_path.resolve(strict=True)==trust_path
        and trust_path.name=='trust.json','publication-review-prepared-trust-path')
    for name in ('trust.json','public.pem'):
        path=trust_path.parent/name
        require(not any(path==root or path.is_relative_to(root) for root in (executable_root,metadata_root)),
            'publication-review-external-trust')
        require(_bounded_regular_bytes(path,65536,'publication-review-trust-bytes')==files[name],
            'publication-review-prepared-trust-mismatch')


def review_publication(executable_root,metadata_root,trust_path,*,executable,metadata_head,
        producer_run_id,artifact_id,archive_sha256,plan_sha256,decision_sha256,journal_head_sha256,
        public_key_sha256,nonce_sha256,commit_epoch):
    require(os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY,'publication-review-ci-only')
    expected=_independent_expectations(executable=executable,metadata_head=metadata_head,
        producer_run_id=producer_run_id,artifact_id=artifact_id,archive_sha256=archive_sha256,
        plan_sha256=plan_sha256,decision_sha256=decision_sha256,journal_head_sha256=journal_head_sha256,
        public_key_sha256=public_key_sha256,nonce_sha256=nonce_sha256,commit_epoch=commit_epoch)
    executable_root=Path(executable_root);metadata_root=Path(metadata_root)
    clean_root(executable_root);clean_root(metadata_root)
    require(not executable_root.is_relative_to(metadata_root) and not metadata_root.is_relative_to(executable_root),
        'publication-review-separate-checkouts')
    for root in (executable_root,metadata_root):
        require(not (root/'.git/commondir').exists() and not (root/'.git/objects/info/http-alternates').exists(),
            'publication-review-independent-checkouts')
    from lightyear_factory.contracts import WorkOrder
    from lightyear_factory.model_admission import FactoryModelAdmission
    from lightyear_execution.contracts import ExecutionPolicy
    from lightyear_execution.tower_drill_admission import verify_human_drill_plan
    from lightyear_execution.tower_drill_reservation import _GitHubAPI
    from tools.ci.operator_flow_review_source import check_review_source
    source_observation=check_review_source(executable_root,executable)
    reviewer_observation=_review_current_identity(executable_root,executable)
    handoff={key:expected[key] for key in ('executable','producer_run_id','artifact_id','archive_sha256')}
    files,observed=fetch_producer_handoff(handoff)
    check_public_expectations(expected,files)
    _prepared_trust(executable_root,metadata_root,trust_path,files)
    candidate,requests=reconstruct_publication_objects(executable_root,files,
        expected_executable=executable,expected_candidate=metadata_head,commit_epoch=commit_epoch)
    require(_materialize_review_checkout(executable_root,metadata_root,files,executable=executable,
        metadata_head=metadata_head,commit_epoch=commit_epoch)==candidate,'publication-review-prepared-candidate-mismatch')
    check_metadata(metadata_root,expected,files)
    order=WorkOrder.load(metadata_root/'tests/fixtures/p5_public/human-clean-control/work-order.json')
    policy=ExecutionPolicy.load(metadata_root/(PREFIX+'execution-policy.json'))
    admission=FactoryModelAdmission.from_external_trust(metadata_root,PREFIX+'plan.json',PREFIX+'proof.json',
        PREFIX+'contract.json',trust_path)
    review=verify_human_drill_plan(admission,order,policy)
    check_native_review(expected,review)
    plan=admission._committed_json(PREFIX+'plan.json')
    runtime=admission.verify_runtime(order,source_root=metadata_root,
        input_paths={key:metadata_root/row['path'] for key,row in plan['bound_inputs'].items()},policy=policy)
    require(plan['executable_commit']==executable and runtime['executable_commit']==metadata_head,
        'publication-review-native-E-M')
    # Do not download a second archive or re-enter admission. Reobserve original
    # producer metadata, original source bytes and current external trust only.
    require(_original_producer(_GitHubAPI(),handoff)==observed,'publication-review-producer-changed')
    check_metadata(metadata_root,expected,files)
    require(reconstruct_publication_objects(executable_root,files,expected_executable=executable,
        expected_candidate=metadata_head,commit_epoch=commit_epoch)==(candidate,requests),
        'publication-review-reconstruction-changed')
    _prepared_trust(executable_root,metadata_root,trust_path,files)
    require(verify_human_drill_plan(admission,order,policy)==review,'publication-review-native-trust-changed')
    # No current consumer run, nonce, full guards or publication permission is
    # inferred. Caller must perform fresh complete guards before any mutation.
    require(check_review_source(executable_root,executable)==source_observation,
        'publication-review-source-observation-changed')
    require(_review_current_identity(executable_root,executable)==reviewer_observation,
        'publication-review-current-identity-changed')
    return candidate,requests
