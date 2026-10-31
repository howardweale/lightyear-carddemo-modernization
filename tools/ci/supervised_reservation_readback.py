"""Read-only reservation object verification; no create/adoption authority.
Returned object equality does not prove a successful create acknowledgement.
The launcher must join an authenticated successful reservation-job receipt.
"""
import base64
import hashlib
import http.client
import re
from lightyear_factory.contracts import ContractError
from tools.ci.supervised_native_observation import (
    BASE,LIMIT,ROUTES,NativeObservations,_connection,_json,_require)
from tools.ci.supervised_flex_exchange import _remaining
from tools.ci.supervised_session_reservation import checked_binding,canonical_record,reservation_ref

RECORD_ROUTES=re.compile(re.escape(BASE)+
    r'/git/(?:ref/tags/factory-supervised-engineering-[0-9a-f]{64}-round-[12]|(?:commits|trees|blobs)/[0-9a-f]{40})')

def object_id(kind, raw):
    return hashlib.sha1(kind.encode('ascii')+b' '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest()

class ReservationReadback(NativeObservations):
    def _get(self, route):
        _require(type(route) is str and (ROUTES.fullmatch(route) is not None or RECORD_ROUTES.fullmatch(route) is not None),'route')
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

    def read_reserved_objects(self, binding, expected_commit):
        value=checked_binding(binding)
        _require(type(expected_commit) is str and re.fullmatch('[0-9a-f]{40}',expected_commit),
                 'reservation-commit')
        record=canonical_record(value)
        blob_sha=object_id('blob',record)
        tree_sha=object_id('tree',b'100644 reservation.json\0'+bytes.fromhex(blob_sha))
        ref=reservation_ref(value)
        route=BASE+'/git/ref/'+ref.removeprefix('refs/')
        def check_ref(reply):
            _require(reply.get('ref')==ref and type(reply.get('object')) is dict
                     and reply['object'].get('type')=='commit'
                     and reply['object'].get('sha')==expected_commit,'reservation-ref')
        check_ref(self._get(route))
        commit=self._get(BASE+'/git/commits/'+expected_commit)
        parents=commit.get('parents')
        _require(commit.get('sha')==expected_commit
                 and type(commit.get('tree')) is dict and commit['tree'].get('sha')==tree_sha
                 and type(parents) is list and len(parents)==1 and type(parents[0]) is dict
                 and parents[0].get('sha')==value['source_sha']
                 and commit.get('message')==value['label']+'\n'+hashlib.sha256(record).hexdigest(),
                 'reservation-commit-binding')
        tree=self._get(BASE+'/git/trees/'+tree_sha)
        entries=tree.get('tree')
        _require(tree.get('sha')==tree_sha and tree.get('truncated') is False
                 and type(entries) is list and len(entries)==1 and type(entries[0]) is dict,
                 'reservation-tree')
        row=entries[0]
        _require(row.get('path')=='reservation.json' and row.get('mode')=='100644'
                 and row.get('type')=='blob' and row.get('sha')==blob_sha,
                 'reservation-entry')
        blob=self._get(BASE+'/git/blobs/'+blob_sha)
        _require(blob.get('sha')==blob_sha and blob.get('encoding')=='base64'
                 and type(blob.get('size')) is int and blob['size']==len(record)
                 and type(blob.get('content')) is str
                 and len(blob['content'])<=65536,'reservation-blob')
        try:
            decoded=base64.b64decode(blob['content'].replace('\n',''),validate=True)
        except (ValueError,UnicodeError):
            raise ContractError('supervised-native-reservation-base64') from None
        _require(decoded==record and object_id('blob',decoded)==blob_sha,'reservation-record')
        # Uses exact current run, complete attempt-one job inventory and source workflow.
        handoff=super().sender_handoff(value,decoded)
        reservers=[j for j in handoff['all_jobs']['jobs']
                   if j.get('name')=='supervised-reservation']
        _require(len(reservers)==1 and reservers[0].get('status')=='completed'
                 and reservers[0].get('conclusion')=='success','reservation-job')
        check_ref(self._get(route))
        return dict(stored_record=decoded,reservation_commit=expected_commit,
                    reservation_job_id=reservers[0]['id'],sender_handoff=handoff,
                    original_create_ack_authenticated=False,
                    label=value['label'],qualification_evidence=False)
