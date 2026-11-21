"""Composed engineering send kernel; no CLI, credential lookup or activation.

The native launcher remains unimplemented. Caller-supplied hashes/dictionaries
are NOT direct-chat approval or authenticated GitHub evidence. Production use
requires the exact approved launcher/workflow, service create/readback and
supervision. This module never grants Track B admission or qualification.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path

from lightyear_factory.contracts import ContractError
from tools.ci.supervised_intcalc_boundary import (
    LABEL, MODEL, generation_request, response_proposal)
from tools.ci.supervised_session_reservation import (
    checked_create_ack, checked_second_round, checked_sender_handoff)
from tools.ci.supervised_flex_exchange import (
    _fixed_provider_connection, _exchange_once)

PACKET_FIELDS = {'label','session_sha256','source_sha','workflow_sha256',
    'public_ca_sha256','call_limit','budget_usd','model','endpoint',
    'not_before_utc','expires_utc','qualification_evidence'}


def _require(ok, reason):
    if not ok:
        raise ContractError('supervised-send-' + reason)


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),
                      ensure_ascii=True,allow_nan=False).encode('ascii')


def _packet(raw, approved_sha256, binding):
    _require(type(raw) is bytes and 0 < len(raw) <= 65536
             and hashlib.sha256(raw).hexdigest() == approved_sha256
             and approved_sha256 == binding['packet_sha256'], 'packet-pin')
    def pairs(items):
        value={}
        for key,item in items:
            _require(key not in value,'packet-duplicate')
            value[key]=item
        return value
    try:
        p=json.loads(raw,object_pairs_hook=pairs)
    except (ValueError,UnicodeError,RecursionError):
        raise ContractError('supervised-send-packet-json') from None
    _require(type(p) is dict and set(p)==PACKET_FIELDS,'packet-fields')
    _require(p['label']==LABEL and p['qualification_evidence'] is False
             and p['session_sha256']==binding['session_sha256']
             and p['source_sha']==binding['source_sha']
             and p['workflow_sha256']==binding['workflow_sha256']
             and type(p['call_limit']) is int and p['call_limit']==2
             and p['budget_usd']=='25.00' and p['model']==MODEL
             and p['endpoint']=='https://api.openai.com/v1/responses','packet-scope')
    try:
        times=[]
        for field in ('not_before_utc','expires_utc'):
            _require(type(p[field]) is str and p[field].endswith('Z'),'packet-window')
            times.append(datetime.datetime.fromisoformat(p[field].replace('Z','+00:00')))
        before,after=times
        now=datetime.datetime.now(datetime.timezone.utc)
        _require(0 < (after-before).total_seconds() <= 7200
                 and before <= now < after,'packet-window')
    except (ValueError,TypeError,OverflowError):
        raise ContractError('supervised-send-packet-window') from None
    return p


def _persist_new(path, raw):
    # Exclusive create is local repeat prevention, not the global reservation.
    # Never delete/adopt a partial intent; file fsync is not universal power-loss
    # durability or an acknowledgement from the separate evidence archive.
    try:
        with path.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        raise ContractError('supervised-send-persistence-refused') from None


def send_once_kernel(*, binding, stored_record, native_run, native_job, all_jobs,
                     workflow_bytes, packet_bytes, approved_packet_sha256,
                     reservation_commit, create_status, create_response,
                     candidate, ca_pem, authorization, deadline, run_directory,
                     previous_receipt=None, approved_continuation=None):
    """Exactly one exchange after checks and exclusive persisted local intent.

    Offline CI may replace the transport with an inert stub; that is component
    evidence only. This kernel cannot itself prove caller approval/API origin,
    service durability, human presence, whole-process timeout or archive readback.
    """
    handoff=checked_sender_handoff(binding,stored_record,native_run,native_job,
                                   all_jobs,workflow_bytes)
    value=handoff['binding']
    packet=_packet(packet_bytes,approved_packet_sha256,value)
    ack=checked_create_ack(value,reservation_commit,create_status,create_response)
    if value['round']==2:
        checked_second_round(value,previous_receipt,approved_continuation)
    else:
        _require(previous_receipt is None and approved_continuation is None,
                 'first-round-extra')
    request=generation_request(candidate)
    _require(hashlib.sha256(request).hexdigest()==value['request_sha256'],'request-pin')
    _require(type(run_directory) in (Path,type(Path('.'))),'directory-type')
    _require(run_directory.is_absolute() and run_directory.is_dir()
             and not run_directory.is_symlink()
             and run_directory.resolve(strict=True)==run_directory,'directory')
    prefix=run_directory/('round-'+str(value['round']))
    intent_path=Path(str(prefix)+'.send-intent.json')
    connection=_fixed_provider_connection(ca_pem,packet['public_ca_sha256'],deadline)
    intent=dict(label=LABEL,binding=value,sender_job_id=handoff['sender_job_id'],
                reservation=ack,qualification_evidence=False)
    try:
        _persist_new(intent_path,_canonical(intent))
        # Check the real wall window again immediately before the only exchange.
        _packet(packet_bytes,approved_packet_sha256,value)
        raw,transport=_exchange_once(connection,candidate,authorization,deadline)
        _persist_new(Path(str(prefix)+'.response.bin'),raw)
        proposal=response_proposal(raw,candidate)
        receipt=dict(label=LABEL,session_sha256=value['session_sha256'],
            packet_sha256=value['packet_sha256'],source_sha=value['source_sha'],
            round=value['round'],sender_job_id=handoff['sender_job_id'],
            stage='RESPONSE_VALIDATED',transport=transport,
            qualification_evidence=False)
        _persist_new(Path(str(prefix)+'.sender-receipt.json'),_canonical(receipt))
        return proposal,receipt
    finally:
        # The durable service reservation and local intent are never removed.
        # Failure means no resume. An uncertain provider outcome may be billed.
        connection.close()
