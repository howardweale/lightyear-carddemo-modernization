"""Read original configured terminal files after refusal without restoring authority.

The return value is an internal mapping of unchanged file bytes. No new receipt
schema, success claim, accounting acceptance, retry or qualification is created.
An abruptly killed process cannot use this same-process reader.
"""
import json
import os
from pathlib import Path
from weakref import WeakKeyDictionary,ref

from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_factory.model_admission import _bounded_regular_bytes

_ORIGINAL=WeakKeyDictionary()


def _state(controller):
    context=controller.execution_context;router=controller.agents.provider
    provider=router.providers[router.default]
    return canonical_hash(dict(admission=context.admission_receipt,
        binding=context._binding,policy=context.policy.to_dict(),
        inputs={k:str(v) for k,v in context._inputs.items()},manifest=context._manifest,
        source_root=str(context._source_root),order_sha256=context._order.content_sha256,
        backend=dict(policy=context.backend.policy.to_dict(),runtime=context.backend.runtime,
            execute_enabled=context.backend.execute_enabled,backend_id=context.backend.backend_id),
        ci={k:os.environ.get(k) for k in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT',
            'GITHUB_REPOSITORY','GITHUB_WORKFLOW_REF','GITHUB_WORKFLOW_SHA')},
        model=dict(default=router.default,model=provider.model,tier=provider.service_tier,
            billing=provider.billing_policy,input_price=provider.input_usd_per_million,
            output_price=provider.output_usd_per_million,max_output=provider.max_output_tokens,
            retries=provider.max_retries,preflight=provider.token_preflight,
            snapshot=provider.require_snapshot_response,managed=provider.manage_failure_budget),
        routing=dict(policy=router.policy,matrix=router.matrix,proof=router.proof,trust=router.trust)))


def _recorded_transport_identity(provider):
    if provider.transport_recorder is None:return None
    from .configured_human_recorded_transport import recorded_transport_identity
    return recorded_transport_identity(provider)


def _original_callback_bindings(controller, budget):
    # Pure identity checks only; not proof of admission or controller origin.
    from lightyear_factory.orchestrator import FactoryOrchestrator
    from lightyear_factory.budgeted_providers import AccountedModelProvider
    if type(controller) is not FactoryOrchestrator or type(budget) is not AccountedModelProvider:
        raise ContractError('configured-terminal-native-callback-owner')
    pairs = (('reservation_checkpoint', '_reserve_model_call'),
             ('observed_checkpoint', '_checkpoint_accounting'),
             ('transport_reservation_checkpoint', '_reserve_model_transport'),
             ('transport_observed_checkpoint', '_observe_model_transport'))
    original = []
    for callback_name, method_name in pairs:
        method = getattr(controller, method_name, None)
        callback = getattr(budget, callback_name, None)
        if (getattr(method, '__self__', None) is not controller
                or getattr(method, '__func__', None) is not getattr(FactoryOrchestrator, method_name)
                or callback != method):
            raise ContractError('configured-terminal-original-callback-changed')
        original.append(method)
    return tuple(original)


def capture_configured_terminal_origin(controller,order,ledger,run_dir):
    from .configured_receipt_controller import verify_configured_controller,_CONTROLLERS
    from lightyear_factory.routing import RoutedBudget
    verify_configured_controller(controller,order)
    context=controller.execution_context
    bound=_CONTROLLERS.get(context)
    if (controller in _ORIGINAL or bound is None or bound['controller'] is not controller
            or bound['ledger'] is not ledger or bound['run_dir']!=Path(run_dir)
            or not context._controller_bound or bound.get('finalized') is not True
            or type(controller.agents.bounded_provider) is not RoutedBudget):
        raise ContractError('configured-terminal-live-origin-required')
    router=controller.agents.provider;provider=router.providers[router.default]
    _ORIGINAL[controller]=dict(pid=os.getpid(),context=ref(context),admission=ref(context._admission),
        backend=ref(context.backend),order=ref(order),router=ref(router),provider=ref(provider),
        workspace=ref(bound['workspace']),artifacts=ref(bound['artifacts']),
        scanner=bound['scanner'],scanner_relations=bound['scanner_relations'],
        budget=ref(controller.agents.bounded_provider.budget),ledger=ref(ledger),
        journal=ref(controller._receipt_journal),count=ref(controller._receipt_count_account),
        state_sha256=_state(controller),identity_sha256=bound['identity_sha256'],
        run_dir=Path(run_dir),transport=provider._transport_opener,
        opener_function=provider.opener.__func__,
        callbacks=_original_callback_bindings(controller,controller.agents.bounded_provider.budget),
        recorder=ref(bound['recorder']),transport_key=bound['transport_key'],
        transport_key_id=bound['recorder'].key_id,
        recorded_transport=_recorded_transport_identity(provider))


def _require_origin(controller):
    # Deliberately no _live(), proof verifier, environment secret, API or clock.
    from lightyear_factory.orchestrator import FactoryOrchestrator
    if type(controller) is not FactoryOrchestrator:
        raise ContractError('configured-terminal-original-controller-required')
    saved=_ORIGINAL.get(controller)
    if saved is None or saved['pid']!=os.getpid():
        raise ContractError('configured-terminal-same-process-origin-required')
    context=controller.execution_context;router=controller.agents.provider
    if (saved['context']() is not context or saved['admission']() is not context._admission
            or saved['backend']() is not context.backend or saved['order']() is not context._order
            or saved['router']() is not router or len(router.providers)!=1
            or router.default not in router.providers
            or saved['provider']() is not router.providers[router.default]
            or saved['budget']() is not controller.agents.bounded_provider.budget
            or saved['budget']().provider is not saved['provider']()
            or saved['budget']().order is not context._order
            or saved['journal']() is not controller._receipt_journal
            or saved['count']() is not controller._receipt_count_account
            or saved['count']().journal is not saved['journal']()
            or saved['count']().budget is not saved['budget']()
            or saved['budget']().count_controller is not saved['count']()
            or saved['state_sha256']!=_state(controller)
            or saved['provider']()._transport_opener is not saved['transport']
            or getattr(saved['provider']().opener,'__self__',None) is not saved['provider']()
            or getattr(saved['provider']().opener,'__func__',None) is not saved['opener_function']):
        raise ContractError('configured-terminal-original-binding-changed')
    if (saved['callbacks'] != _original_callback_bindings(controller,saved['budget']())
            or saved['recorded_transport'] != _recorded_transport_identity(saved['provider']())
            or (None if saved['recorder'] is None else saved['recorder']())
               is not saved['provider']().transport_recorder
            or saved['recorder']() is None
            or saved['recorder']().key is not saved['transport_key']
            or saved['recorder']().key_id!=saved['transport_key_id']):
        raise ContractError('configured-terminal-original-callback-or-recorder-changed')
    from .configured_human_lifecycle import original_scanner_relations
    workspace=saved['workspace']();artifacts=saved['artifacts']()
    if (workspace is None or artifacts is None
            or workspace.root!=(saved['run_dir']/'workspace').resolve()
            or artifacts.root!=saved['run_dir']/'artifacts' or artifacts.run_id!=saved['run_dir'].name
            or controller.agents.isolation_scan is not saved['scanner']
            or saved['scanner_relations']!=original_scanner_relations(controller,saved['order'](),
                workspace,saved['ledger'](),controller.agents.isolation_scan)):
        raise ContractError('configured-terminal-original-scanner-or-store-changed')
    return saved


def _original_json(raw):
    # Canonical hashes cannot disambiguate duplicate wire keys after parsing.
    # Preserve the original bytes and reject ambiguity before any relationships.
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:
                raise ContractError('configured-terminal-duplicate-json-key')
            value[key]=item
        return value
    def nonfinite(value):
        raise ContractError('configured-terminal-nonfinite-json')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite)


def _ledger_bytes(raw):
    if type(raw) is not bytes or not raw or not raw.endswith(b'\n'):
        raise ContractError('configured-terminal-incomplete-ledger')
    rows=[];previous=None
    for sequence,line in enumerate(raw.splitlines(),1):
        if not line.strip():raise ContractError('configured-terminal-blank-ledger-row')
        row=_original_json(line)
        if (type(row) is not dict or type(row.get('sequence')) is not int
                or row.get('sequence')!=sequence
                or row.get('previous_sha256')!=previous
                or row.get('event_sha256')!=canonical_hash(row,{'event_sha256'})):
            raise ContractError('configured-terminal-ledger-chain')
        previous=row['event_sha256'];rows.append(row)
    return rows


def read_original_configured_terminal(controller):
    from .configured_receipt_build_bindings import verify_configured_terminal_build as verify_receipt_tail
    saved=_require_origin(controller);root=saved['run_dir']
    context=controller.execution_context
    names={'receipt.json':1024*1024,'summary.json':1024*1024,
        'attempt-identity.json':65536,'events.jsonl':32*1024*1024,
        'attempt-accounting.jsonl':32*1024*1024}
    if (root.parent!=controller.runs_root or saved['ledger']() is None
            or saved['ledger']().path!=root/'events.jsonl'
            or saved['journal']().path!=root/'attempt-accounting.jsonl'):
        raise ContractError('configured-terminal-original-paths-required')
    raw={name:_bounded_regular_bytes(root/name,limit,'configured-terminal-file')
         for name,limit in names.items()}
    receipt=_original_json(raw['receipt.json']);summary=_original_json(raw['summary.json'])
    identity=_original_json(raw['attempt-identity.json'])
    admission=context.admission_receipt
    if (receipt.get('receipt_type')!='lightyear-autonomous-factory-run'
            or receipt.get('status') not in ('passed','blocked')
            or receipt.get('content_sha256')!=canonical_hash(receipt,{'content_sha256'})
            or receipt.get('work_order_sha256')!=context._order.content_sha256
            or summary.get('receipt_sha256')!=receipt['content_sha256']
            or summary.get('status')!=receipt['status']
            or identity.get('schema')!='factory-attempt-identity/1'
            or identity.get('content_sha256')!=canonical_hash(identity,{'content_sha256'})
            or identity['content_sha256']!=saved['identity_sha256']
            or identity.get('attempt_id')!=root.name
            or identity.get('work_order_sha256')!=receipt['work_order_sha256']
            or identity.get('admission_receipt_sha256')!=admission['content_sha256']
            or identity.get('consumed_nonce_sha256')!=admission['nonce_sha256']
            or controller._receipt_identity!=identity):
        raise ContractError('configured-terminal-original-receipt-binding')
    events=_ledger_bytes(raw['events.jsonl']);accounting=_ledger_bytes(raw['attempt-accounting.jsonl'])
    if (events!=saved['ledger']().events or accounting!=saved['journal']().events
            or any(row['payload'].get('attempt_identity_sha256')!=identity['content_sha256']
                   for row in accounting)):
        raise ContractError('configured-terminal-original-journal-binding')
    verify_receipt_tail(receipt,summary,events)
    from .configured_terminal_runtime_join import match_terminal_runtime
    match_terminal_runtime(receipt,admission,identity,context._binding['runtime'])
    _require_origin(controller)
    if any(_bounded_regular_bytes(root/name,names[name],'configured-terminal-file')!=value
           for name,value in raw.items()):
        raise ContractError('configured-terminal-file-changed-during-read')
    # Bytes only. In particular, no accounting, expected-refusal or strict pass.
    return raw
