"""Prepared native reservation preflight; no CLI or credential discovery.
Only the exact approved workflow/launcher may invoke reserve_from_native.
Hash/window validation does not itself establish human approval or presence.
"""
import base64
import hashlib
from lightyear_factory.contracts import ContractError
from tools.ci.supervised_native_observation import BASE,NativeObservations
from tools.ci.supervised_session_reservation import (
    checked_binding,checked_second_round,REPOSITORY)
from tools.ci.supervised_send_kernel import _packet
from tools.ci.supervised_reservation_service import NativeReservationWriter
from tools.ci.supervised_reservation_handoff import encode_completed_create

def _require(ok,reason):
    if not ok:raise ContractError('supervised-preflight-'+reason)

def _run(value,run):
    _require(type(run) is dict and type(run.get('repository')) is dict
             and run['repository'].get('full_name')==REPOSITORY,'repository')
    for k,wanted in (('id',value['run_id']),('run_attempt',1),
                     ('workflow_id',value['workflow_id'])):
        _require(type(run.get(k)) is int and run[k]==wanted,'run')
    _require(run.get('head_sha')==value['source_sha']
             and run.get('path')==value['workflow_path']
             and run.get('event')=='workflow_dispatch'
             and run.get('status')=='in_progress','run')

class ReservationPreflight(NativeObservations):
    def reservation_job(self,binding):
        value=checked_binding(binding)
        path=BASE+'/actions/runs/'+str(value['run_id'])
        _run(value,self._get(path))
        content=self._get(BASE+'/contents/'+value['workflow_path']+'?ref='+value['source_sha'])
        _require(content.get('type')=='file' and content.get('encoding')=='base64'
                 and content.get('path')==value['workflow_path']
                 and type(content.get('content')) is str
                 and len(content['content'])<=180000,'workflow')
        try:workflow=base64.b64decode(content['content'].replace('\n',''),validate=True)
        except (ValueError,UnicodeError):raise ContractError('supervised-preflight-workflow') from None
        _require(0<len(workflow)<=131072 and hashlib.sha256(workflow).hexdigest()==value['workflow_sha256'],
                 'workflow-pin')
        jobs=[];total=None
        for page in range(1,11):
            reply=self._get(path+'/attempts/1/jobs?per_page=100&page='+str(page))
            rows=reply.get('jobs');count=reply.get('total_count')
            _require(type(count) is int and 1<=count<=1000 and type(rows) is list
                     and 0<len(rows)<=100,'pages')
            if total is None:total=count
            _require(count==total,'page-drift')
            jobs.extend(rows)
            _require(len(jobs)<=total,'page-overflow')
            if len(jobs)==total:break
            _require(len(rows)==100,'short-page')
        _require(len(jobs)==total,'incomplete')
        ids=set()
        for job in jobs:
            _require(type(job) is dict and type(job.get('id')) is int
                     and 0<job['id']<2**63 and job['id'] not in ids
                     and type(job.get('run_id')) is int and job['run_id']==value['run_id']
                     and type(job.get('run_attempt')) is int and job['run_attempt']==1
                     and job.get('head_sha')==value['source_sha'],'job-identity')
            ids.add(job['id'])
        matched=[j for j in jobs if j.get('name')=='supervised-reservation']
        _require(len(matched)==1 and matched[0].get('status')=='in_progress','reservation-role')
        _run(value,self._get(path))
        return matched[0]['id']

def reserve_from_native(*,binding,packet_bytes,approved_packet_sha256,
                        ca_pem,job_token,deadline,run_directory,
                        previous_receipt=None,approved_continuation=None):
    """Produce outputs after native preflight and own successful create.

    Exact trusted launcher must authenticate approval/baseline/human presence,
    local reservation job role, token provenance and (round two) continuation
    and archived failed-verdict origin. These are not supplied by a hash alone.
    """
    value=checked_binding(binding)
    packet=_packet(packet_bytes,approved_packet_sha256,value)
    if value['round']==2:
        checked_second_round(value,previous_receipt,approved_continuation)
    else:
        _require(previous_receipt is None and approved_continuation is None,'first-round-extra')
    native=ReservationPreflight(ca_pem=ca_pem,ca_sha256=packet['public_ca_sha256'],
                               token=job_token,deadline=deadline)
    job_id=native.reservation_job(value)
    # Recheck actual wall-clock approval window after native observations.
    _packet(packet_bytes,approved_packet_sha256,value)
    writer=NativeReservationWriter(ca_pem=ca_pem,ca_sha256=packet['public_ca_sha256'],
                                  token=job_token,deadline=deadline)
    result=writer.create_once(value,run_directory)
    return encode_completed_create(result,job_id)
