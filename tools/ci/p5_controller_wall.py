"""CI-only controller elapsed-clock probe; never a production timing claim."""
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator
from tools.ci.p5_budget_evidence import retain as retain_budget, validate as validate_budget
from tools.ci.p5_controller_budgets import BudgetStub
from tools.ci.p5_fixture import Fixture

CASES = ('clean', 'past-wall')


def validate(value):
    def require(ok):
        if not ok:
            raise ValueError('p5-wall-evidence-invalid')
    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result)
            result[key] = item
        return result
    def text(kind):
        raw = value[kind+'_utf8']
        require(isinstance(raw, str) and 0 < len(raw.encode()) < 50000)
        require(hashlib.sha256(raw.encode()).hexdigest() == value[kind+'_sha256'])
        return raw
    def document(kind):
        doc = json.loads(text(kind), object_pairs_hook=unique)
        require(doc['content_sha256'] == canonical_hash(doc, {'content_sha256'}))
        return doc
    try:
        case = value['case']; run_id = 'p5-wall-'+case
        require(case in CASES and value['run_id'] == run_id)
        require(value['schema'] == 'p5-controller-wall-observation/1')
        require(value['clock_scope'] == 'controller module only, advanced after real plan_created append')
        require(value['real_model_calls'] == value['actual_spend'] == 0)
        require(type(value['wall_seconds']) is int and value['wall_seconds'] > 0)
        require(value['source_before_sha256'] == value['source_after_sha256'])
        require(value['plan_created_count'] == 1 and type(value['plan_created_count']) is int)
        expected_roles = ['planner', 'builder'] if case == 'clean' else ['planner']
        require(value['transport_roles'] == expected_roles)
        require(type(value['transport_calls']) is int and value['transport_calls'] == len(expected_roles))
        require(value['controller_refused'] is (case == 'past-wall'))
        require(value['clock_delta_seconds'] == (0 if case == 'clean' else value['wall_seconds']+1))
        require(value['failure_causes'] == ([] if case == 'clean' else ['Factory exceeded max_elapsed_seconds']))
        if case == 'clean':
            require(validate_budget(value['clean_control'], case='control', run_id=run_id,
                                    work_order_sha256=value['work_order_sha256']))
            return True
        receipt, identity = document('receipt'), document('identity')
        require(receipt['status'] == 'blocked' and receipt['qualifies_for_factory_receipt'] is False)
        require(receipt['receipt_type'] == 'lightyear-autonomous-factory-run')
        require('factory_build_receipt' not in receipt and receipt['attempts'] == 0)
        require(receipt['reason'] == 'factory-isolation-run-refused')
        require(receipt['work_order_sha256'] == identity['work_order_sha256'] == value['work_order_sha256'])
        require(identity['schema'] == 'factory-attempt-identity/1' and identity['attempt_id'] == run_id)
        calls = json.loads(text('calls'), object_pairs_hook=unique)
        require(isinstance(calls, list) and len(calls) == 1)
        call = calls[0]
        require(call['call_sequence'] == 1 and type(call['call_sequence']) is int)
        require(call['content_sha256'] == canonical_hash(call, {'content_sha256'}))
        require(call['role'] == 'planner' and call['cost_estimate_available'] is True)
        a = receipt['failure_accounting']
        require(a['schema'] == 'factory-sanitized-accounting/1' and type(a['calls']) is int and a['calls'] == 1)
        for key in ('input_tokens', 'output_tokens'):
            require(type(a[key]) is int and type(call[key]) is int and a[key] == call[key] == 1)
        require(a['estimated_cost_usd'] == call['estimated_cost_usd'] == 0)
        require(a['call_hashes'] == [dict(request_sha256=call.get('request_sha256'), response_sha256=call.get('response_sha256'))])
        require(a['billing_final'] is False and a['in_flight_final_usage'] == 'none')
        require(a['duration_basis'] == 'observed-through-checkpoint')
        require(type(a['duration_ms']) is int and a['duration_ms'] == (value['wall_seconds']+1)*1000)
        require(len(a['scanned_transports']) == 1 and a['scanned_transports'][0]['role'] == 'planner')
        raw = text('ledger'); require(raw.endswith('\n'))
        events = [json.loads(row, object_pairs_hook=unique) for row in raw.splitlines()]
        previous = None
        for index, event in enumerate(events, 1):
            require(type(event['sequence']) is int and event['sequence'] == index)
            require(event['previous_sha256'] == previous)
            require(event['event_sha256'] == canonical_hash(event, {'event_sha256'}))
            previous = event['event_sha256']
        require(previous == receipt['ledger_head_sha256'])
        require(sum(e['kind'] == 'plan_created' for e in events) == 1)
        require(not any(e['kind'] in ('build_proposed', 'builder_blocked') for e in events))
        require(events[-1]['kind'] == 'controller_error' and events[-1]['state'] == 'BLOCKED')
        require(events[-1]['payload'] == {'reason': 'factory-isolation-run-refused'})
        require(any(e['kind'] == 'work_order_accepted' and e['payload']['work_order_sha256'] == value['work_order_sha256'] for e in events))
        require(any(e['kind'] == 'hardened_admission_bound' and e['payload']['admission_receipt_sha256'] == identity['admission_receipt_sha256'] for e in events))
        require(any(e['kind'] == 'workspace_read_manifest' and e['payload']['sha256'] == identity['workspace_inventory_sha256'] for e in events))
        return True
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        raise ValueError('p5-wall-evidence-invalid') from None


def observe_case(parent, repository, case):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or case not in CASES:
        raise ValueError('p5-wall-ci-only')
    parent = Path(parent); parent.mkdir()
    fixture = Fixture(parent, repository, controller_probe=True)
    try:
        roles = []; causes = []; plans = []; clock = [1000.0]
        class RecordingStub(BudgetStub):
            def complete(self, role, instruction, payload, schema):
                roles.append(role)
                return super().complete(role, instruction, payload, schema)
        stub = RecordingStub('control', fixture.order); agents = ModelAgentSet(stub)
        _, admission = fixture.verify_order()
        context = HardenedExecutionContext(fixture.policy,
            OCIContainerBackend(fixture.policy, 'docker', execute=False), admission, fixture.key)
        runs = parent/'runs'; run_id = 'p5-wall-'+case
        source = fixture.root/'worker.py'; original = source.read_bytes()
        controller = FactoryOrchestrator(fixture.root, runs, agents,
            execution_context=context, model_admission=fixture.admission,
            factory_input_paths=fixture.input_paths,
            workspace_read_manifest=fixture.runtime()['workspace_read_manifest'],
            private_expected_values_path=fixture.private_values_path)
        real_append = RunLedger.append
        real_failure = FactoryOrchestrator._record_isolation_failure
        def append(ledger, state, kind, payload):
            result = real_append(ledger, state, kind, payload)
            if kind == 'plan_created':
                if plans or roles != ['planner']:
                    raise ValueError('p5-wall-plan-boundary')
                plans.append(kind)
                if case == 'past-wall':
                    clock[0] += fixture.order.max_elapsed_seconds+1
            return result
        def record_failure(instance, *args, **kwargs):
            cause = sys.exc_info()[1]
            causes.append(str(cause))
            if type(cause) is not ContractError or str(cause) != 'Factory exceeded max_elapsed_seconds':
                raise ValueError('p5-wall-wrong-underlying-refusal')
            return real_failure(instance, *args, **kwargs)
        refused = False
        # Replace only this module's clock reference. Provider, verifier and
        # global time retain their real clocks; all controller logic delegates.
        with patch('lightyear_factory.orchestrator.time', SimpleNamespace(monotonic=lambda: clock[0])), \
                patch.object(RunLedger, 'append', append), \
                patch.object(FactoryOrchestrator, '_record_isolation_failure', record_failure):
            try:
                controller.run(fixture.order, run_id)
            except ContractError as error:
                if str(error) != 'factory-isolation-run-refused':
                    raise ValueError('p5-wall-wrong-controller-refusal') from None
                refused = True
        if causes != ([] if case == 'clean' else ['Factory exceeded max_elapsed_seconds']):
            raise ValueError('p5-wall-wrong-underlying-refusal')
        budget = agents.bounded_provider
        if type(budget) is not AccountedModelProvider or stub.calls != len(budget.calls):
            raise ValueError('p5-wall-accounted-provider-required')
        digest = lambda raw: hashlib.sha256(raw).hexdigest()
        value = dict(schema='p5-controller-wall-observation/1', case=case, run_id=run_id,
            clock_scope='controller module only, advanced after real plan_created append',
            wall_seconds=fixture.order.max_elapsed_seconds, clock_delta_seconds=clock[0]-1000,
            work_order_sha256=fixture.order.content_sha256, plan_created_count=len(plans),
            source_before_sha256=digest(original), source_after_sha256=digest(source.read_bytes()),
            controller_refused=refused, failure_causes=causes, transport_roles=roles,
            transport_calls=stub.calls, real_model_calls=0, actual_spend=0)
        directory = runs/run_id
        if case == 'clean':
            value['clean_control'] = retain_budget(directory, budget.calls, case='control',
                run_id=run_id, work_order_sha256=fixture.order.content_sha256)
        else:
            for kind, filename in (('receipt', 'receipt.json'), ('identity', 'attempt-identity.json'), ('ledger', 'events.jsonl')):
                raw = (directory/filename).read_bytes()
                value[kind+'_utf8'], value[kind+'_sha256'] = raw.decode(), digest(raw)
            raw = json.dumps(budget.calls, sort_keys=True, separators=(',', ':'), allow_nan=False)
            value['calls_utf8'], value['calls_sha256'] = raw, digest(raw.encode())
        validate(value)
        return value
    finally:
        fixture.close()


def validate_collection(rows):
    if (not isinstance(rows, list) or len(rows) != len(CASES)
            or not all(isinstance(row, dict) for row in rows)
            or tuple(row.get('case') for row in rows) != CASES):
        raise ValueError('p5-wall-collection-invalid')
    if not all(validate(row) is True for row in rows):
        raise ValueError('p5-wall-collection-invalid')
    return True


def observe(fixture, repository):
    root = fixture.parent/'wall-controller-probes'
    root.mkdir()
    rows = [observe_case(root/case, repository, case) for case in CASES]
    validate_collection(rows)
    return rows
