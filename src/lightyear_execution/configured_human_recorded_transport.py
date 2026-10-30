"""Native opt-in recorded transport: exact endpoints, no redirects or injected opener.

Construction does not authorize a request. Existing proof, original recorder,
physical reservations and active native provider call must all precede send.
"""
from urllib.request import Request, build_opener, urlopen
from weakref import WeakKeyDictionary
from lightyear_factory.contracts import ContractError
from lightyear_factory.additional_providers import _RecordedNoRedirect

_NATIVE = WeakKeyDictionary()


def _dispatch_fingerprint(director):
    def freeze(value):
        if type(value) is dict:
            return tuple((key,freeze(item)) for key,item in sorted(value.items(),key=lambda row:repr(row[0])))
        if type(value) is list:return tuple(value)
        raise ContractError('configured-recorded-dispatch-shape')
    methods=[]
    def capture(owner,name):
        method=getattr(owner,name,None)
        if not callable(method):
            raise ContractError('configured-recorded-dispatch-method-shape')
        methods.append((owner,name,method))
    # urllib resolves these methods with getattr at send time. Remembering the
    # same handler objects or routing lists alone does not pin their callables.
    for table,suffix in ((director.handle_open,'_open'),
                         (director.process_request,'_request'),
                         (director.process_response,'_response')):
        if type(table) is not dict:
            raise ContractError('configured-recorded-dispatch-shape')
        for protocol,handlers in sorted(table.items()):
            if type(protocol) is not str or type(handlers) is not list:
                raise ContractError('configured-recorded-dispatch-shape')
            for handler in handlers:capture(handler,protocol+suffix)
    if type(director.handle_error) is not dict:
        raise ContractError('configured-recorded-dispatch-shape')
    for protocol,lookup in sorted(director.handle_error.items()):
        if type(protocol) is not str:
            raise ContractError('configured-recorded-dispatch-shape')
        if type(lookup) is dict:
            for code,handlers in sorted(lookup.items(),key=lambda row:repr(row[0])):
                if type(handlers) is not list:
                    raise ContractError('configured-recorded-dispatch-shape')
                for handler in handlers:capture(handler,protocol+'_error_'+str(code))
        elif type(lookup) is list:
            for handler in lookup:capture(handler,protocol+'_error')
        else:raise ContractError('configured-recorded-dispatch-shape')
    for name in ('open','_open','_call_chain','error'):capture(director,name)
    # Pin native helper dispatch used inside HTTPS and redirect handlers too.
    # This is callable identity, not arbitrary Python memory attestation.
    for handler in director.handlers:
        for name in ('do_open','do_request_','redirect_request'):
            if hasattr(handler,name):capture(handler,name)
    parents=tuple((handler,getattr(handler,'parent',None)) for handler in director.handlers)
    return (tuple(director.handlers), freeze(director.handle_open),
            freeze(director.handle_error), freeze(director.process_request),
            freeze(director.process_response),tuple(methods),parents)


def _require_original_dispatch(director,expected):
    # expected comes only from the original private registry in the public
    # transport entry. Comparing snapshots never grants call/admission authority.
    if _dispatch_fingerprint(director)!=expected:
        raise ContractError('configured-recorded-native-dispatch-changed')


def bind_native_recorded_transport(provider):
    from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider
    if (type(provider) is not SnapshotOpenAIResponsesProvider or provider in _NATIVE
            or provider._injected_opener is not False
            or provider._transport_opener is not urlopen or provider._transport_started):
        raise ContractError('configured-recorded-original-native-provider-required')
    # Reuse the existing native no-redirect handler; never accept a supplied
    # opener or clear the original injected-opener marker. No connection here.
    director=build_opener(_RecordedNoRedirect())
    _NATIVE[provider]=(director,_dispatch_fingerprint(director))


def recorded_transport_identity(provider):
    from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider
    if type(provider) is not SnapshotOpenAIResponsesProvider:
        raise ContractError('configured-recorded-native-provider-required')
    saved=_NATIVE.get(provider)
    if (saved is None or provider._injected_opener is not False
            or provider._transport_opener is not urlopen):
        raise ContractError('configured-recorded-native-dispatch-changed')
    _require_original_dispatch(saved[0],saved[1])
    return saved[0].open


def require_recorded_request(request):
    if (type(request) is not Request or request.full_url not in (
            'https://api.openai.com/v1/responses',
            'https://api.openai.com/v1/responses/input_tokens')
            or request.get_method() != 'POST'
            or type(request.data) is not bytes or not request.data
            or len(request.data) > 8*1024*1024
            or request.has_header('Host')):
        raise ContractError('configured-recorded-exact-request-required')


def open_native_recorded_transport(provider,request,kwargs):
    # This entry cannot be used independently of the native call lifecycle.
    opener=recorded_transport_identity(provider)
    if (provider.transport_recorder is None or not provider._recorded_call_active
            or provider._recorded_role not in ('planner','failure_analyst','builder')
            or type(kwargs) is not dict or set(kwargs) != {'timeout'}
            or type(kwargs['timeout']) not in (int,float)
            or not 0 < kwargs['timeout'] <= 240):
        raise ContractError('configured-recorded-active-call-required')
    require_recorded_request(request)
    from .configured_human_controller import _ROUTERS as public_routers
    from .configured_receipt_controller import _ROUTERS as receipt_routers
    old=[context for context,original in list(public_routers.items()) if original[1] is provider]
    receipt=[context for context,original in list(receipt_routers.items()) if original[1] is provider]
    if len(old)+len(receipt)!=1:
        raise ContractError('configured-recorded-unique-controller-required')
    if receipt:
        from .configured_receipt_wire_boundary import require_original_wire_open
    else:
        from .configured_human_wire_boundary import require_original_wire_open
    require_original_wire_open(provider,request)
    if recorded_transport_identity(provider) != opener:
        raise ContractError('configured-recorded-native-dispatch-changed')
    return opener(request,**kwargs)
