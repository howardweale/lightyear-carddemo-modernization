"""Prepared create-only engineering reservation writer; no CLI or activation.
Requires a separately approved launcher, exact public namespace and token scope.
No provider credential, candidate execution, retry, delete, ref update or adoption.
This module is not approval or a proof of a global spending cap.
"""
import base64
import hashlib
import http.client
import json
import re
from pathlib import Path
from lightyear_factory.contracts import ContractError
from tools.ci.supervised_native_observation import (
    BASE, LIMIT, NativeObservations, _connection, _json, _require)
from tools.ci.supervised_flex_exchange import _remaining
from tools.ci.supervised_session_reservation import (
    checked_binding, canonical_record, reservation_ref, checked_create_ack)
from tools.ci.supervised_send_kernel import _persist_new

POST_ROUTES=frozenset(BASE+'/git/'+suffix for suffix in ('blobs','trees','commits','refs'))

def object_id(kind, raw):
    return hashlib.sha1(kind.encode('ascii')+b' '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest()

class NativeReservationWriter(NativeObservations):
    def _post(self, route, payload):
        _require(route in POST_ROUTES,'route')
        body=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
        _require(len(body)<=65536,'request-size')
        connection=_connection(self._ca_pem,self._ca_sha256,self._deadline)
        response=None
        try:
            connection.timeout=_remaining(self._deadline)
            connection.request('POST',route,body=body,headers={
                'Content-Type':'application/json','Content-Length':str(len(body)),
                'Authorization':'Bearer '+self._token,
                'Accept':'application/vnd.github+json',
                'Accept-Encoding':'identity','Connection':'close',
                'X-GitHub-Api-Version':'2022-11-28',
                'User-Agent':'supervised-engineering-observer'})
            sock=connection.sock
            sock.settimeout(_remaining(self._deadline))
            response=connection.getresponse()
            _require(response.status==201,'http-refused')
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

    def create_once(self, binding, run_directory):
        """Create exactly one round claim; failed/uncertain calls never resume.

        The trusted launcher must validate approval, current native reservation
        job/workflow/source and round-two continuation before calling this method.
        A read-only sender must independently verify these objects and the exact
        native reservation job; merely passing this return dictionary is unsafe.
        """
        value=checked_binding(binding)
        _require(not getattr(self,'_used',False),'writer-reused')
        self._used=True
        _require(type(run_directory) in (Path,type(Path('.')))
                 and run_directory.is_absolute() and run_directory.is_dir()
                 and not run_directory.is_symlink()
                 and run_directory.resolve(strict=True)==run_directory,'directory')
        record=canonical_record(value)
        intent=run_directory/('round-'+str(value['round'])+'.reservation-intent.json')
        _persist_new(intent,record)
        # Blob and single-file tree are checked against local Git object IDs.
        blob_sha=object_id('blob',record)
        blob=self._post(BASE+'/git/blobs',
                        {'content':base64.b64encode(record).decode('ascii'),'encoding':'base64'})
        _require(blob.get('sha')==blob_sha,'blob-pin')
        tree_sha=object_id('tree',b'100644 reservation.json\0'+bytes.fromhex(blob_sha))
        tree=self._post(BASE+'/git/trees',{'tree':[
            {'path':'reservation.json','mode':'100644','type':'blob','sha':blob_sha}]})
        _require(tree.get('sha')==tree_sha,'tree-pin')
        message='supervised engineering run, not a qualified production run\n'+hashlib.sha256(record).hexdigest()
        commit=self._post(BASE+'/git/commits',
                    {'message':message,'tree':tree_sha,'parents':[value['source_sha']]})
        commit_sha=commit.get('sha')
        _require(type(commit_sha) is str and re.fullmatch('[0-9a-f]{40}',commit_sha)
                 and type(commit.get('tree')) is dict and commit['tree'].get('sha')==tree_sha
                 and type(commit.get('parents')) is list
                 and len(commit['parents'])==1
                 and commit['parents'][0].get('sha')==value['source_sha']
                 and commit.get('message')==message,'commit-pin')
        # The same session+round collides across independent dispatches.
        # No existence check, update, delete, retry or GET-based adoption.
        response=self._post(BASE+'/git/refs',
                           {'ref':reservation_ref(value),'sha':commit_sha})
        ack=checked_create_ack(value,commit_sha,201,response)
        result=dict(label=value['label'],binding=value,reservation_commit=commit_sha,
                    blob=blob_sha,tree=tree_sha,create_status=201,
                    create_response=response,ack=ack,qualification_evidence=False)
        _persist_new(run_directory/('round-'+str(value['round'])+'.reservation-ack.json'),
                     json.dumps(result,sort_keys=True,separators=(',',':')).encode('ascii'))
        return result
