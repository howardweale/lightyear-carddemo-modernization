"""Predeclared evaluation arm; never adds attempts or judges a result itself.

Only an explicitly budget-approved matrix should construct this provider. Its
declaration is included in the plan and every call is replay-checked by aggregate.
It is not a production route until separately evaluated and approved in Tower.
"""
from .contracts import ContractError, canonical_hash
from .budgeted_providers import AccountedModelProvider
from .providers import ProviderResult


def validate(declaration, providers):
    if declaration.get('schema') != 'factory-escalation-arm/1':
        raise ContractError('escalation declaration')
    if set(declaration['model_versions']) != {declaration['first'], declaration['repair']}:
        raise ContractError('escalation model closure')
    if not 1 <= declaration['max_builder_attempts'] <= 10:
        raise ContractError('escalation attempt cap')
    if any(m not in providers or providers[m].model != version
           for m, version in declaration['model_versions'].items()):
        raise ContractError('escalation model version changed')


class EvaluationLadder:
    provider_id = 'factory-evaluation-ladder'

    def __init__(self, providers, declaration):
        validate(declaration, providers)
        self.providers, self.declaration = providers, declaration
        self.model = canonical_hash(declaration)

    def bind_order(self, order):
        if order.metadata.get('campaign_id') or order.metadata.get('calibration_campaign'):
            raise ContractError('campaigns cannot use factory escalation')
        if self.declaration['max_builder_attempts'] > order.max_attempts:
            raise ContractError('ladder exceeds judge attempt budget')
        return LadderBudget(self, order)


class LadderBudget:
    def __init__(self, ladder, order):
        self.ladder = ladder
        self.budget = AccountedModelProvider(ladder.providers[ladder.declaration['first']], order)
        self.builder_attempt = 0

    @property
    def calls(self):
        return self.budget.calls

    def complete(self, role, instruction, payload, schema):
        d = self.ladder.declaration
        validate(d, self.ladder.providers)
        if role == 'builder':
            if self.builder_attempt >= d['max_builder_attempts']:
                raise ContractError('ladder attempt budget exhausted')
            if self.builder_attempt and (not isinstance(payload.get('public_failure'), dict)
                                         or not payload['public_failure']):
                raise ContractError('ladder repair requires closed diagnostic')
            self.builder_attempt += 1
        selected = d['repair'] if self.builder_attempt > 1 else d['first']
        self.budget.provider = self.ladder.providers[selected]
        choice = dict(arm_sha256=canonical_hash(d), builder_attempt=self.builder_attempt,
                      role=role, model=selected)
        before = len(self.calls)
        try:
            result = self.budget.complete(role, instruction, payload, schema)
        finally:
            # Failed calls are retained too. There is no provider-error fallback.
            for i in range(before, len(self.calls)):
                row = {**self.calls[i], 'escalation': choice}
                row['content_sha256'] = canonical_hash(row, {'content_sha256'})
                self.calls[i] = row
        return ProviderResult(result.content, self.calls[-1])

    def summary(self):
        row = {**self.budget.summary(), 'escalation_arm': self.ladder.declaration}
        row['content_sha256'] = canonical_hash(row, {'content_sha256'})
        return row


def replay_call(call, declaration, builder_attempt):
    """Called in receipt call-order, with a counter reset for every trial."""
    choice = call.get('escalation', {})
    if choice.get('role') == 'builder':
        builder_attempt += 1
    selected = declaration['repair'] if builder_attempt > 1 else declaration['first']
    if (choice != dict(arm_sha256=canonical_hash(declaration), builder_attempt=builder_attempt,
                       role=choice.get('role'), model=selected)
            or choice.get('role') not in {'planner', 'builder', 'failure_analyst'}
            or builder_attempt > declaration['max_builder_attempts']
            or call['model'] != declaration['model_versions'][selected]):
        raise ContractError('matrix escalation binding')
    return builder_attempt
