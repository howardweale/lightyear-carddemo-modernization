"""Bind conservative count charges to the controller's existing attempt ledger.

This is draft integration, not a provider tokenization proof. The proposed
production binder selects the request-derived profile. Its numbers and named
limitation are unapproved. Replay reports evidence and cannot authorize resume.
"""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
import os

from .contracts import ContractError, canonical_hash
from .count_charge_account import CountChargeAccount, replay_count_charges
from .flex_billing import flex_billing_policy, is_flex_billing_policy


def unavailable_count_bound(raw):
    raise ContractError('count-input-bound-not-established-before-send')


def bind_controller_counts(controller):
    from .routing import RoutedBudget
    from .budgeted_providers import AccountedModelProvider
    bounded = getattr(controller.agents, 'bounded_provider', None)
    providers = list(bounded.router.providers.values()) if type(bounded) is RoutedBudget else [getattr(bounded, 'provider', None)]
    if not any(getattr(provider, 'billing_policy', None) is not None for provider in providers):
        return None
    budget = bounded.budget if type(bounded) is RoutedBudget else bounded
    if type(budget) is not AccountedModelProvider:
        raise ContractError('count-controller-accounted-budget-required')
    from .count_request_bound import serialized_count_bound
    component = ControllerCountAccounting(budget, controller._receipt_journal,
                                         controller._receipt_identity['content_sha256'],
                                         bound_resolver=serialized_count_bound)
    component.profile = 'request-bytes-v1'
    budget.count_controller = component
    controller._receipt_count_account = component
    return dict(billing_policy=flex_billing_policy(), count_cap_usd=str(budget.order.max_model_cost_usd),
                count_bound_profile=component.profile)


def live_count_header(controller):
    component = getattr(controller, '_receipt_count_account', None)
    if component is None:
        return None
    from .routing import RoutedBudget
    bounded = getattr(controller.agents, 'bounded_provider', None)
    budget = bounded.budget if type(bounded) is RoutedBudget else bounded
    if (type(component) is not ControllerCountAccounting
            or component.budget is not budget
            or getattr(budget, 'count_controller', None) is not component
            or component.journal is not controller._receipt_journal
            or component.identity != controller._receipt_identity['content_sha256']):
        raise ContractError('count-controller-live-header-binding')
    result = dict(billing_policy=flex_billing_policy(), count_cap_usd=str(budget.order.max_model_cost_usd))
    if component.profile is not None:
        if component.profile != 'request-bytes-v1':
            raise ContractError('count-controller-bound-profile')
        result['count_bound_profile'] = component.profile
    return result


def validate_live_count_generation(accounting, reservation):
    rows = accounting['count_financial_accounting']['count_account']['calls']
    preflight = reservation['input_token_preflight']
    if (not rows or rows[-1]['state'] != 'counted-conservative-charge'
            or rows[-1]['ticket']['request_sha256'] != preflight['count_request_sha256']
            or rows[-1]['counted_input_tokens'] != preflight['input_tokens']):
        raise ContractError('count-controller-generation-before-durable-settlement')


class ControllerCountAccounting:
    def __init__(self, budget, journal, identity, *, bound_resolver=None):
        from .budgeted_providers import AccountedModelProvider
        from .ledger import RunLedger
        if type(budget) is not AccountedModelProvider or type(journal) is not RunLedger:
            raise ContractError('count-controller-native-binding')
        if budget.calls or budget.estimated_cost_usd != 0:
            raise ContractError('count-controller-must-bind-before-calls')
        self.budget, self.journal, self.identity = budget, journal, identity
        self.profile = None
        self.resolver = unavailable_count_bound if bound_resolver is None else bound_resolver
        if not callable(self.resolver):
            raise ContractError('count-controller-bound-resolver')
        self.active = None
        self.book = CountChargeAccount(flex_billing_policy(),
            cap_usd=str(budget.order.max_model_cost_usd), attempt_identity_sha256=identity,
            other_exposure_usd=self._other_exposure, durable_append=self._append)

    def _other_exposure(self):
        cost = Decimal(str(self.budget.estimated_cost_usd))
        if self.active is not None:
            invocation, bounds = self.active
            if len(self.budget.calls) < invocation['call_sequence']:
                cost += Decimal(str(bounds['estimated_cost_usd']))
        return cost

    def _live_journal(self):
        from .ledger import RunLedger
        from .orchestrator import _reconcile_physical_accounting_journal
        loaded = RunLedger(self.journal.path)
        expected = dict(attempt_identity_sha256=self.identity, protocol=5,
            billing_policy=flex_billing_policy(), count_cap_usd=str(self.budget.order.max_model_cost_usd))
        if self.profile is not None:
            expected['count_bound_profile'] = self.profile
        if (not loaded.verify() or loaded.events != self.journal.events or not loaded.events
                or loaded.events[0]['payload'] != expected
                or getattr(self.budget, 'count_controller', None) is not self):
            raise ContractError('count-controller-live-journal-binding')
        reconcile_controller_counts(loaded.events, self.identity, _reconcile_physical_accounting_journal)

    def _append(self, event):
        self._live_journal()
        if self.active is None:
            raise ContractError('count-controller-outside-logical-call')
        invocation, _ = self.active
        self.journal.append('RESERVED' if event['kind'] == 'count_charge_reserved' else 'OBSERVED',
            'count_financial', dict(attempt_identity_sha256=self.identity,
                invocation=deepcopy(invocation), event=deepcopy(event)))
        with self.journal.path.open('ab') as stream:
            os.fsync(stream.fileno())

    @contextmanager
    def scope(self, provider, invocation, bounds):
        from .providers import OpenAIResponsesProvider
        if (self.active is not None or not isinstance(provider, OpenAIResponsesProvider)
                or not is_flex_billing_policy(getattr(provider, 'billing_policy', None))
                or getattr(provider, 'max_retries', None) != 0
                or provider.count_account is not None or provider.count_bound_resolver is not None
                or invocation['call_sequence'] != len(self.budget.calls)+1
                or bounds['cost_estimate_available'] is not True):
            raise ContractError('count-controller-provider-or-invocation-binding')
        self.active = (deepcopy(invocation), deepcopy(bounds))
        provider.count_account, provider.count_bound_resolver = self.book, self.resolver
        try:
            yield
        finally:
            provider.count_account = provider.count_bound_resolver = None
            self.active = None

    def report(self):
        from .orchestrator import _reconcile_physical_accounting_journal
        return reconcile_controller_counts(self.journal.events, self.identity,
            _reconcile_physical_accounting_journal)['count_financial_accounting']


def financial_report(counts, generation_cost, pending_generation_cost=0):
    # Generation's logical totals already include managed-failure reserves.
    # Physical generation observations MUST NOT be added a second time.
    result = dict(schema='factory-conservative-financial-accounting/1',
        generation_logical_cost_usd=str(Decimal(str(generation_cost))), count_account=counts,
        pending_generation_reserve_usd=str(Decimal(str(pending_generation_cost))),
        combined_conservative_cost_usd=str(Decimal(str(generation_cost)) +
                                           Decimal(str(pending_generation_cost)) +
                                           Decimal(counts['count_exposure_usd'])),
        billing_final=False, actual_provider_cost_usd=None,
        invoice_reconciliation="The actual cost will be reconciled by Howard from the provider's invoice.")
    result['content_sha256'] = canonical_hash(result)
    return result


def reconcile_controller_counts(events, identity, physical_replay):
    """Validate all count events and native accounting without relaxing v4.

    Caller first verifies the complete original RunLedger chain. The projection
    below is used only for existing semantic validation, never as a new ledger.
    """
    if not events:
        raise ContractError('count-controller-empty-journal')
    first = events[0]
    header = first['payload']
    fields = {'attempt_identity_sha256', 'protocol', 'billing_policy', 'count_cap_usd'}
    profile = header.get('count_bound_profile')
    if 'count_bound_profile' in header:
        fields.add('count_bound_profile')
        if profile != 'request-bytes-v1':
            raise ContractError('count-controller-unknown-bound-profile')
    if (first['kind'] != 'model_reservations' or first['state'] != 'READY'
            or set(header) != fields
            or header['attempt_identity_sha256'] != identity
            or type(header['protocol']) is not int or header['protocol'] != 5
            or not is_flex_billing_policy(header['billing_policy'])):
        raise ContractError('count-controller-protocol')
    projected = [dict(first, payload=dict(attempt_identity_sha256=identity, protocol=4))]
    financial = []
    logical = accounting = None
    pending = None
    completed_count = None
    for event in events[1:]:
        payload, kind = event['payload'], event['kind']
        if payload.get('attempt_identity_sha256') != identity:
            raise ContractError('count-controller-identity')
        if kind == 'count_financial':
            if (set(payload) != {'attempt_identity_sha256', 'invocation', 'event'}
                    or logical is None or accounting is None):
                raise ContractError('count-controller-financial-binding')
            invocation = dict(call_sequence=logical['call_sequence'],
                              invocation_sha256=logical['invocation_sha256'])
            row = payload['event']
            if not isinstance(row, dict) or payload['invocation'] != invocation:
                raise ContractError('count-controller-logical-binding')
            exposure = Decimal(str(accounting['estimated_cost_usd']))+Decimal(str(logical['estimated_cost_usd']))
            if row.get('other_exposure_usd') != str(exposure):
                raise ContractError('count-controller-generation-exposure')
            expected_state = 'RESERVED' if row.get('kind') == 'count_charge_reserved' else 'OBSERVED'
            if event['state'] != expected_state:
                raise ContractError('count-controller-financial-state')
            if row.get('kind') == 'count_charge_reserved':
                if profile == 'request-bytes-v1' and 'bound_basis' not in row:
                    raise ContractError('count-controller-required-bound-basis-missing')
                if pending is not None or completed_count is not None:
                    raise ContractError('count-controller-duplicate-count')
                pending = dict(row=row, physical=None, observation=None)
            elif row.get('kind') == 'count_charge_observed':
                if pending is None:
                    raise ContractError('count-controller-settlement-without-reserve')
                physical = pending['physical']
                observation = pending['observation']
                if row.get('counted_input_tokens') is not None and (
                        physical is None or observation is None
                        or observation.get('outcome') != 'returned'
                        or observation.get('input_token_count') != row['counted_input_tokens']):
                    raise ContractError('count-controller-count-evidence-mismatch')
                completed_count = pending
                completed_count['settlement'] = row
                pending = None
            else:
                raise ContractError('count-controller-financial-kind')
            financial.append(row)
            continue
        if kind == 'reserved':
            if pending is not None:
                raise ContractError('count-controller-next-call-with-pending-count')
            logical = payload['reservation']
            completed_count = None
        elif kind == 'model_transport_reserved':
            reservation = payload['reservation']
            if (reservation['provider'] != 'openai-responses'
                    or reservation['model'] != header['billing_policy']['model']
                    or reservation['pricing'] != dict(input_usd_per_million=5.5,output_usd_per_million=24.75)
                    or type(reservation['provider_attempt']) is not int or reservation['provider_attempt'] != 1
                    or reservation['transport_kind'] not in ('input-token-count','responses')):
                raise ContractError('count-controller-physical-policy-mismatch')
            if reservation['transport_kind'] == 'input-token-count':
                if (pending is None or pending['physical'] is not None
                        or pending['row']['request_sha256'] != reservation['request_sha256']):
                    raise ContractError('count-controller-send-without-financial-reserve')
                if ('bound_basis' in pending['row'] and
                        pending['row']['bound_basis']['request_bytes'] != reservation['request_bytes']):
                    raise ContractError('count-controller-physical-bound-bytes')
                pending['physical'] = reservation
            elif reservation['transport_kind'] == 'responses':
                if (pending is not None or completed_count is None or completed_count['observation'] is None
                        or type(completed_count['settlement'].get('counted_input_tokens')) is not int
                        or completed_count['settlement'].get('bound_exceeded') is not False
                        or completed_count['settlement'].get('shared_cap_exceeded') is not False):
                    raise ContractError('count-controller-generation-before-count-settlement')
        elif kind == 'model_transport_observed':
            if pending is not None and pending['physical'] is not None:
                pending['observation'] = payload['observation']
        elif kind == 'sanitized_accounting':
            if pending is not None and (accounting is None or payload['accounting']['calls'] != accounting['calls']):
                raise ContractError('count-controller-checkpoint-with-pending-count')
            accounting = payload['accounting']
            if logical is not None and accounting['calls'] >= logical['call_sequence']:
                logical = None
        projected.append(event)
    native = physical_replay(projected, identity)
    counts = replay_count_charges(financial, header['billing_policy'], cap_usd=header['count_cap_usd'],
                                 attempt_identity_sha256=identity)
    native['count_financial_accounting'] = financial_report(counts, native['estimated_cost_usd'],
        logical['estimated_cost_usd'] if logical is not None else 0)
    native['count_financial_accounting']['pending_count_before_send'] = pending is not None and pending['physical'] is None
    native['count_financial_accounting']['content_sha256'] = canonical_hash(
        native['count_financial_accounting'], {'content_sha256'})
    return native
