"""Native configured controller bridge; no CLI dispatch or execution authority.

This module is an isolated source proposal. Its factory requires an already
genuinely admitted, same-process context and never accepts a provider callback.
"""
from copy import deepcopy
from pathlib import Path
from urllib.request import urlopen
from weakref import WeakKeyDictionary

from lightyear_factory.contracts import ContractError,canonical_hash
from .configured_human_context import ConfiguredHumanExecutionContext

_ROUTERS=WeakKeyDictionary()
_STARTED=WeakKeyDictionary()
_CONTROLLERS=WeakKeyDictionary()


def _live_context(context):
    if type(context) is not ConfiguredHumanExecutionContext:
        raise ContractError('configured-controller-native-context-required')
    context._live()


def _provider_binding(context,router):
    from lightyear_factory.routing import TaskRouter
    from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider
    _live_context(context)
    original=_ROUTERS.get(context)
    document=context._binding['models']['document']
    default=document['default'];model=document['models'][default]
    if (original is None or original[0] is not router or type(router) is not TaskRouter
            or router.default!=default or router.model!=default
            or set(router.providers)!={default}
            or any(value is not None for value in (router.policy,router.matrix,router.proof,router.trust))):
        raise ContractError('configured-controller-original-router-required')
    provider=router.providers[default]
    if (provider is not original[1] or type(provider) is not SnapshotOpenAIResponsesProvider
            or provider.model!=model['model'] or provider.service_tier!='flex'
            or provider.max_retries!=0 or provider.token_preflight is not True
            or provider.require_snapshot_response is not True
            or provider.manage_failure_budget is not True
            or provider.max_output_tokens!=model['max_output_tokens']
            or provider.input_usd_per_million!=model['input_usd_per_million']
            or provider.output_usd_per_million!=model['output_usd_per_million']
            or provider.billing_policy!=model['billing_policy']
            or provider._transport_opener is not urlopen
            or getattr(provider.opener,'__self__',None) is not provider
            or getattr(provider.opener,'__func__',None) is not SnapshotOpenAIResponsesProvider._open_verified):
        raise ContractError('configured-controller-provider-changed')
    return provider


def create_configured_human_router(context):
    from lightyear_factory.model_config import configured_models
    from lightyear_factory.provider_secrets import HardenedSecretStore
    from lightyear_factory.routing import TaskRouter
    _live_context(context)
    if context in _STARTED or context._bound:
        raise ContractError('configured-controller-router-reuse')
    _STARTED[context]=True
    try:
        document=deepcopy(context._binding['models']['document'])
        providers=configured_models(document,secret_store=HardenedSecretStore(context))
        context._live()
        router=TaskRouter(providers,document['default'])
        _ROUTERS[context]=(router,providers[document['default']])
        _provider_binding(context,router)
        return router
    except BaseException:
        _ROUTERS.pop(context,None)
        context.close()
        raise ContractError('configured-controller-router-construction-refused') from None


def verify_configured_controller(controller,order):
    from lightyear_factory.orchestrator import FactoryOrchestrator
    from lightyear_factory.agents import ModelAgentSet
    if type(controller) is not FactoryOrchestrator:
        raise ContractError('configured-controller-native-controller-required')
    context=controller.execution_context
    _live_context(context)
    if (order is not context._order or controller.model_admission is not context._admission
            or type(controller.agents) is not ModelAgentSet
            or Path(controller.source_root).resolve()!=Path(context._source_root).resolve()
            or controller.factory_input_paths!=context._inputs
            or controller.workspace_read_manifest!=context._manifest
            or controller.candidate_signing_paths is not None
            or controller.private_expected_values_path is not None):
        raise ContractError('configured-controller-original-inputs-required')
    _provider_binding(context,controller.agents.provider)
    if context in _CONTROLLERS and _CONTROLLERS[context]['controller'] is not controller:
        raise ContractError('configured-controller-replacement-refused')
    return deepcopy(context._binding['runtime'])


def bind_configured_controller(controller,order,ledger,run_dir):
    from lightyear_factory.routing import RoutedBudget
    from lightyear_factory.budgeted_providers import AccountedModelProvider
    from lightyear_factory.ledger import RunLedger
    from lightyear_factory.controller_count_accounting import live_count_header
    verify_configured_controller(controller,order)
    context=controller.execution_context
    bounded=controller.agents.bounded_provider
    if (context in _CONTROLLERS or not context._bound
            or type(bounded) is not RoutedBudget
            or bounded.router is not controller.agents.provider
            or type(bounded.budget) is not AccountedModelProvider
            or bounded.budget.provider is not _ROUTERS[context][1]
            or bounded.budget.order is not order or bounded.budget.calls
            or type(ledger) is not RunLedger or ledger.path!=Path(run_dir)/'events.jsonl'
            or Path(run_dir).parent!=controller.runs_root):
        raise ContractError('configured-controller-binding-refused')
    identity=controller._receipt_identity
    if (type(identity) is not dict
            or identity.get('content_sha256')!=canonical_hash(identity,{'content_sha256'})
            or identity.get('work_order_sha256')!=order.content_sha256
            or identity.get('admission_receipt_sha256')!=context.admission_receipt['content_sha256']
            or identity.get('consumed_nonce_sha256')!=context.admission_receipt['nonce_sha256']
            or type(controller._receipt_journal) is not RunLedger
            or controller._receipt_journal.path!=Path(run_dir)/'attempt-accounting.jsonl'):
        raise ContractError('configured-controller-original-attempt-required')
    header=live_count_header(controller)
    if header is None or header.get('count_bound_profile')!='request-bytes-v1':
        raise ContractError('configured-controller-shared-count-generation-required')
    # Use the unchanged controller's original physical reservation callbacks.
    for name,method in (('reservation_checkpoint','_reserve_model_call'),
                        ('observed_checkpoint','_checkpoint_accounting'),
                        ('transport_reservation_checkpoint','_reserve_model_transport'),
                        ('transport_observed_checkpoint','_observe_model_transport')):
        if getattr(bounded.budget,name,None)!=getattr(controller,method):
            raise ContractError('configured-controller-original-journal-callbacks-required')
    _CONTROLLERS[context]=dict(controller=controller,ledger=ledger,run_dir=Path(run_dir),
        identity_sha256=identity['content_sha256'],journal=controller._receipt_journal,finalized=False)
    # Original attempt/count journals exist, but no role authorization or
    # terminal origin is enabled until scanner/store/workspace finalization.
