"""Original durable reservation plus current proof immediately before native open.

Encrypted request persistence may take time after the reservation guard. This
second boundary grants no authority, retries, replacement tickets or receipt.
It does not cancel requests already in flight. No external callback is accepted.
"""
from hashlib import sha256
from weakref import WeakKeyDictionary
from lightyear_factory.contracts import ContractError

_ATTEMPTED=WeakKeyDictionary()


def match_pending_request(events,identity,request,role,model,sequence):
    # Pure relationship check: synthetic records never establish live origin.
    from .configured_human_recorded_transport import require_recorded_request
    from .configured_human_transport import configured_transport_action
    require_recorded_request(request)
    physical=[event for event in events if event.get('kind') in
              ('model_transport_reserved','model_transport_observed')]
    if not physical or physical[-1]['kind']!='model_transport_reserved':
        raise ContractError('configured-wire-boundary-pending-reservation-required')
    event=physical[-1];payload=event.get('payload',{});row=payload.get('reservation')
    configured_transport_action(row,model,sequence)
    kind='responses' if request.full_url.endswith('/responses') else 'input-token-count'
    if (payload.get('attempt_identity_sha256')!=identity
            or type(payload.get('transport_sequence')) is not int or payload['transport_sequence']<1
            or row.get('role')!=role or row.get('transport_kind')!=kind
            or row.get('request_sha256')!=sha256(request.data).hexdigest()
            or type(row.get('request_bytes')) is not int or row['request_bytes']!=len(request.data)):
        raise ContractError('configured-wire-boundary-original-request-mismatch')
    return event,row


def require_original_wire_open(provider,request):
    from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider
    from .configured_human_controller import _ROUTERS,_CONTROLLERS
    from .configured_human_terminal import _require_origin,_original_callback_bindings
    from .configured_human_transport import require_configured_transport
    if type(provider) is not SnapshotOpenAIResponsesProvider:
        raise ContractError('configured-wire-boundary-native-provider-required')
    owners=[(context,_CONTROLLERS.get(context)) for context,original in list(_ROUTERS.items())
            if original[1] is provider]
    if len(owners)!=1 or owners[0][1] is None:
        raise ContractError('configured-wire-boundary-original-controller-required')
    context,binding=owners[0];controller=binding['controller']
    saved=_require_origin(controller)
    if (saved['context']() is not context or saved['provider']() is not provider
            or provider.transport_recorder is None or not provider._recorded_call_active):
        raise ContractError('configured-wire-boundary-original-call-required')
    budget=saved['budget']()
    events=controller._live_journal_events()
    event,row=match_pending_request(events,saved['identity_sha256'],request,
        provider._recorded_role,provider.model,len(budget.calls)+1)
    key=event['event_sha256']
    attempted=_ATTEMPTED.setdefault(provider,set())
    if key in attempted:raise ContractError('configured-wire-boundary-reservation-reuse')
    # A failed check burns only this in-process open attempt; it never consumes
    # a new admission nonce or changes the original durable accounting journal.
    attempted.add(key)
    head=controller._receipt_journal.head_sha256
    # All original-byte hashing/persistence above precedes this genuine current
    # proof/role/workflow/input verification and final native elapsed check.
    require_configured_transport(controller,row)
    if (controller._receipt_journal.head_sha256!=head
            or provider.transport_recorder is not saved['recorder']()
            or saved['callbacks']!=_original_callback_bindings(controller,budget)):
        raise ContractError('configured-wire-boundary-binding-changed')
