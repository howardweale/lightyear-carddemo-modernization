"""Validate retained disposable context observations; never qualify a factory run."""
import hashlib
import json
import re

from lightyear_factory.contracts import canonical_hash
from tools.ci.p5_budget_evidence import validate as validate_budget

CASES = ('clean', 'normalized', 'base64', 'hex')
ORIGIN = 'disposable CI controller; real assembler and scanner; synthetic input injection'


def validate(value, *, case, work_order_sha256):
    def require(ok):
        if not ok:
            raise ValueError('p5-context-evidence-invalid')

    def digest(raw):
        return hashlib.sha256(raw).hexdigest()

    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result)
            result[key] = item
        return result

    def text(kind):
        raw = value[kind+'_utf8']
        require(isinstance(raw, str) and 0 < len(raw.encode('utf-8')) < 50000)
        require(digest(raw.encode('utf-8')) == value[kind+'_sha256'])
        return raw

    def document(kind):
        result = json.loads(text(kind), object_pairs_hook=unique)
        require(isinstance(result, dict))
        require(result['content_sha256'] == canonical_hash(result, {'content_sha256'}))
        return result

    def is_hash(item):
        return isinstance(item, str) and re.fullmatch('[0-9a-f]{64}', item)

    try:
        require(case in CASES and value['case'] == case)
        run_id = 'p5-context-'+case
        require(value['schema'] == 'p5-retained-context-evidence/1' and value['origin'] == ORIGIN)
        require(value['run_id'] == run_id and value['work_order_sha256'] == work_order_sha256)
        require(value['controller_refused'] is (case != 'clean'))
        require(type(value['transport_calls']) is int and value['transport_calls'] == (2 if case == 'clean' else 0))
        assembly = value['assembly']
        require(assembly['injection_boundary'] == 'copied worker.py immediately before real assemble')
        require(assembly['source_before_sha256'] == assembly['source_after_sha256'] == assembly['workspace_before_sha256'])
        require(assembly['assembled_file_sha256'] == assembly['workspace_after_sha256'])
        for key in ('source_before_sha256', 'source_after_sha256', 'workspace_before_sha256',
                    'workspace_after_sha256', 'assembled_file_sha256', 'context_sha256'):
            require(is_hash(assembly[key]))
        require((assembly['workspace_before_sha256'] == assembly['workspace_after_sha256']) is (case == 'clean'))
        scans = value['scanner_observations']
        require(isinstance(scans, list) and 2 <= len(scans) <= 100)
        require(all(set(row) == {'surface', 'sha256', 'outcome'} and isinstance(row['surface'], str)
                    and is_hash(row['sha256']) and row['outcome'] in ('passed', 'isolation-breach') for row in scans))
        contexts = [i for i, row in enumerate(scans) if row['surface'] == 'controller-context']
        require(len(contexts) == 1)
        at = contexts[0]
        require(any(row == dict(surface='initial-workspace-file', sha256=assembly['workspace_before_sha256'],
                                outcome='passed') for row in scans[:at]))
        require(scans[at] == dict(surface='controller-context', sha256=assembly['context_sha256'],
                                 outcome='passed' if case == 'clean' else 'isolation-breach'))
        if case == 'clean':
            require(all(row['outcome'] == 'passed' for row in scans))
            require(validate_budget(value['clean_control'], case='control', run_id=run_id,
                                    work_order_sha256=work_order_sha256))
            return True
        require(at == len(scans)-1 and all(row['outcome'] == 'passed' for row in scans[:at]))
        receipt, identity = document('receipt'), document('identity')
        require(receipt['receipt_type'] == 'lightyear-autonomous-factory-run')
        require(receipt['status'] == 'blocked' and receipt['qualifies_for_factory_receipt'] is False)
        require(receipt['reason'] == 'factory-isolation-run-refused' and receipt['attempts'] == 0)
        require('factory_build_receipt' not in receipt)
        require(receipt['work_order_sha256'] == identity['work_order_sha256'] == work_order_sha256)
        require(identity['schema'] == 'factory-attempt-identity/1' and identity['attempt_id'] == run_id)
        for key in ('consumed_nonce_sha256', 'sealed_workspace_sha256', 'admission_receipt_sha256',
                    'workspace_inventory_sha256'):
            require(is_hash(identity[key]))
        accounting = receipt['failure_accounting']
        require(accounting['schema'] == 'factory-sanitized-accounting/1')
        for key in ('calls', 'input_tokens', 'output_tokens'):
            require(type(accounting[key]) is int and accounting[key] == 0)
        require(type(accounting['estimated_cost_usd']) in (int, float) and accounting['estimated_cost_usd'] == 0)
        require(accounting['call_hashes'] == accounting['scanned_transports'] == [])
        require(accounting['in_flight_final_usage'] == 'none' and accounting['billing_final'] is False)
        require(accounting['duration_basis'] == 'observed-through-checkpoint')
        require(type(accounting['duration_ms']) is int and accounting['duration_ms'] >= 0)
        ledger = text('ledger')
        require(ledger.endswith('\n') and all(line.strip() for line in ledger.splitlines()))
        events = [json.loads(line, object_pairs_hook=unique) for line in ledger.splitlines()]
        previous = None
        for index, event in enumerate(events, 1):
            require(type(event['sequence']) is int and event['sequence'] == index)
            require(event['previous_sha256'] == previous)
            require(event['event_sha256'] == canonical_hash(event, {'event_sha256'}))
            previous = event['event_sha256']
        require(previous == receipt['ledger_head_sha256'])
        require(events[-1]['kind'] == 'controller_error' and events[-1]['state'] == 'BLOCKED')
        require(events[-1]['payload'] == {'reason': 'factory-isolation-run-refused'})
        require(any(e['kind'] == 'work_order_accepted' and e['payload']['work_order_sha256'] == work_order_sha256 for e in events))
        require(any(e['kind'] == 'hardened_admission_bound' and e['payload']['admission_receipt_sha256'] == identity['admission_receipt_sha256'] for e in events))
        require(any(e['kind'] == 'workspace_read_manifest' and e['payload']['sha256'] == identity['workspace_inventory_sha256'] for e in events))
        recorded = [dict(surface=row['artifact'], sha256=row['sha256'], outcome='passed')
                    for e in events if e['kind'] == 'model_isolation_scan_passed' for row in e['payload']['scanned']]
        require(recorded == scans[:at])
        return True
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        raise ValueError('p5-context-evidence-invalid') from None
