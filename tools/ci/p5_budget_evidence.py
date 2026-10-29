"""Retain synthetic controller accounting evidence without qualifying a run."""
import hashlib
import json
import math
from pathlib import Path

from lightyear_factory.contracts import canonical_hash

CASES = {'control': 2, 'dollar-preflight': 0, 'dollar-returned': 1,
         'token-preflight': 0, 'token-returned': 1,
         'failed-primary-no-fallback-authority': 1,
         'fallback-admitted': 2, 'fallback-model-refused': 1}


def validate(value, *, case, run_id, work_order_sha256):
    """Check exact retained bytes, call completeness and controller aggregates."""
    def require(ok):
        if not ok:
            raise ValueError('p5-budget-retained-evidence-invalid')

    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result)
            result[key] = item
        return result

    def document(kind, limit):
        text = value[kind+'_utf8']
        require(isinstance(text, str) and 0 < len(text.encode('utf-8')) <= limit)
        require(hashlib.sha256(text.encode('utf-8')).hexdigest() == value[kind+'_sha256'])
        return json.loads(text, object_pairs_hook=unique)

    try:
        require(case in CASES and value['case'] == case)
        require(value['schema'] == 'p5-retained-budget-evidence/1')
        require(value['origin'] == 'disposable CI controller with stub transport')
        require(value['run_id'] == run_id and value['work_order_sha256'] == work_order_sha256)
        receipt = document('receipt', 65536)
        identity = document('identity', 16384)
        calls = document('calls', 65536)
        for item in (receipt, identity):
            require(isinstance(item, dict))
            require(item['content_sha256'] == canonical_hash(item, {'content_sha256'}))
            require(item['work_order_sha256'] == work_order_sha256)
        require(identity['schema'] == 'factory-attempt-identity/1' and identity['attempt_id'] == run_id)
        require(receipt['status'] == 'blocked')
        if case == 'control':
            # _finish emits the normal BLOCKED control receipt without this field.
            # Bind that exact shape; absence is never a qualification assertion.
            require('qualifies_for_factory_receipt' not in receipt)
            require(receipt['run_id'] == run_id)
            require(receipt['receipt_type'] == 'lightyear-autonomous-factory-run')
            require('factory_build_receipt' not in receipt)
        else:
            require(receipt['qualifies_for_factory_receipt'] is False)
        require(isinstance(calls, list) and len(calls) == CASES[case])
        require(len({call['content_sha256'] for call in calls}) == len(calls))
        for index, call in enumerate(calls, 1):
            require(call['content_sha256'] == canonical_hash(call, {'content_sha256'}))
            require(type(call['call_sequence']) is int and call['call_sequence'] == index)
            for key in ('input_tokens', 'output_tokens'):
                require(type(call[key]) is int and call[key] >= 0)
            cost = call['estimated_cost_usd']
            require(type(cost) in (int, float) and math.isfinite(cost) and cost >= 0)
            require(call['cost_estimate_available'] is True)
        accounting = receipt['failure_accounting']
        require(accounting['schema'] == 'factory-sanitized-accounting/1')
        require(type(accounting['calls']) is int and accounting['calls'] == len(calls))
        for key in ('input_tokens', 'output_tokens', 'estimated_cost_usd'):
            require(accounting[key] == sum(call[key] for call in calls))
        require(accounting['call_hashes'] == [dict(request_sha256=call.get('request_sha256'),
                response_sha256=call.get('response_sha256')) for call in calls])
        require(accounting['billing_final'] is False)
        require(accounting['duration_basis'] == 'observed-through-checkpoint')
        require(type(accounting['duration_ms']) is int and accounting['duration_ms'] >= 0)
        # Retain uncertainty from failed transport; never convert it into zero/final billing.
        require(accounting['in_flight_final_usage'] in ('none', 'unknown'))
        if case in ('failed-primary-no-fallback-authority', 'fallback-admitted', 'fallback-model-refused'):
            require(calls[0]['status'] == 'failed' and calls[0]['usage'] == 'reserved-upper-bound')
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('p5-budget-retained-evidence-invalid') from None


def retain(run_directory, calls, *, case, run_id, work_order_sha256):
    """Read final controller files; call details remain separately labelled observer evidence."""
    root = Path(run_directory)
    raw = {'receipt': (root/'receipt.json').read_bytes(),
           'identity': (root/'attempt-identity.json').read_bytes(),
           'calls': json.dumps(calls, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')}
    value = dict(schema='p5-retained-budget-evidence/1',
        origin='disposable CI controller with stub transport', case=case,
        run_id=run_id, work_order_sha256=work_order_sha256)
    for kind, data in raw.items():
        value[kind+'_utf8'] = data.decode('utf-8')
        value[kind+'_sha256'] = hashlib.sha256(data).hexdigest()
    validate(value, case=case, run_id=run_id, work_order_sha256=work_order_sha256)
    return value
