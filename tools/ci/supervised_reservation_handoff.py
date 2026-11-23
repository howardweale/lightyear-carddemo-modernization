"""Unsigned native job-output receipt codec; not standalone authentication.
Only a reviewed, source-pinned workflow may supply these values through needs.
No environment lookup, filesystem write, network, model call or live entry.
"""
import base64
import hashlib
import json
from lightyear_factory.contracts import ContractError
from tools.ci.supervised_session_reservation import (
    checked_binding,canonical_record,checked_create_ack,LABEL)

FIELDS={'label','binding','reservation_job_id','reservation_commit',
        'create_status','create_response','qualification_evidence'}

def _require(ok,reason):
    if not ok:raise ContractError('supervised-handoff-'+reason)

def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),
                      ensure_ascii=True,allow_nan=False).encode('ascii')

def encode_completed_create(result,reservation_job_id):
    """Called only after writer persisted its own successful-create receipt."""
    _require(type(result) is dict,'result')
    binding=checked_binding(result.get('binding'))
    _require(type(reservation_job_id) is int and 0<reservation_job_id<2**63,'job')
    ack=checked_create_ack(binding,result.get('reservation_commit'),
                           result.get('create_status'),result.get('create_response'))
    _require(result.get('label')==LABEL and result.get('qualification_evidence') is False
             and result.get('ack')==ack,'create-result')
    value=dict(label=LABEL,binding=binding,reservation_job_id=reservation_job_id,
               reservation_commit=result['reservation_commit'],create_status=201,
               create_response=result['create_response'],qualification_evidence=False)
    raw=_canonical(value)
    _require(len(raw)<=16384,'size')
    return {'receipt_base64':base64.b64encode(raw).decode('ascii'),
            'receipt_sha256':hashlib.sha256(raw).hexdigest()}

def bind_job_output(encoded,digest,binding,readback):
    """Validate bytes and joins; the caller must authenticate workflow origin.

    A digest supplied alongside bytes detects substitution relative to a trusted
    needs output only. Never accept dispatch inputs/files/manual fields as origin.
    The result deliberately does not assert original-create authentication.
    """
    expected=checked_binding(binding)
    _require(type(encoded) is str and 0<len(encoded)<=21848,'encoding')
    try:raw=base64.b64decode(encoded,validate=True)
    except (ValueError,UnicodeError):raise ContractError('supervised-handoff-encoding') from None
    _require(len(raw)<=16384 and hashlib.sha256(raw).hexdigest()==digest,'digest')
    def pairs(items):
        out={}
        for k,v in items:
            _require(k not in out,'duplicate')
            out[k]=v
        return out
    def constant(value):raise ValueError('nonfinite')
    try:value=json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    except ContractError:
        raise
    except (ValueError,UnicodeError,RecursionError):
        raise ContractError('supervised-handoff-json') from None
    _require(type(value) is dict and set(value)==FIELDS and _canonical(value)==raw,'canonical')
    _require(value['label']==LABEL and value['qualification_evidence'] is False
             and checked_binding(value['binding'])==expected,'binding')
    _require(type(readback) is dict and readback.get('label')==LABEL
             and readback.get('qualification_evidence') is False
             and readback.get('stored_record')==canonical_record(expected)
             and readback.get('reservation_commit')==value['reservation_commit']
             and type(value['reservation_job_id']) is int
             and value['reservation_job_id']>0
             and readback.get('reservation_job_id')==value['reservation_job_id'],'readback')
    ack=checked_create_ack(expected,value['reservation_commit'],
                           value['create_status'],value['create_response'])
    return dict(receipt=value,receipt_sha256=digest,ack=ack,
                original_create_ack_authenticated=False,
                requires_reviewed_needs_origin=True,label=LABEL,qualification_evidence=False)
