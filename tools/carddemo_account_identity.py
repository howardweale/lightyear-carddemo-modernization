"""Validate bound receipt identity and unsigned scope; no execution authority."""
from datetime import date, datetime
import json
import re

PROGRAMS = ['COSGN00C', 'COMEN01C', 'COACTVWC', 'COACTUPC', 'COPAUS0C', 'COPAUS1C']
GATES = {'api-reference', 'browser', 'browser-reference', 'ci-jobs', 'mutation', 'mutation-reference'}
REQUEST = {'action': 'review evidence and remaining gaps', 'activation_authorized': False,
           'phase2_authorized': False, 'reviewer': 'Howard', 'signature': None,
           'status': 'unsigned-review-request'}
JOBS = {'compose-smoke', 'full-slice-proof', 'source-and-service-foundation'}


def _equal(actual, expected):
    return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False)


def verify_receipt_identity(receipt, run, source_head, tested_commit):
    """Caller must bind all inputs and independently verify Git parents/tree and workflow jobs."""
    if not isinstance(receipt, dict) or not isinstance(run, dict):
        raise ValueError('account-receipt-shape')
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value)
           for value in (source_head, tested_commit)):
        raise ValueError('account-receipt-commit')
    if (receipt.get('source_head') != source_head or receipt.get('tested_commit') != tested_commit
            or run.get('head_sha') != source_head):
        raise ValueError('account-receipt-head')
    run_id = run.get('id')
    if type(run_id) is not int or run_id <= 0 or receipt.get('run_id') != str(run_id):
        raise ValueError('account-receipt-run')
    if (run.get('event') != 'pull_request' or run.get('status') != 'completed'
            or run.get('conclusion') != 'success' or run.get('path') != '.github/workflows/carddemo-web.yml'
            or not isinstance(run.get('repository'), dict)
            or run['repository'].get('full_name') != 'howardweale/lightyear-carddemo-modernization'
            or type(run.get('run_attempt')) is not int or run['run_attempt'] <= 0):
        raise ValueError('account-receipt-workflow')
    if (receipt.get('schema') != 'carddemo-slice-receipt/1' or receipt.get('status') != 'proved-in-ci'
            or receipt.get('unsigned') is not True or receipt.get('acceptance_complete') is not True
            or not _equal(receipt.get('factory_request'), REQUEST)
            or not _equal(receipt.get('remaining_evidence_gaps'), [])):
        raise ValueError('account-receipt-authority')
    original_date = receipt.get('date')
    if not isinstance(original_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', original_date):
        raise ValueError('account-receipt-date')
    date.fromisoformat(original_date)
    scope = receipt.get('scope')
    if not isinstance(scope, dict) or not _equal(scope.get('programs'), PROGRAMS):
        raise ValueError('account-receipt-programs')
    gates = receipt.get('gates')
    if not isinstance(gates, dict) or set(gates) != GATES:
        raise ValueError('account-receipt-gates')
    if any(not isinstance(gate, dict) or gate.get('passed') is not True for gate in gates.values()):
        raise ValueError('account-receipt-gate-status')
    expected_ci = {'passed': True, 'results': {key: {'outputs': {}, 'result': 'success'} for key in JOBS}}
    if not _equal(gates['ci-jobs'], expected_ci):
        raise ValueError('account-receipt-ci-jobs')
    measured = run.get('run_started_at', run.get('created_at'))
    if not isinstance(measured, str): raise ValueError('account-receipt-measurement-date')
    measurement_date = datetime.fromisoformat(measured.replace('Z', '+00:00')).date().isoformat()
    return {'source_head': source_head, 'tested_commit': tested_commit, 'run_id': run_id,
            'measurement_date': measurement_date,
            'run_attempt': run['run_attempt'], 'original_receipt_date': original_date,
            'unsigned': True, 'activation_authorized': False, 'phase2_authorized': False}
