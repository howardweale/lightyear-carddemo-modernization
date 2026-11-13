"""Check retained disposable workspace race evidence without changing qualification."""
import hashlib
import json
import re

from lightyear_factory.contracts import canonical_hash
from tools.ci.p5_budget_evidence import validate as validate_budget


def validate(value, *, case, work_order_sha256):
    def require(ok):
        if not ok: raise ValueError('p5-workspace-evidence-invalid')
    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result); result[key] = item
        return result
    def text(kind):
        raw = value[kind+'_utf8']
        require(isinstance(raw, str) and 0 < len(raw.encode()) < 50000)
        require(hashlib.sha256(raw.encode()).hexdigest() == value[kind+'_sha256'])
        return raw
    def document(kind):
        result = json.loads(text(kind), object_pairs_hook=unique)
        require(result['content_sha256'] == canonical_hash(result, {'content_sha256'}))
        return result
    try:
        require(case in ('clean', 'read-mutation') and value['case'] == case)
        run_id = 'p5-workspace-'+case
        require(value['schema'] == 'p5-retained-workspace-evidence/1')
        require(value['origin'] == 'disposable CI controller; mutation after real file read before post-read fstat')
        require(value['run_id'] == run_id and value['work_order_sha256'] == work_order_sha256)
        require(value['controller_refused'] is (case != 'clean'))
        require(value['transport_roles'] == (['planner', 'builder'] if case == 'clean' else ['planner']))
        require(type(value['transport_calls']) is int and value['transport_calls'] == len(value['transport_roles']))
        for field in ('source_before_sha256', 'source_after_sha256', 'workspace_after_sha256'):
            require(isinstance(value[field], str) and re.fullmatch('[0-9a-f]{64}', value[field]))
        require(value['source_before_sha256'] == value['source_after_sha256'])
        require(value['reads'] == [value['source_before_sha256']])
        expected = [dict(surface='initial-workspace', outcome='passed'),
                    dict(surface='builder-workspace', outcome='passed' if case == 'clean' else 'workspace-isolation-refused')]
        if case == 'clean':
            expected.append(dict(surface='final-candidate-package', outcome='passed'))
        require(value['boundaries'] == expected)
        if case == 'clean':
            require(value['injections'] == [] and value['workspace_after_sha256'] == value['source_before_sha256'])
            require(validate_budget(value['clean_control'], case='control', run_id=run_id, work_order_sha256=work_order_sha256))
            return True
        require(len(value['injections']) == 1)
        injection = value['injections'][0]
        require(injection['before_sha256'] == value['source_before_sha256'])
        require(injection['after_sha256'] == value['workspace_after_sha256'] != injection['before_sha256'])
        require(type(injection['before_bytes']) is int and type(injection['after_bytes']) is int)
        require(0 < injection['before_bytes'] < injection['after_bytes'])
        receipt, identity = document('receipt'), document('identity')
        require(receipt['status'] == 'blocked' and receipt['qualifies_for_factory_receipt'] is False)
        require(receipt['receipt_type'] == 'lightyear-autonomous-factory-run' and 'factory_build_receipt' not in receipt)
        require(receipt['reason'] == 'factory-isolation-run-refused' and receipt['attempts'] == 1)
        require(receipt['work_order_sha256'] == identity['work_order_sha256'] == work_order_sha256)
        require(identity['schema'] == 'factory-attempt-identity/1' and identity['attempt_id'] == run_id)
        calls = json.loads(text('calls'), object_pairs_hook=unique)
        require(isinstance(calls, list) and len(calls) == 1)
        call = calls[0]
        require(call['call_sequence'] == 1 and type(call['call_sequence']) is int)
        require(call['content_sha256'] == canonical_hash(call, {'content_sha256'}))
        require(call['cost_estimate_available'] is True)
        a = receipt['failure_accounting']
        require(a['schema'] == 'factory-sanitized-accounting/1' and type(a['calls']) is int and a['calls'] == 1)
        for key in ('input_tokens', 'output_tokens'):
            require(type(call[key]) is int and type(a[key]) is int and a[key] == call[key] == 1)
        require(a['estimated_cost_usd'] == call['estimated_cost_usd'] == 0)
        require(a['call_hashes'] == [dict(request_sha256=call.get('request_sha256'), response_sha256=call.get('response_sha256'))])
        require(a['billing_final'] is False and a['in_flight_final_usage'] == 'none')
        require(a['duration_basis'] == 'observed-through-checkpoint' and type(a['duration_ms']) is int and a['duration_ms'] >= 0)
        require(len(a['scanned_transports']) == 1 and a['scanned_transports'][0]['role'] == 'planner')
        require(all(re.fullmatch('[0-9a-f]{64}', a['scanned_transports'][0][key]) for key in ('prompt_sha256', 'response_sha256')))
        ledger = text('ledger'); require(ledger.endswith('\n') and all(row.strip() for row in ledger.splitlines()))
        events = [json.loads(row, object_pairs_hook=unique) for row in ledger.splitlines()]
        previous = None
        for sequence, event in enumerate(events, 1):
            require(type(event['sequence']) is int and event['sequence'] == sequence and event['previous_sha256'] == previous)
            require(event['event_sha256'] == canonical_hash(event, {'event_sha256'})); previous = event['event_sha256']
        require(previous == receipt['ledger_head_sha256'])
        require(events[-1]['state'] == 'BLOCKED' and events[-1]['kind'] == 'controller_error')
        require(events[-1]['payload'] == {'reason': 'factory-isolation-run-refused'})
        require(any(e['kind'] == 'work_order_accepted' and e['payload']['work_order_sha256'] == work_order_sha256 for e in events))
        require(any(e['kind'] == 'hardened_admission_bound' and e['payload']['admission_receipt_sha256'] == identity['admission_receipt_sha256'] for e in events))
        require(any(e['kind'] == 'workspace_read_manifest' and e['payload']['sha256'] == identity['workspace_inventory_sha256'] for e in events))
        return True
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        raise ValueError('p5-workspace-evidence-invalid') from None
