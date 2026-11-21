"""Original prior component-CI prerequisite; no signing or admission authority.

A successful component is necessary, never the full terminal/diagnosed CI,
publication-guard, approval, or complete rehearsal gate. No caller API accepted.
"""
from datetime import datetime,timezone
import os,re,subprocess
from pathlib import Path
from tools.ci.operator_flow_handoff import require,REPOSITORY
WORKFLOW='.github/workflows/operator-flow-component.yml'
REQUIRED_STEPS=('Verify exact component source before any tests',
    'Original subprocess download bounds and refusal checks',
    'Exact PR producer fixture and identity refusal checks',
    'Bounded public handoff byte and refusal checks','Exact consumer configuration refusal checks',
    'Original prior-CI prerequisite relationship checks',
    'Actual Git metadata construction and refusal checks',
    'Exact publication object serialization checks',
    'Original handoff metadata object reconstruction checks',
    'Prepared publication review public boundary checks',
    'Selected review module source checks',
    'Actual consumer Git metadata and untrusted candidate checks',
    'Actual full-tree and main merge refusal checks',
    'Actual wrapper and disposable native proof component','Recheck exact component source after component')

def component_source_guard():
    env=os.environ;expected=env.get('COMPONENT_EXECUTABLE','');revision=env.get('GITHUB_WORKFLOW_SHA','')
    require(env.get('GITHUB_ACTIONS')=='true' and env.get('GITHUB_REPOSITORY')==REPOSITORY
        and env.get('GITHUB_JOB')=='operator-component' and env.get('GITHUB_RUN_ATTEMPT')=='1'
        and env.get('GITHUB_EVENT_NAME') in ('pull_request','workflow_dispatch')
        and env.get('GITHUB_WORKFLOW_REF','').startswith(REPOSITORY+'/'+WORKFLOW+'@')
        and re.fullmatch('[0-9a-f]{40}',expected) and re.fullmatch('[0-9a-f]{40}',revision),
        'component-source-ci-identity')
    root=Path(env['GITHUB_WORKSPACE']).resolve(strict=True)
    def git(*args):
        return subprocess.check_output(['git','--no-optional-locks','-C',str(root),*args],stderr=subprocess.DEVNULL)
    require(git('rev-parse','HEAD').decode().strip()==expected
        and not git('status','--porcelain=v1','--untracked-files=all'),'component-exact-clean-source')
    expected_bytes=git('show',expected+':'+WORKFLOW)
    require(0<len(expected_bytes)<=262144 and git('show',revision+':'+WORKFLOW)==expected_bytes,
        'component-actual-workflow-source')

def _time(value):
    require(type(value) is str,'prior-ci-time-shape')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(result.tzinfo is not None and result.utcoffset().total_seconds()==0,'prior-ci-time-utc')
    return result

def validate_prior_component(executable,producer_id,validation_id,producer,run,workflow,listed,*,producer_event='workflow_dispatch'):
    # Pure record relationships only. Synthetic inputs to this helper cannot
    # establish service authenticity or a live execution context.
    # Dispatch default preserves old pure fixture assertions only. The live entry
    # below exclusively requests pull_request and accepts no caller event value.
    require(producer_event in ('workflow_dispatch','pull_request'),'prior-ci-producer-event')
    require(type(executable) is str and re.fullmatch('[0-9a-f]{40}',executable)
        and all(type(x) is int and 0<x<10**20 for x in (producer_id,validation_id))
        and producer_id!=validation_id,'prior-ci-expectations')
    require(type(producer.get('id')) is int and producer['id']==producer_id
        and producer.get('head_sha')==executable and producer.get('event')==producer_event
        and producer.get('status')=='in_progress' and type(producer.get('run_attempt')) is int
        and producer['run_attempt']==1 and producer.get('head_repository',{}).get('full_name')==REPOSITORY,
        'prior-ci-original-producer')
    require(type(run.get('id')) is int and run['id']==validation_id
        and run.get('head_sha')==executable and run.get('event') in ('pull_request','workflow_dispatch')
        and run.get('head_repository',{}).get('full_name')==REPOSITORY
        and type(run.get('run_attempt')) is int and run['run_attempt']==1
        and run.get('status')=='completed' and run.get('conclusion')=='success'
        and type(run.get('workflow_id')) is int and run['workflow_id']>0,'prior-ci-original-validation-run')
    require(workflow.get('path')==WORKFLOW and type(workflow.get('id')) is int
        and workflow['id']==run['workflow_id'],'prior-ci-original-workflow')
    rows=listed.get('jobs')
    require(type(rows) is list and type(listed.get('total_count')) is int
        and listed['total_count']==len(rows)==1,'prior-ci-complete-single-job')
    job=rows[0]
    require(type(job.get('id')) is int and job['id']>0 and job.get('name')=='operator-component'
        and type(job.get('run_id')) is int and job['run_id']==validation_id
        and job.get('head_sha')==executable and job.get('status')=='completed'
        and job.get('conclusion')=='success'
        and ('run_attempt' not in job or type(job['run_attempt']) is int and job['run_attempt']==1),
        'prior-ci-original-component-job')
    steps=job.get('steps')
    require(type(steps) is list and all(type(s) is dict for s in steps),'prior-ci-steps')
    for name in REQUIRED_STEPS:
        matches=[s for s in steps if s.get('name')==name]
        require(len(matches)==1 and matches[0].get('status')=='completed'
            and matches[0].get('conclusion')=='success','prior-ci-required-step')
    require(_time(run['created_at'])<=_time(job['started_at'])<=_time(job['completed_at'])
        <=_time(producer['created_at']),'prior-ci-must-precede-producer')
    return dict(repository=REPOSITORY,executable=executable,validation_run_id=validation_id,
        validation_run_attempt=1,validation_job_id=job['id'],workflow_id=run['workflow_id'],workflow_path=WORKFLOW,
        completed_at=job['completed_at'],required_steps=list(REQUIRED_STEPS))

def require_prior_component(executable,producer_id,validation_id):
    require(os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY
        and os.environ.get('GITHUB_JOB')=='operator-producer'
        and os.environ.get('GITHUB_EVENT_NAME')=='pull_request'
        and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','prior-ci-original-producer-environment')
    require(type(validation_id) is str and re.fullmatch('[1-9][0-9]{0,19}',validation_id)
        and type(producer_id) is int and producer_id>0,'prior-ci-run-input')
    validation_id=int(validation_id)
    from lightyear_execution.tower_drill_reservation import _GitHubAPI
    api=_GitHubAPI();prefix='/repos/'+REPOSITORY
    producer=api.request('GET',prefix+'/actions/runs/'+str(producer_id))
    run=api.request('GET',prefix+'/actions/runs/'+str(validation_id))
    require(type(run.get('workflow_id')) is int and run['workflow_id']>0,'prior-ci-workflow-id')
    workflow=api.request('GET',prefix+'/actions/workflows/'+str(run['workflow_id']))
    listed=api.request('GET',prefix+'/actions/runs/'+str(validation_id)+'/attempts/1/jobs?per_page=100')
    result=validate_prior_component(executable,producer_id,validation_id,producer,run,workflow,listed,producer_event='pull_request')
    again=api.request('GET',prefix+'/actions/runs/'+str(validation_id))
    require(all(again.get(k)==run.get(k) for k in
        ('id','head_sha','event','head_repository','run_attempt','status','conclusion','workflow_id','created_at')),
        'prior-ci-validation-run-changed')
    return result

if __name__=='__main__':component_source_guard()
