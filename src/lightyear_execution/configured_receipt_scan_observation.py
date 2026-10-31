"""Original configured controller-context scan diagnostic; no outcome authority.

Keep only a digest/length tuple inside the existing terminal-origin registry.
Never retain raw context, expected values, an exception or traceback. The native
scanner and original refusal remain unchanged. No durable receipt schema,
admission, proof reentry, retry, qualification or cross-process attestation.
"""
from hashlib import sha256
import sys
from lightyear_factory.contracts import ContractError


def _describe_failed_bytes(name,raw,error):
    # Pure classification of untrusted arguments, not proof of scanner origin.
    from lightyear_factory.isolation_scan import MAX_BYTES
    if (type(name) is not str or name!='controller-context'
            or type(raw) is not bytes or not 0<len(raw)<=MAX_BYTES
            or type(error) is not ContractError or error.args!=('isolation-breach',)):
        raise ContractError('configured-context-scan-observation-shape')
    return sha256(raw).hexdigest(),len(raw)


def record_original_context_scan_failure(controller,surface,error):
    from lightyear_factory.orchestrator import FactoryOrchestrator
    from lightyear_factory.isolation_scan import scan
    from .configured_receipt_terminal import _require_origin
    saved=_require_origin(controller)
    caller=sys._getframe(1)
    trace=None;inspect_frame=None;scan_frame=None
    try:
        if (caller.f_code is not FactoryOrchestrator._scan_controller_value.__code__
                or caller.f_locals.get('self') is not controller
                or caller.f_locals.get('surface')!=surface
                or caller.f_locals.get('error') is not error
                or sys.exc_info()[1] is not error):
            raise ContractError('configured-context-scan-original-caller')
        # Original traceback must be outer scan wrapper -> captured original
        # scanner closure -> native scan's own breach. A failure while obtaining
        # expected values, in a replaced callback, or in a decoder does not fit.
        trace=error.__traceback__
        if trace is None or trace.tb_frame is not caller:
            raise ContractError('configured-context-scan-original-trace')
        trace=trace.tb_next
        if trace is None or trace.tb_frame.f_code is not saved['scanner'].__code__:
            raise ContractError('configured-context-scan-original-closure')
        inspect_frame=trace.tb_frame
        if (inspect_frame.f_locals.get('self') is not controller
                or inspect_frame.f_locals.get('name')!=surface
                or inspect_frame.f_locals.get('scan') is not scan):
            raise ContractError('configured-context-scan-original-binding')
        trace=trace.tb_next
        if trace is None or trace.tb_frame.f_code is not scan.__code__ or trace.tb_next is not None:
            raise ContractError('configured-context-scan-native-breach-required')
        scan_frame=trace.tb_frame;raw=inspect_frame.f_locals.get('raw')
        if (scan_frame.f_locals.get('name')!=surface
                or scan_frame.f_locals.get('raw') is not raw):
            raise ContractError('configured-context-scan-original-bytes')
        descriptor=_describe_failed_bytes(surface,raw,error)
        from .configured_receipt_scan_match import classify_stopping_view
        match=classify_stopping_view(scan_frame.f_locals.get('tokens'),
            scan_frame.f_locals.get('windows'),scan_frame.f_locals.get('normalized'))
        from .configured_receipt_case import is_answer_order
        intended=None
        if is_answer_order(controller.execution_context._order):
            from .configured_receipt_answer_stimulus import describe_original_answer_match
            intended=describe_original_answer_match(controller,caller.f_locals.get('value'),
                scan_frame.f_locals.get('normalized'))
        if 'context_scan_failure' in saved:
            # Multiple observations are ambiguous, never overwrite with a later
            # apparently good result. Existing registry cleanup removes this too.
            saved['context_scan_failure']=None
            saved.pop('context_scan_stopping_view_match',None)
            saved.pop('answer_context_match',None)
            raise ContractError('configured-context-scan-duplicate-observation')
        saved['context_scan_failure']=descriptor
        saved['context_scan_stopping_view_match']=match
        if intended is not None:saved['answer_context_match']=intended
    finally:
        # Do not add traceback/frame ownership to existing key lifetime roots.
        del caller,trace,inspect_frame,scan_frame


def emit_original_context_scan_failure(controller):
    from .configured_receipt_terminal import _require_origin
    saved=_require_origin(controller)
    value=saved.get('context_scan_failure')
    if value is None:
        return False  # Missing/ambiguous is unavailable, never a passed scan.
    # Fixed ASCII diagnostic only, no raw context or exception detail. This is
    # not a signed case outcome and supplies neither admission nor no-send proof.
    import re
    from lightyear_factory.isolation_scan import MAX_BYTES
    if (type(value) is not tuple or len(value)!=2
            or type(value[0]) is not str or not re.fullmatch('[0-9a-f]{64}',value[0])
            or type(value[1]) is not int or not 0<value[1]<=MAX_BYTES):
        raise ContractError('configured-context-scan-invalid-descriptor')
    digest,size=value
    match=saved.get('context_scan_stopping_view_match')
    if type(match) is not str or match not in ('canary','expected-window','canary-and-expected-window'):
        raise ContractError('configured-context-scan-match-unavailable')
    suffix=''
    from .configured_receipt_case import is_answer_order
    if is_answer_order(controller.execution_context._order):
        intended=saved.get('answer_context_match')
        if (type(intended) is not tuple or len(intended)!=3 or intended!=saved.get('answer_stimulus')
                or any(type(intended[i]) is not str or not re.fullmatch('[0-9a-f]{64}',intended[i]) for i in (0,2))
                or type(intended[1]) is not int or not 0<intended[1]<=20000):
            raise ContractError('configured-answer-intended-match-unavailable')
        suffix=' copied-worker-sha256='+intended[0]+' intended-fragment-sha256='+intended[2]
    sys.stderr.write('configured-original-controller-context-scan-breach '
        +'sha256='+digest+' bytes='+str(size)+' stopping-view-match='+match+suffix+'\n')
    return True
