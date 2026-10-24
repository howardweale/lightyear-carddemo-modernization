"""Synthetic CI: real routing approval remains subordinate to F2 admission."""
from datetime import timedelta
import json
import os
from pathlib import Path
import uuid

from lightyear_control_tower.console import ConsoleService, provision
from lightyear_control_tower.decisions import digest
from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.annotation_tools import review_request
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.routing import TaskRouter, admitted_policy
from lightyear_factory.routing_policy import compile_policy
from tools.ci.p5_controller_budgets import BudgetStub
from tools.ci.p5_controller_probe import inspect_receipt
from tools.ci.p5_fixture import Fixture


def observe(parent, repository, *, changed_fallback_model=False):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('p5-ci-fallback-only')
    parent = Path(parent)
    parent.mkdir()
    fixture = Fixture(parent, Path(repository), controller_probe=True)
    service = None
    try:
        root = parent/'routing-authority-data'
        root.mkdir()
        credential = provision(parent/'routing-authority'/'authority.json',
            'graph-memory', 'p5-routing', 'Disposable routing CI').read_text().strip()
        service = ConsoleService(root, parent/'routing-authority'/'authority.json')
        service.grant_roles('p5-routing', ['operator', 'campaign-authorizer'],
                            reason='Synthetic CI routing only')
        token = service.login(credential)['token']
        primary = BudgetStub('failed-primary-no-fallback-authority', fixture.order)
        secondary = BudgetStub('control', fixture.order)
        if changed_fallback_model:
            secondary.model = 'p5-other-2026-10-23'
        providers = {'primary': primary, 'secondary': secondary}
        matrix = dict(schema='factory-evaluation-matrix/1', false_acceptances=0,
            cells=[dict(model=name, model_version=p.model, task_type='plan',
                workload='P5-SYNTHETIC', run_count=35, passed=35, false_acceptances=0,
                cost_per_verified_task=index+1,
                runs=[name+str(i) for i in range(35)],
                pair_ids=[str(i) for i in range(35)],
                paired_outcomes={str(i): True for i in range(35)})
                for index, (name, p) in enumerate(providers.items())])
        matrix['content_sha256'] = digest(matrix)
        policy = compile_policy(matrix, margin=.1)
        if policy['routes']['plan']['fallback'] != 'secondary':
            raise ValueError('p5-fallback-policy-fixture')
        request = review_request(root, 'graph-memory', 'model-routing-policy',
                                 dict(policy=policy, matrix_receipt=matrix))
        item = service.review(token, request['id'])
        event = service.decide(token, dict(item_id=item['id'], bound=item['bound'],
            outcome='approved', reason='Synthetic routing only; not run authority',
            named_owner='Disposable P5 CI',
            review_after=(fixture.now+timedelta(days=1)).date().isoformat(),
            previous_decision_sha256=None, request_id=str(uuid.uuid4())))
        proof = service.proof(token, event['content_sha256'])
        trust = dict(tower_key=service.public_key.decode(), scope='graph-memory',
                     trusted_head=proof['journal']['journal_head_sha256'])
        if admitted_policy(policy, matrix, proof, trust,
                versions={n:p.model for n,p in providers.items()}) is None:
            raise ValueError('p5-fallback-real-approval-refused')
        agents = ModelAgentSet(TaskRouter(providers, 'primary', policy=policy,
                                         matrix=matrix, proof=proof, trust=trust))
        _, admission = fixture.verify_order()
        context = HardenedExecutionContext(fixture.policy,
            OCIContainerBackend(fixture.policy, 'docker', execute=False), admission, fixture.key)
        controller = FactoryOrchestrator(fixture.root, parent/'runs', agents,
            execution_context=context, model_admission=fixture.admission,
            factory_input_paths=fixture.input_paths,
            workspace_read_manifest=fixture.runtime()['workspace_read_manifest'],
            private_expected_values_path=fixture.private_values_path)
        try:
            controller.run(fixture.order, 'fallback-probe')
        except ContractError as error:
            if str(error) != 'factory-isolation-run-refused':
                raise ValueError('p5-fallback-wrong-refusal') from None
        else:
            raise ValueError('p5-fallback-missing-refusal')
        routed = agents.bounded_provider
        budget = routed.budget
        expected_secondary = 0 if changed_fallback_model else 1
        if (type(budget) is not AccountedModelProvider or primary.calls != 1
                or secondary.calls != expected_secondary
                or len(budget.calls) != 1+expected_secondary
                or budget.calls[0].get('status') != 'failed'
                or budget.calls[0].get('usage') != 'reserved-upper-bound'
                or budget.estimated_cost_usd <= 0):
            raise ValueError('p5-fallback-accounting-or-admission')
        if ([r['model'] for r in routed.routing[:2]] != ['primary', 'secondary']
                or not routed.routing[1]['fallback']
                or any(r['policy_sha256'] != digest(policy) for r in routed.routing[:2])):
            raise ValueError('p5-fallback-route-binding')
        if len(routed.routing) != (2 if changed_fallback_model else 3):
            raise ValueError('p5-fallback-next-call-boundary')
        if not changed_fallback_model and routed.routing[2]['task_type'] != 'repair-from-closed-diagnostic':
            raise ValueError('p5-fallback-builder-not-reached')
        path = parent/'runs'/'fallback-probe'/'receipt.json'
        receipt = inspect_receipt(path)
        raw = json.loads(path.read_bytes())
        if raw.get('work_order_sha256') != fixture.order.content_sha256:
            raise ValueError('p5-fallback-receipt-binding')
        return dict(changed_fallback_model=changed_fallback_model,
            routing_approval_verified=True, policy_sha256=digest(policy),
            primary_calls=primary.calls, secondary_calls=secondary.calls,
            accounted_calls=len(budget.calls), shared_call_cap=fixture.order.max_model_calls,
            simulated_accounted_cost_usd=budget.estimated_cost_usd,
            controller_receipt=receipt,
            receipt_has_model_accounting='calls' in raw.get('intelligence', {}),
            real_model_calls=0, actual_spend=0)
    finally:
        if service is not None:
            service.close()
        fixture.close()
