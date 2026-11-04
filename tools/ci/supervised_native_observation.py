"""Direct native GitHub observations for supervised engineering.

No credential lookup, mutation, model call or command-line entry. The caller
must supply approved public CA bytes and its narrowly scoped read token.
"""
import base64
import hashlib
import http.client
import json
import re

from lightyear_factory.contracts import ContractError
from tools.ci.supervised_flex_exchange import _fixed_provider_connection, _remaining
from tools.ci.supervised_session_reservation import (
    REPOSITORY, checked_binding, checked_sender_handoff)

BASE = '/repos/' + REPOSITORY
ROUTES = re.compile(re.escape(BASE) + r'(?:/actions/runs/[1-9][0-9]*(?:/attempts/1/jobs\?per_page=100&page=[1-9][0-9]*)?|/contents/\.github/workflows/supervised-intcalc-engineering\.yml\?ref=[0-9a-f]{40})')
LIMIT = 4194304


def _require(ok, reason):
    if not ok:
        raise ContractError('supervised-native-' + reason)


def _connection(ca_pem, ca_sha256, deadline):
    template = _fixed_provider_connection(ca_pem, ca_sha256, deadline)
    try:
        # Reuse the explicit-root native context, never the provider connection.
        return http.client.HTTPSConnection('api.github.com',443,
                        timeout=template.timeout,context=template._context)
    finally:
        template.close()


def _json(raw):
    def pairs(items):
        out={}
        for k,v in items:
            _require(k not in out,'json-duplicate')
            out[k]=v
        return out
    def constant(value):
        raise ValueError('nonfinite')
    try:
        return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,UnicodeError,RecursionError):
        raise ContractError('supervised-native-json') from None


class NativeObservations:
    """Read-only fixed routes, one fresh connection per GET, no retry/redirect."""
    def __init__(self, *, ca_pem, ca_sha256, token, deadline):
        _require(type(token) is str and 1 <= len(token) <= 4096
                 and all(33 <= ord(c) <= 126 for c in token),'token-format')
        self._ca_pem=ca_pem
        self._ca_sha256=ca_sha256
        self._token=token
        self._deadline=deadline

    def _get(self, route):
        _require(type(route) is str and ROUTES.fullmatch(route) is not None,'route')
        connection=_connection(self._ca_pem,self._ca_sha256,self._deadline)
        response=None
        try:
            connection.timeout=_remaining(self._deadline)
            connection.request('GET',route,headers={
                'Authorization':'Bearer '+self._token,
                'Accept':'application/vnd.github+json',
                'Accept-Encoding':'identity','Connection':'close',
                'X-GitHub-Api-Version':'2022-11-28',
                'User-Agent':'supervised-engineering-observer'})
            sock=connection.sock
            sock.settimeout(_remaining(self._deadline))
            response=connection.getresponse()
            _require(response.status==200,'http-refused')
            headers=response.getheaders()
            lengths=[v for k,v in headers if k.lower()=='content-length']
            encodings=[v for k,v in headers if k.lower()=='content-encoding']
            transfers=[v for k,v in headers if k.lower()=='transfer-encoding']
            _require(len(lengths)<=1 and (not encodings or encodings==['identity'])
                     and (not transfers or
                          (len(transfers)==1 and transfers[0].lower()=='chunked'
                           and not lengths)), 'framing')
            length=None
            if lengths:
                _require(lengths[0].isascii() and lengths[0].isdigit()
                         and len(lengths[0])<=7,'length')
                length=int(lengths[0]);_require(0 < length <= LIMIT,'length')
            data=bytearray()
            while True:
                sock.settimeout(_remaining(self._deadline))
                block=response.read1(min(8192,LIMIT+1-len(data)))
                if not block:break
                data.extend(block)
                _require(len(data)<=LIMIT,'size')
                if length is not None and len(data)==length:break
            _remaining(self._deadline)
            _require(bool(data) and (length is None or len(data)==length),'truncated')
            value=_json(bytes(data))
            _require(type(value) is dict,'object')
            return value
        except ContractError:
            raise
        except (OSError,http.client.HTTPException,ValueError,AttributeError):
            raise ContractError('supervised-native-outcome-unknown') from None
        finally:
            if response is not None:response.close()
            connection.close()

    def sender_handoff(self, binding, stored_record):
        value=checked_binding(binding)
        run_path=BASE+'/actions/runs/'+str(value['run_id'])
        run=self._get(run_path)
        _require(type(run.get('run_attempt')) is int and run['run_attempt']==1,
                 'current-attempt')
        result=self._get(BASE+'/contents/'+value['workflow_path']+
                         '?ref='+value['source_sha'])
        _require(result.get('type')=='file' and result.get('encoding')=='base64'
                 and result.get('path')==value['workflow_path']
                 and type(result.get('content')) is str,'workflow-content')
        _require(len(result['content'])<=180000,'workflow-size')
        try:
            workflow=base64.b64decode(result['content'].replace('\n',''),validate=True)
        except (ValueError,UnicodeError):
            raise ContractError('supervised-native-workflow-encoding') from None
        _require(hashlib.sha256(workflow).hexdigest()==value['workflow_sha256'],
                 'workflow-pin')
        jobs=[];total=None
        for page in range(1,11):
            batch=self._get(run_path+'/attempts/1/jobs?per_page=100&page='+str(page))
            count=batch.get('total_count');rows=batch.get('jobs')
            _require(type(count) is int and 1<=count<=1000
                     and type(rows) is list and 0<len(rows)<=100,'pagination')
            if total is None:total=count
            _require(count==total,'pagination-drift')
            jobs.extend(rows)
            _require(len(jobs)<=total,'pagination-overflow')
            if len(jobs)==total:break
            _require(len(rows)==100,'pagination-short')
        _require(len(jobs)==total,'pagination-incomplete')
        matches=[job for job in jobs if type(job) is dict
                 and job.get('name')==value['sender_job_name']]
        _require(len(matches)==1,'sender-unique')
        observed=checked_sender_handoff(value,stored_record,run,matches[0],
                          {'total_count':total,'jobs':jobs},workflow)
        # Re-read live run identity after pagination; no stale attempt adoption.
        refreshed=self._get(run_path)
        checked_sender_handoff(value,stored_record,refreshed,matches[0],
                          {'total_count':total,'jobs':jobs},workflow)
        return dict(binding=value,stored_record=stored_record,native_run=refreshed,
                    native_job=matches[0],all_jobs={'total_count':total,'jobs':jobs},
                    workflow_bytes=workflow,observed=observed)
