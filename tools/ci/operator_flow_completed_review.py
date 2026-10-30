"""Original completed reviewer GET/step-log observation before publication.

Matching service/log records are not current proof/trust, full guards or
publication permission. No API/verifier/clock injection, writes or retries.
Live PR head must still be E; do not reuse this reader after publication M.
"""
import hashlib,json,os,re
from pathlib import Path
from tools.ci.operator_flow_publication_review import REVIEW_WORKFLOW,REVIEW_JOB,_independent_expectations
from tools.ci.operator_flow_review_workflow import _review_observation
from tools.ci.operator_flow_review_cli import SCALARS
from tools.ci.operator_flow_consumer import clean_root,git
from tools.ci.operator_flow_handoff import REPOSITORY,fetch_producer_handoff,_original_producer
from tools.ci.operator_flow_publication_reconstruction import reconstruct_publication_objects
from tools.ci.operator_flow_download import _capture_bounded_stdout
from tools.ci.operator_flow_metadata import require

STEP='Original disposable native publication review'
LIMIT=1024*1024

def _relationships(run,workflow,listing,pr,merge,expected):
    run_id,job_id,head,number,base,tested=(expected[k] for k in ('run','job','executable','pr','base','tested_merge'))
    require(all(type(v) is int and 0<v<10**20 for v in (run_id,job_id,number))
        and all(type(v) is str and re.fullmatch('[0-9a-f]{40}',v) for v in (head,base,tested)),
        'completed-review-expectations')
    require(type(run) is dict and type(run.get('id')) is int and run['id']==run_id
        and type(run.get('run_attempt')) is int and run['run_attempt']==1
        and run.get('event')=='pull_request' and run.get('head_sha')==head
        and run.get('status')=='completed' and run.get('conclusion')=='success'
        and run.get('repository',{}).get('full_name')==REPOSITORY
        and run.get('head_repository',{}).get('full_name')==REPOSITORY
        and type(run.get('workflow_id')) is int and run['workflow_id']>0,'completed-review-run')
    require(type(workflow) is dict and type(workflow.get('id')) is int
        and workflow['id']==run['workflow_id'] and workflow.get('path')==REVIEW_WORKFLOW,'completed-review-workflow')
    require(type(listing) is dict and type(listing.get('jobs')) is list
        and type(listing.get('total_count')) is int and listing['total_count']==len(listing['jobs'])==1,
        'completed-review-single-job')
    job=listing['jobs'][0]
    require(type(job) is dict and type(job.get('id')) is int and job['id']==job_id
        and type(job.get('run_id')) is int and job['run_id']==run_id and job.get('head_sha')==head
        and job.get('name')==REVIEW_JOB and job.get('status')=='completed' and job.get('conclusion')=='success'
        and ('run_attempt' not in job or type(job['run_attempt']) is int and job['run_attempt']==1),
        'completed-review-job')
    steps=job.get('steps')
    require(type(steps) is list and 1<=len(steps)<=30
        and all(type(x) is dict and type(x.get('number')) is int and x['number']>0
            and type(x.get('name')) is str and x.get('status')=='completed' and x.get('conclusion')=='success'
            for x in steps),'completed-review-successful-steps')
    numbers=[x['number'] for x in steps]
    require(numbers==sorted(set(numbers)),'completed-review-step-order')
    required=('Run actions/checkout@v7','Run actions/setup-python@v6','Install native public verification dependency','Fetch original tested merge and workflow revision',STEP)
    positions=[]
    for name in required:
        matches=[x['number'] for x in steps if x['name']==name]
        require(len(matches)==1,'completed-review-required-step');positions.extend(matches)
    require(positions==sorted(positions),'completed-review-required-order')
    require(type(pr) is dict and type(pr.get('number')) is int and pr['number']==number
        and pr.get('state')=='open' and pr.get('head',{}).get('sha')==head
        and pr.get('head',{}).get('repo',{}).get('full_name')==REPOSITORY
        and pr.get('base',{}).get('sha')==base and pr.get('base',{}).get('ref')=='main'
        and pr.get('base',{}).get('repo',{}).get('full_name')==REPOSITORY
        and pr.get('merge_commit_sha')==tested,'completed-review-current-E-before-publication')
    require(type(merge) is dict and merge.get('sha')==tested and type(merge.get('parents')) is list
        and [x.get('sha') for x in merge['parents']]==[base,head],'completed-review-tested-merge')
    return dict(expected,workflow=workflow['id'],step=positions[-1],
        steps=[(x['number'],x['name'],x['status'],x['conclusion']) for x in steps])

def _snapshot(api,expected):
    prefix='/repos/'+REPOSITORY
    run=api.request('GET',prefix+'/actions/runs/'+str(expected['run']))
    require(type(run.get('workflow_id')) is int and run['workflow_id']>0,'completed-review-workflow-id')
    workflow=api.request('GET',prefix+'/actions/workflows/'+str(run['workflow_id']))
    jobs=api.request('GET',prefix+'/actions/runs/'+str(expected['run'])+'/attempts/1/jobs?per_page=100')
    pr=api.request('GET',prefix+'/pulls/'+str(expected['pr']))
    merge=api.request('GET',prefix+'/git/commits/'+expected['tested_merge'])
    return _relationships(run,workflow,jobs,pr,merge,expected)

def _log_identity(raw,candidate,requests,values,observed):
    require(type(raw) is bytes and 0<len(raw)<=LIMIT,'completed-review-log-size')
    text=raw.decode('utf-8');marker='DISPOSABLE_REVIEW_BINDING '
    require(text.count(marker)==1,'completed-review-unique-observation')
    row=next(line for line in text.splitlines() if marker in line)
    match=re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{1,9}Z (DISPOSABLE_REVIEW_BINDING .+)',row)
    require(match is not None,'completed-review-original-log-line')
    line=match.group(1);pairs=[item.split('=',1) for item in line[len(marker):].split(' ')]
    require(all(len(pair)==2 for pair in pairs) and len({pair[0] for pair in pairs})==len(pairs),
        'completed-review-diagnostic-fields')
    fields=dict(pairs)
    numeric={}
    for key in ('pr','reviewer_run','reviewer_job','workflow'):
        value=fields.get(key,'');require(re.fullmatch('[1-9][0-9]{0,19}',value),'completed-review-diagnostic-number')
        numeric[key]=int(value)
    identity=dict(pr=numeric['pr'],run=numeric['reviewer_run'],job=numeric['reviewer_job'],workflow=numeric['workflow'],
        executable=fields.get('E'),base=fields.get('base'),tested_merge=fields.get('tested_merge'),
        workflow_revision=fields.get('workflow_revision'),workflow_sha256=fields.get('workflow_sha256'),
        event_sha256=fields.get('event_sha256'))
    require(all(identity[k]==observed[k] for k in ('pr','run','job','workflow','executable','base','tested_merge')),
        'completed-review-service-log-join')
    require(line==_review_observation(candidate,requests,values,identity),'completed-review-exact-request-binding')
    return identity

def _workflow_bytes(root,revision):
    require(type(revision) is str and re.fullmatch('[0-9a-f]{40}',revision),'completed-review-source-revision')
    ref=revision+':'+REVIEW_WORKFLOW;size=git(root,'cat-file','-s',ref).decode().strip()
    require(re.fullmatch('[1-9][0-9]{0,6}',size) and int(size)<=262144,'completed-review-source-size')
    raw=git(root,'show',ref);require(len(raw)==int(size),'completed-review-source-length')
    return raw

def read_reviewed_publication(executable_root,*,reviewer_run_id,reviewer_job_id,pr_number,base,tested_merge,values):
    # Values are independent external arguments, never adopted from logs/proof.
    require(type(values) is dict and set(values)==set(SCALARS),'completed-review-independent-values')
    _independent_expectations(**values)
    expected=dict(run=reviewer_run_id,job=reviewer_job_id,pr=pr_number,
        executable=values['executable'],base=base,tested_merge=tested_merge)
    require(all(type(expected[k]) is int and 0<expected[k]<10**20 for k in ('run','job','pr'))
        and all(type(expected[k]) is str and re.fullmatch('[0-9a-f]{40}',expected[k]) for k in ('base','tested_merge')),
        'completed-review-independent-identity')
    root=Path(executable_root);clean_root(root)
    require(git(root,'rev-parse','HEAD').decode().strip()==values['executable'],'completed-review-clean-E')
    # Scratch has no active reviewer workflow, so it cannot reach the API.
    workflow_bytes=_workflow_bytes(root,values['executable'])
    require(_workflow_bytes(root,tested_merge)==workflow_bytes,'completed-review-tested-workflow')
    from lightyear_execution.tower_drill_reservation import _GitHubAPI
    api=_GitHubAPI();observed=_snapshot(api,expected)
    handoff={k:values[k] for k in ('executable','producer_run_id','artifact_id','archive_sha256')}
    files,producer=fetch_producer_handoff(handoff)
    candidate,requests=reconstruct_publication_objects(root,files,expected_executable=values['executable'],
        expected_candidate=values['metadata_head'],commit_epoch=values['commit_epoch'])
    endpoint='/repos/'+REPOSITORY+'/actions/jobs/'+str(reviewer_job_id)+'/steps/'+str(observed['step'])+'/logs'
    raw=_capture_bounded_stdout(['gh','api',endpoint],max_bytes=LIMIT,timeout=45)
    identity=_log_identity(raw,candidate,requests,values,observed)
    require(_workflow_bytes(root,identity['workflow_revision'])==workflow_bytes
        and hashlib.sha256(workflow_bytes).hexdigest()==identity['workflow_sha256'],
        'completed-review-original-workflow-bytes')
    require(_snapshot(api,expected)==observed,'completed-review-service-changed')
    require(_original_producer(api,handoff)==producer,'completed-review-producer-changed')
    require(reconstruct_publication_objects(root,files,expected_executable=values['executable'],
        expected_candidate=values['metadata_head'],commit_epoch=values['commit_epoch'])==(candidate,requests),
        'completed-review-reconstruction-changed')
    clean_root(root);require(git(root,'rev-parse','HEAD').decode().strip()==values['executable'],
        'completed-review-source-changed')
    # Original false flags remain. No current proof/trust/full guards or grant.
    return candidate,requests,dict(observed,log_sha256=hashlib.sha256(raw).hexdigest(),identity=identity,producer=producer)
