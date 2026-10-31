"""Unsigned engineering reservation bindings; no service writes or live entry.

These checks are necessary, not authentication. A future native caller must obtain
the exact approved packet and GitHub observations independently. Never use these
objects as Track B admission or as proof of a qualified production run.
"""
import hashlib
import json
import re

from lightyear_factory.contracts import ContractError
from tools.ci.supervised_intcalc_boundary import LABEL

REPOSITORY = 'howardweale/lightyear-carddemo-modernization'
PREFIX = 'refs/tags/factory-supervised-engineering-'
SHA256 = re.compile(r'[0-9a-f]{64}')
SHA1 = re.compile(r'[0-9a-f]{40}')
BINDING_FIELDS = frozenset(('label', 'session_sha256', 'packet_sha256',
    'source_sha', 'workflow_sha256', 'workflow_path', 'workflow_id', 'run_id',
    'run_attempt', 'sender_job_name', 'round', 'request_sha256',
    'previous_receipt_sha256', 'continuation_sha256', 'qualification_evidence'))


def _require(ok, reason):
    if not ok:
        raise ContractError('supervised-reservation-' + reason)


def _digest(value, pattern=SHA256):
    return type(value) is str and pattern.fullmatch(value) is not None


def _positive(value):
    return type(value) is int and 0 < value < 2**63


def checked_binding(value):
    _require(type(value) is dict and set(value) == BINDING_FIELDS, 'fields')
    _require(value['label'] == LABEL and value['qualification_evidence'] is False,
             'label')
    for key in ('session_sha256', 'packet_sha256', 'workflow_sha256',
                'request_sha256'):
        _require(_digest(value[key]), 'digest')
    _require(_digest(value['source_sha'], SHA1), 'source')
    _require(value['workflow_path'] ==
             '.github/workflows/supervised-intcalc-engineering.yml', 'workflow')
    for key in ('workflow_id', 'run_id'):
        _require(_positive(value[key]), 'native-id')
    _require(value['sender_job_name'] == 'supervised-sender', 'sender-role')
    _require(type(value['run_attempt']) is int and value['run_attempt'] == 1,
             'rerun')
    _require(type(value['round']) is int and value['round'] in (1, 2), 'round')
    if value['round'] == 1:
        _require(value['previous_receipt_sha256'] is None
                 and value['continuation_sha256'] is None, 'first-round')
    else:
        _require(_digest(value['previous_receipt_sha256'])
                 and _digest(value['continuation_sha256']), 'continuation')
    # Freeze against mutation of a caller-owned dictionary.
    return dict(value)


def canonical_record(binding):
    return json.dumps(checked_binding(binding), sort_keys=True,
                      separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def reservation_ref(binding):
    value = checked_binding(binding)
    # Deliberately exclude run/request IDs: another dispatch for this approved
    # session/round must collide with the same permanent create-only ref.
    return PREFIX + value['session_sha256'] + '-round-' + str(value['round'])


def checked_second_round(binding, previous_receipt, approved_continuation):
    value = checked_binding(binding)
    _require(value['round'] == 2, 'second-required')
    _require(type(previous_receipt) is bytes and 0 < len(previous_receipt) <= 65536,
             'previous-bytes')
    _require(hashlib.sha256(previous_receipt).hexdigest() ==
             value['previous_receipt_sha256'], 'previous-digest')
    # A native verifier/archival reader must supply these exact bytes; this
    # decoder is not an archival readback or verifier authenticity claim.
    def pairs(items):
        result = {}
        for key, item in items:
            _require(key not in result, 'previous-duplicate')
            result[key] = item
        return result
    try:
        receipt = json.loads(previous_receipt, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError('supervised-reservation-previous-json') from None
    fields = {'label', 'session_sha256', 'packet_sha256', 'source_sha',
              'round', 'outcome', 'qualification_evidence'}
    _require(type(receipt) is dict and set(receipt) == fields, 'previous-fields')
    _require(receipt['label'] == LABEL and receipt['qualification_evidence'] is False
             and receipt['session_sha256'] == value['session_sha256']
             and receipt['packet_sha256'] == value['packet_sha256']
             and receipt['source_sha'] == value['source_sha']
             and type(receipt['round']) is int and receipt['round'] == 1
             and receipt['outcome'] == 'FAIL', 'previous-verdict')
    _require(type(approved_continuation) is bytes
             and 0 < len(approved_continuation) <= 65536
             and hashlib.sha256(approved_continuation).hexdigest() ==
             value['continuation_sha256'], 'human-continuation')
    return value


def checked_create_ack(binding, expected_commit, status, response):
    """Only the successful response to THIS create-ref POST may pass.

    Existing refs (422), lost acknowledgements and later GETs are never adopted.
    No caller may retry a create or use this function to resume an attempt.
    """
    _require(_digest(expected_commit, SHA1), 'commit')
    _require(type(status) is int and status == 201, 'create-not-confirmed')
    _require(type(response) is dict, 'create-response')
    expected_ref = reservation_ref(binding)
    _require(response.get('ref') == expected_ref, 'create-ref')
    obj = response.get('object')
    _require(type(obj) is dict and obj.get('type') == 'commit'
             and obj.get('sha') == expected_commit, 'create-object')
    return {'label': LABEL, 'ref': expected_ref, 'commit': expected_commit,
            'record_sha256': hashlib.sha256(canonical_record(binding)).hexdigest(),
            'qualification_evidence': False}


def checked_sender_handoff(binding, stored_record, native_run, native_job,
                           all_jobs, workflow_bytes):
    """Bind the reserved role to one allocated native job after it starts.

    The native caller must independently fetch the exact workflow and every
    page for this run attempt. This function authenticates neither dictionaries
    nor the caller. The reviewed workflow must have one fixed sender, no matrix,
    one send entry, and an exclusive local intent before invoking that entry.
    """
    value = checked_binding(binding)
    _require(type(stored_record) is bytes
             and stored_record == canonical_record(value), 'stored-record')
    _require(type(workflow_bytes) is bytes and 0 < len(workflow_bytes) <= 131072
             and hashlib.sha256(workflow_bytes).hexdigest() ==
             value['workflow_sha256'], 'workflow-bytes')
    _require(type(native_run) is dict and type(native_job) is dict, 'native-record')
    repo = native_run.get('repository')
    _require(type(repo) is dict and repo.get('full_name') == REPOSITORY,
             'native-repository')
    for key in ('run_attempt', 'workflow_id'):
        _require(type(native_run.get(key)) is int and native_run[key] == value[key],
                 'native-run')
    _require(type(native_run.get('id')) is int
             and native_run['id'] == value['run_id']
             and native_run.get('head_sha') == value['source_sha']
             and native_run.get('event') == 'workflow_dispatch'
             and native_run.get('path') == value['workflow_path']
             and native_run.get('status') == 'in_progress', 'native-run')
    _require(type(all_jobs) is dict and set(all_jobs) == {'total_count','jobs'},
             'job-list')
    count, jobs = all_jobs['total_count'], all_jobs['jobs']
    _require(type(count) is int and 1 <= count <= 1000 and type(jobs) is list
             and len(jobs) == count, 'job-list-complete')
    ids = set()
    for job in jobs:
        _require(type(job) is dict and _positive(job.get('id'))
                 and job['id'] not in ids
                 and type(job.get('run_id')) is int
                 and job['run_id'] == value['run_id']
                 and type(job.get('run_attempt')) is int
                 and job['run_attempt'] == 1
                 and job.get('head_sha') == value['source_sha'], 'job-list-identity')
        ids.add(job['id'])
    candidates = [job for job in jobs if job.get('name') == value['sender_job_name']]
    _require(len(candidates) == 1 and candidates[0] == native_job, 'sender-unique')
    _require(native_job.get('status') == 'in_progress', 'native-job')
    return dict(binding=value, sender_job_id=native_job['id'],
                record_sha256=hashlib.sha256(stored_record).hexdigest(),
                label=LABEL, qualification_evidence=False)
