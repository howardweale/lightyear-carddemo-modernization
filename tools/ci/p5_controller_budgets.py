"""Synthetic CI probes of the real controller's budget refusal and receipts."""
import hashlib
import json
import os
from pathlib import Path

from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.providers import ProviderError, ProviderResult
from lightyear_factory.routing import RoutedBudget, TaskRouter
from tools.ci.p5_controller_probe import inspect_receipt
from tools.ci.p5_fixture import Fixture

CASES = ('control', 'dollar-preflight', 'dollar-returned', 'token-preflight',
         'token-returned', 'failed-primary-no-fallback-authority')


class BudgetStub:
    provider_id = 'p5-stub'
    model = 'p5-stub-2026-10-23'
    manage_failure_budget = True
    input_usd_per_million = 1.0
    output_usd_per_million = 1.0
    max_output_tokens = 16

    def __init__(self, case, order):
        self.case, self.order, self.calls = case, order, 0
        if case == 'dollar-preflight':
            self.input_usd_per_million = 1_000_000.0
        if case == 'token-preflight':
            self.max_output_tokens = order.max_model_tokens + 1

    def complete(self, role, instruction, payload, schema):
        self.calls += 1
        if self.case == 'failed-primary-no-fallback-authority':
            raise ProviderError(role, 'p5-synthetic-primary-failure')
        if role == 'planner':
            value = dict(summary='Synthetic controller budget plan', risks=[], tasks=[dict(
                id='synthetic', objective='Observe budget refusal', paths=['worker.py'],
                graph_node_ids=[], evidence_capsule_ids=[])])
        elif role == 'builder':
            value = dict(summary='Synthetic no-edit control', edits=[], blocked_reason='Synthetic stop')
        else:
            raise ValueError('p5-budget-unexpected-role')
        tokens = self.order.max_model_tokens + 1 if self.case == 'token-returned' else 1
        cost = self.order.max_model_cost_usd + 0.01 if self.case == 'dollar-returned' else 0.0
        return ProviderResult(value, dict(input_tokens=tokens, output_tokens=1,
            estimated_cost_usd=cost, cost_estimate_available=True, provider=self.provider_id,
            model=self.model, role=role))


def observe_case(parent, repository, case):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or case not in CASES:
        raise ValueError('p5-ci-budget-case-refused')
    parent = Path(parent)
    parent.mkdir()
    fixture = Fixture(parent, repository, controller_probe=True)
    try:
        primary = BudgetStub(case, fixture.order)
        secondary = BudgetStub('control', fixture.order)
        routed = case == 'failed-primary-no-fallback-authority'
        # No routing proof is supplied: real routing must not invent permission
        # to call the available secondary after a failed primary.
        provider = TaskRouter({'primary': primary, 'secondary': secondary}, 'primary') if routed else primary
        agents = ModelAgentSet(provider)
        _, admission = fixture.verify_order()
        context = HardenedExecutionContext(fixture.policy,
            OCIContainerBackend(fixture.policy, 'docker', execute=False), admission, fixture.key)
        runs = parent/'runs'
        controller = FactoryOrchestrator(fixture.root, runs, agents,
            execution_context=context, model_admission=fixture.admission,
            factory_input_paths=fixture.input_paths,
            workspace_read_manifest=fixture.runtime()['workspace_read_manifest'],
            private_expected_values_path=fixture.private_values_path)
        refused = False
        try:
            controller.run(fixture.order, 'p5-budget-'+case)
        except ContractError as error:
            if str(error) != 'factory-isolation-run-refused':
                raise ValueError('p5-budget-wrong-refusal') from None
            refused = True
        bounded = agents.bounded_provider
        if routed:
            if type(bounded) is not RoutedBudget:
                raise ValueError('p5-budget-router-path')
            budget = bounded.budget
        else:
            budget = bounded
        # This also fails when a future F2 controller regression constructs the
        # base class, even if the particular preflight refusal still works.
        if type(budget) is not AccountedModelProvider:
            raise ValueError('p5-budget-base-provider-path')
        expected_calls = 2 if case == 'control' else 0 if case.endswith('preflight') else 1
        path = runs/('p5-budget-'+case)/'receipt.json'
        receipt = inspect_receipt(path)
        raw_receipt = json.loads(path.read_bytes())
        if raw_receipt.get('work_order_sha256') != fixture.order.content_sha256:
            raise ValueError('p5-budget-receipt-order-binding')
        if (refused != (case != 'control') or primary.calls != expected_calls
                or len(budget.calls) != expected_calls or secondary.calls != 0):
            raise ValueError('p5-budget-call-or-refusal-mismatch')
        accounting = raw_receipt.get('failure_accounting', {})
        if (accounting.get('schema') != 'factory-sanitized-accounting/1'
                or accounting.get('calls') != len(budget.calls)
                or accounting.get('input_tokens') != budget.input_tokens
                or accounting.get('output_tokens') != budget.output_tokens
                or accounting.get('estimated_cost_usd') != budget.estimated_cost_usd
                or type(accounting.get('duration_ms')) is not int
                or len(accounting.get('call_hashes', [])) != len(budget.calls)):
            raise ValueError('p5-budget-durable-accounting-mismatch')
        tokens = budget.input_tokens + budget.output_tokens
        cost = budget.estimated_cost_usd
        if case == 'dollar-returned' and cost <= fixture.order.max_model_cost_usd:
            raise ValueError('p5-budget-returned-cost-lost')
        if case == 'token-returned' and tokens <= fixture.order.max_model_tokens:
            raise ValueError('p5-budget-returned-tokens-lost')
        if case.endswith('preflight') and (tokens != 0 or cost != 0):
            raise ValueError('p5-budget-preflight-spurious-charge')
        if routed and (budget.calls[0].get('status') != 'failed'
                or budget.calls[0].get('usage') != 'reserved-upper-bound'
                or tokens <= 0 or cost <= 0 or len(bounded.routing) != 1
                or bounded.routing[0]['fallback'] is not False):
            raise ValueError('p5-budget-failed-primary-accounting')
        return dict(case=case, controller_refused=refused, primary_stub_calls=primary.calls,
            secondary_stub_calls=secondary.calls, accounted_calls=len(budget.calls),
            accounted_tokens=tokens, simulated_accounted_cost_usd=cost,
            call_evidence_sha256=[c['content_sha256'] for c in budget.calls],
            wrapper_type=type(budget).__name__, routed=routed, controller_receipt=receipt,
            work_order_sha256=fixture.order.content_sha256,
            receipt_has_model_accounting='calls' in raw_receipt.get('failure_accounting', {}),
            receipt_bytes_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            real_model_calls=0, actual_spend=0)
    finally:
        fixture.close()


def observe(fixture, repository):
    root = fixture.parent/'budget-controller-probes'
    root.mkdir()
    rows = [observe_case(root/case, repository, case) for case in CASES]
    return rows
