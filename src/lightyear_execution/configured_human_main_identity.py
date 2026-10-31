"""Read-only proposed main-job identity; no reservation, lease or signing.

The existing PR-only reservation and main-only signer are unchanged. This
cannot create a context or resume a nonce. It is not wired to dispatch. A separate main
reservation proposal shares the existing nonce namespace; no dispatch opts in.
"""
import os,re
from lightyear_execution.contracts import ExecutionContractError

REPOSITORY='howardweale/lightyear-carddemo-modernization'
WORKFLOW='.github/workflows/p5-configured-human-main.yml'
JOB='configured-build-control'
PREFIX='/repos/'+REPOSITORY


def _validate_main_identity(binding,head,environment,run,workflow,jobs,main_ref):
    # Pure relationship validation. Synthetic input here grants no authority.
    ci=binding.get('ci',{})
    run_id=environment.get('GITHUB_RUN_ID','')
    if (type(head) is not str or not re.fullmatch('[0-9a-f]{40}',head)
            or environment.get('GITHUB_ACTIONS')!='true'
            or environment.get('GITHUB_REPOSITORY')!=REPOSITORY
            or environment.get('GITHUB_REF')!='refs/heads/main'
            or environment.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
            or environment.get('GITHUB_SHA')!=head
            or environment.get('GITHUB_WORKFLOW_SHA')!=head
            or environment.get('GITHUB_WORKFLOW_REF')!=REPOSITORY+'/'+WORKFLOW+'@refs/heads/main'
            or environment.get('GITHUB_RUN_ATTEMPT')!='1'
            or environment.get('GITHUB_JOB')!=JOB
            or type(run_id) is not str or not re.fullmatch('[1-9][0-9]{0,19}',run_id)
            or ci.get('repository')!=REPOSITORY or ci.get('job')!=JOB
            or type(ci.get('run_attempt')) is not int or ci['run_attempt']!=1
            or type(ci.get('workflow_ref')) is not str
            or not re.fullmatch(re.escape(REPOSITORY+'/'+WORKFLOW+'@')+'[0-9a-f]{40}',ci['workflow_ref'])):
        raise ExecutionContractError('configured-main-exact-environment-required')
    if (type(run.get('id')) is not int or str(run['id'])!=run_id
            or type(run.get('run_attempt')) is not int or run['run_attempt']!=1
            or run.get('event')!='workflow_dispatch' or run.get('status')!='in_progress'
            or run.get('head_sha')!=head or run.get('head_branch')!='main'
            or run.get('head_repository',{}).get('full_name')!=REPOSITORY
            or type(run.get('workflow_id')) is not int or run['workflow_id']<=0
            or type(workflow.get('id')) is not int or workflow['id']!=run['workflow_id']
            or workflow.get('path')!=WORKFLOW or workflow.get('state')!='active'
            or main_ref.get('ref')!='refs/heads/main'
            or main_ref.get('object',{}).get('type')!='commit'
            or main_ref['object'].get('sha')!=head):
        raise ExecutionContractError('configured-main-live-run-workflow-ref-required')
    rows=jobs.get('jobs')
    if (type(rows) is not list or type(jobs.get('total_count')) is not int
            or jobs['total_count']!=len(rows) or len(rows)>100
            or any(type(row) is not dict for row in rows)):
        raise ExecutionContractError('configured-main-complete-job-list-required')
    matches=[row for row in rows if row.get('name')==JOB]
    if len(matches)!=1:raise ExecutionContractError('configured-main-unique-job-required')
    job=matches[0]
    if (type(job.get('id')) is not int or job['id']<=0
            or job.get('status')!='in_progress' or job.get('head_sha')!=head
            or type(job.get('run_id')) is not int or str(job['run_id'])!=run_id
            or ('run_attempt' in job and (type(job['run_attempt']) is not int or job['run_attempt']!=1))):
        raise ExecutionContractError('configured-main-live-job-required')
    # Existing consumption-record CI shape; this mapping is NOT consumption.
    return dict(repository=REPOSITORY,run_id=int(run_id),run_attempt=1,job=JOB,
        job_id=job['id'],workflow_id=run['workflow_id'],workflow_ref=ci['workflow_ref'],head_sha=head)


def _read_main_ci_identity(binding,head,api,environment):
    # Internal synthetic-API test boundary; not a public admission entry.
    run_id=environment.get('GITHUB_RUN_ID','')
    if type(run_id) is not str or not re.fullmatch('[1-9][0-9]{0,19}',run_id):
        raise ExecutionContractError('configured-main-run-id-required')
    run=api.request('GET',PREFIX+'/actions/runs/'+run_id)
    workflow_id=run.get('workflow_id')
    if type(workflow_id) is not int or workflow_id<=0:
        raise ExecutionContractError('configured-main-workflow-id-required')
    workflow=api.request('GET',PREFIX+'/actions/workflows/'+str(workflow_id))
    jobs=api.request('GET',PREFIX+'/actions/runs/'+run_id+'/attempts/1/jobs?per_page=100')
    main=api.request('GET',PREFIX+'/git/ref/heads/main')
    identity=_validate_main_identity(binding,head,environment,run,workflow,jobs,main)
    if api.request('GET',PREFIX+'/git/ref/heads/main')!=main:
        raise ExecutionContractError('configured-main-ref-advanced')
    return identity


def _main_environment():
    return {name:os.environ.get(name,'') for name in (
        'GITHUB_ACTIONS','GITHUB_REPOSITORY','GITHUB_REF','GITHUB_EVENT_NAME','GITHUB_SHA',
        'GITHUB_WORKFLOW_SHA','GITHUB_WORKFLOW_REF','GITHUB_RUN_ATTEMPT','GITHUB_RUN_ID','GITHUB_JOB')}


def review_configured_main_identity(admission,order,policy):
    from .configured_human_admission import verify_configured_human_plan
    from .tower_drill_context import _workflow_source
    from .tower_drill_reservation import _GitHubAPI
    review=verify_configured_human_plan(admission,order,policy)
    environment=_main_environment()
    # Current verified HEAD may contain only the permitted proof metadata delta
    # from the original signed executable. Preserve both revisions unchanged.
    head=review['verified_model_admission']['executable_commit']
    identity=_read_main_ci_identity(review['drill_binding'],head,_GitHubAPI(),environment)
    source=_workflow_source(admission.root,review,environment)
    if (_main_environment()!=environment or verify_configured_human_plan(admission,order,policy)!=review):
        raise ExecutionContractError('configured-main-fresh-binding-changed')
    return dict(identity=identity,workflow_source=source,execution_authorized=False,
        nonce_consumed=False,secrets_leased=False,signing_authorized=False)
