"""Read-only service observations of an existing configured consumption.

An annotated tag is unsigned. Its presence and matching workflow metadata do
not prove who created it, native admission, process death or signed outcome
authority. No existing claim can be resumed through this module. Production
entry constructs its own API; synthetic internal tests grant no authority.
"""
from copy import deepcopy
import re
from .contracts import ExecutionContractError
from .configured_consumption_evidence import consumption_message_bytes,check_consumption_admission_relations
from .configured_human_main_identity import REPOSITORY,WORKFLOW,JOB,PREFIX
from .tower_drill_reservation import _GitHubAPI

def _require(ok,reason):
    if not ok:raise ExecutionContractError('configured-consumption-observation-'+reason)

def _oid(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{40}',value) is not None

def _identity(record):
    ci=record['ci']
    _require(set(ci)=={'repository','run_id','run_attempt','job','job_id','workflow_id','workflow_ref','head_sha'},'identity-shape')
    _require(ci['repository']==REPOSITORY and ci['job']==JOB and _oid(ci['head_sha'])
        and type(ci['run_attempt']) is int and ci['run_attempt']==1
        and all(type(ci[k]) is int and 0<ci[k]<10**20 for k in ('run_id','job_id','workflow_id'))
        and type(ci['workflow_ref']) is str
        and re.fullmatch(re.escape(REPOSITORY+'/'+WORKFLOW+'@')+'[0-9a-f]{40}',ci['workflow_ref']) is not None,'identity-binding')
    return ci

def _observe_consumption(record,admission,api):
    """Internal synthetic service boundary. Returns observations, never authority."""
    record=deepcopy(record);admission=deepcopy(admission)
    check_consumption_admission_relations(record,admission)
    ci=_identity(record);message=consumption_message_bytes(record).decode('utf-8')
    name='factory-human-drill-consumed-'+record['nonce_sha256']
    ref_path=PREFIX+'/git/ref/tags/'+name
    tag_path=PREFIX+'/git/tags/'+admission['consumed_tag_object']
    def get(path):
        # All call sites are fixed below; no caller-supplied endpoint or method.
        value=api.request('GET',path)
        _require(type(value) is dict,'service-shape')
        return deepcopy(value)
    ref=get(ref_path);tag=get(tag_path)
    target={'type':'commit','sha':ci['head_sha'],
            'url':'https://api.github.com'+PREFIX+'/git/commits/'+ci['head_sha']}
    _require(ref.get('ref')==admission['consumed_ref']
        and type(ref.get('object')) is dict
        and ref['object'].get('type')=='tag'
        and ref['object'].get('sha')==admission['consumed_tag_object']
        and tag.get('sha')==admission['consumed_tag_object']
        and tag.get('tag')==name and tag.get('message')==message
        and tag.get('object')==target,'remote-tag-binding')
    run=get(PREFIX+'/actions/runs/'+str(ci['run_id']))
    workflow=get(PREFIX+'/actions/workflows/'+str(ci['workflow_id']))
    job=get(PREFIX+'/actions/jobs/'+str(ci['job_id']))
    _require(type(run.get('id')) is int and run['id']==ci['run_id']
        and type(run.get('run_attempt')) is int and run['run_attempt']==1
        and type(run.get('workflow_id')) is int and run['workflow_id']==ci['workflow_id']
        and run.get('event')=='workflow_dispatch' and run.get('head_branch')=='main'
        and run.get('head_sha')==ci['head_sha']
        and run.get('status') in ('in_progress','completed')
        and type(run.get('head_repository')) is dict
        and run['head_repository'].get('full_name')==REPOSITORY,'remote-run-binding')
    _require(type(workflow.get('id')) is int and workflow['id']==ci['workflow_id']
        and workflow.get('path')==WORKFLOW,'remote-workflow-binding')
    _require(type(job.get('id')) is int and job['id']==ci['job_id']
        and type(job.get('run_id')) is int and job['run_id']==ci['run_id']
        and job.get('name')==JOB and job.get('head_sha')==ci['head_sha']
        and job.get('status') in ('in_progress','completed')
        and ('run_attempt' not in job or (type(job['run_attempt']) is int and job['run_attempt']==1)),
        'remote-job-binding')
    _require(get(ref_path)==ref and get(tag_path)==tag,'remote-tag-changed')
    # Preserve original service documents, including failed job conclusions.
    # This mapping is not a receipt schema and is not fed to strict qualification.
    return {'ref':ref,'tag':tag,'run':run,'workflow':workflow,'job':job}

def observe_existing_consumption(record,admission):
    """Bounded GET-only observation with existing job authentication; no writes."""
    return _observe_consumption(record,admission,_GitHubAPI())
