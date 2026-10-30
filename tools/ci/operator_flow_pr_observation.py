"""CI-only original PR identity observations. Never signing/admission authority.

No caller API or execution context is accepted. The pure relationship helper
checks untrusted records only; its success does not authenticate those records.
The proposed workflow has no signing, nonce or publication entry.
"""
import hashlib,os,re,subprocess
from pathlib import Path
from tools.ci.operator_flow_handoff import require,strict_json,REPOSITORY
WORKFLOW='.github/workflows/operator-flow-pr-observation.yml'
JOB='operator-pr-observation'
LABEL='operator-rehearsal-producer'

def relationships(event,run,job,live,head,run_id):
    require(type(event) is dict and event.get('action')=='labeled'
        and event.get('label',{}).get('name')==LABEL,'observation-event')
    require(type(head) is str and re.fullmatch('[0-9a-f]{40}',head)
        and type(run_id) is int and 0<run_id<10**20,'observation-expectations')
    pr=event.get('pull_request',{});number=event.get('number')
    require(type(number) is int and 0<number<10**20
        and pr.get('number')==number and type(pr.get('number')) is int
        and event.get('repository',{}).get('full_name')==REPOSITORY,'observation-pr-number')
    for value in (pr,live):
        require(type(value) is dict and type(value.get('number')) is int
            and value['number']==number and value.get('state')=='open'
            and value.get('head',{}).get('sha')==head
            and value.get('head',{}).get('repo',{}).get('full_name')==REPOSITORY
            and value.get('base',{}).get('repo',{}).get('full_name')==REPOSITORY,
            'observation-original-pr')
    require(type(run.get('id')) is int and run['id']==run_id
        and run.get('event')=='pull_request' and run.get('status')=='in_progress'
        and type(run.get('run_attempt')) is int and run['run_attempt']==1
        and run.get('head_repository',{}).get('full_name')==REPOSITORY
        and type(run.get('workflow_id')) is int and run['workflow_id']>0,'observation-original-run')
    # Native admission currently expects both service head fields to be E.
    # Observe/refuse a mismatch; never normalize a merge SHA to E or forge it.
    require(run.get('head_sha')==head and job.get('head_sha')==head,'observation-service-head')
    require(type(job.get('id')) is int and job['id']>0
        and type(job.get('run_id')) is int and job['run_id']==run_id
        and job.get('name')==JOB and job.get('status')=='in_progress'
        and ('run_attempt' not in job or type(job['run_attempt']) is int and job['run_attempt']==1),
        'observation-original-job')
    return number

def main():
    env=os.environ
    require(env.get('GITHUB_ACTIONS')=='true' and env.get('GITHUB_EVENT_NAME')=='pull_request'
        and env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_JOB')==JOB
        and env.get('GITHUB_RUN_ATTEMPT')=='1'
        and env.get('RUNNER_ENVIRONMENT')=='github-hosted'
        and env.get('GITHUB_WORKFLOW_REF','').startswith(REPOSITORY+'/'+WORKFLOW+'@'),
        'observation-ci-only')
    head=env.get('OBSERVATION_EXECUTABLE','');merge=env.get('GITHUB_SHA','');revision=env.get('GITHUB_WORKFLOW_SHA','')
    run_text=env.get('GITHUB_RUN_ID','')
    require(all(re.fullmatch('[0-9a-f]{40}',x) for x in (head,merge,revision))
        and re.fullmatch('[1-9][0-9]{0,19}',run_text),'observation-ci-shapes')
    root=Path(env['GITHUB_WORKSPACE']).resolve(strict=True)
    temporary=Path(env['RUNNER_TEMP']).resolve(strict=True)
    for path in (root,temporary):
        require(not any(x.lower()=='onedrive' for x in path.parts)
            and not any(p.is_symlink() or p.is_junction() for p in (path,*path.parents)),
            'observation-path')
    require(not temporary.is_relative_to(root),'observation-independent-output')
    metadata=root/'.git'
    require(metadata.is_dir() and not metadata.is_symlink() and not metadata.is_junction()
        and not any((metadata/p).exists() for p in ('commondir','objects/info/alternates','objects/info/http-alternates')),
        'observation-independent-git')
    def git(*args):return subprocess.check_output(['git','--no-optional-locks','-C',str(root),*args],stderr=subprocess.DEVNULL)
    def source_guard():
        require(git('rev-parse','HEAD').decode().strip()==head
            and not git('status','--porcelain=v1','--untracked-files=all'),'observation-clean-E')
        original=git('show',head+':'+WORKFLOW)
        require(0<len(original)<=262144 and git('show',revision+':'+WORKFLOW)==original,
            'observation-runner-workflow-bytes')
        return hashlib.sha256(original).hexdigest()
    workflow_sha=source_guard()
    event_path=Path(env['GITHUB_EVENT_PATH'])
    require(event_path.is_file() and not event_path.is_symlink() and not event_path.is_junction()
        and event_path.stat().st_size<=1048576,'observation-event-file')
    with event_path.open('rb') as f:raw=f.read(1048577)
    require(0<len(raw)<=1048576,'observation-event-size');event=strict_json(raw)
    number=event.get('number')
    require(type(number) is int and 0<number<10**20,'observation-number-shape')
    from lightyear_execution.tower_drill_reservation import _GitHubAPI
    api=_GitHubAPI();prefix='/repos/'+REPOSITORY;run_id=int(run_text)
    def observe():
        run=api.request('GET',prefix+'/actions/runs/'+run_text)
        require(type(run.get('workflow_id')) is int and run['workflow_id']>0,'observation-workflow-id')
        workflow=api.request('GET',prefix+'/actions/workflows/'+str(run['workflow_id']))
        require(workflow.get('path')==WORKFLOW and workflow.get('id')==run['workflow_id'],
            'observation-service-workflow')
        listed=api.request('GET',prefix+'/actions/runs/'+run_text+'/attempts/1/jobs?per_page=100')
        rows=listed.get('jobs')
        require(type(rows) is list and type(listed.get('total_count')) is int
            and listed['total_count']==len(rows)==1 and type(rows[0]) is dict,'observation-complete-single-job')
        job=rows[0];live=api.request('GET',prefix+'/pulls/'+str(number))
        relationships(event,run,job,live,head,run_id)
        return {'pr':number,'run':run_id,'job':job['id'],'workflow':run['workflow_id'],
            'source_head':head,'run_head':run['head_sha'],'job_head':job['head_sha'],
            'github_sha':merge,'workflow_revision':revision,'workflow_sha256':workflow_sha,
            'event_sha256':hashlib.sha256(raw).hexdigest()}
    observed=observe()
    require(observe()==observed and source_guard()==workflow_sha,'observation-changed')
    require(event_path.read_bytes()==raw,'observation-event-changed')
    # Fixed public scalars only. Raw event/service bodies and credentials stay local.
    output=temporary/'operator-flow-pr-identity.txt'
    text='NON-AUTHORIZING ORIGINAL PR IDENTITY OBSERVATION\n'
    text+=''.join(str(k)+'='+str(v)+'\n' for k,v in observed.items())
    text+='signing=false\nadmission=false\nfull_route_passed=false\n'
    with output.open('x',encoding='utf-8',newline='\n') as f:f.write(text)

if __name__=='__main__':main()
