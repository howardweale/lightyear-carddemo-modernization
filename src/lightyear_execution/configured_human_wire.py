"""Inactive bounded wire-retention primitives for native configured integration.

These functions neither open a connection nor grant admission. The controller
must bind the original recorder and genuine role proof before any invocation.
No caller-provided callback, signer, key generator or qualification path exists.
"""
from contextlib import contextmanager
from io import BytesIO
from copy import deepcopy
from http.client import HTTPResponse, IncompleteRead
from urllib.error import HTTPError
from urllib.request import urlopen

from lightyear_factory.contracts import ContractError

LIMIT = 8 * 1024 * 1024


def bounded_response_bytes(response):
    """Return original bytes and completeness without decoding or canonicalizing.

    A cap or partial read is evidence of an incomplete response, never success.
    Callers must persist that distinction before refusing interpretation.
    """
    # Native HTTPResponse.read(n) may return EOF without IncompleteRead while
    # Content-Length bytes remain. HTTPError delegates reads to that same
    # response, so retain its original framing object before reading.
    framing = response.fp if type(response) is HTTPError else response
    try:
        raw = response.read(LIMIT + 1)
    except IncompleteRead as error:
        raw = error.partial
        if type(raw) is not bytes:
            raise ContractError('configured-wire-partial-byte-type') from None
        return raw[:LIMIT], False
    except OSError:
        # A network error before any returned bytes is an unknown/incomplete
        # body. It cannot become an empty successful provider response.
        return b'', False
    if type(raw) is not bytes:
        raise ContractError('configured-wire-response-byte-type')
    if len(raw) > LIMIT:
        return raw[:LIMIT], False
    # read(n) is permitted to return fewer bytes than n without EOF. A second
    # read must prove EOF; otherwise retain the complete bounded prefix.
    chunks = [raw]
    total = len(raw)
    while raw:
        try:
            raw = response.read(LIMIT - total + 1)
        except IncompleteRead as error:
            if type(error.partial) is not bytes:
                raise ContractError('configured-wire-partial-byte-type') from None
            return (b''.join(chunks) + error.partial)[:LIMIT], False
        except OSError:
            # Preserve already observed bytes even if a later read fails.
            return b''.join(chunks), False
        if type(raw) is not bytes:
            raise ContractError('configured-wire-response-byte-type')
        chunks.append(raw); total += len(raw)
        if total > LIMIT:
            return b''.join(chunks)[:LIMIT], False
    if type(framing) is HTTPResponse:
        if framing.chunked:
            complete = framing.chunk_left is None and framing.isclosed()
        else:
            complete = framing.length is None or (type(framing.length) is int and framing.length == 0)
        return b''.join(chunks), complete
    # Generic byte streams keep their existing EOF semantics. This helper
    # grants no admission; only the native transport opens real requests.
    return b''.join(chunks), True


@contextmanager
def bounded_count_response(response):
    """Buffer a complete bounded count body before the existing parser sees it.

    No count, accounting result, admission or encrypted generation record is
    manufactured here. The caller owns the original response context. Refusal
    propagates through the original physical observer and count-charge scope,
    which retain an unknown result and the existing conservative hold.
    """
    raw, complete = bounded_response_bytes(response)
    if not complete:
        raise ContractError('configured-wire-incomplete-count-response')
    with BytesIO(raw) as buffered:
        buffered.headers = getattr(response, 'headers', {})
        yield buffered


def require_native_recorder_binding(provider, recorder):
    """Refuse forged types and altered transport; never reconstruct authority."""
    from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider
    from lightyear_factory.model_transport_records import ModelTransportRecorder
    if (type(provider) is not SnapshotOpenAIResponsesProvider
            or type(recorder) is not ModelTransportRecorder
            or provider._injected_opener is not False
            or provider._transport_opener is not urlopen
            or getattr(provider.opener, '__self__', None) is not provider
            or getattr(provider.opener, '__func__', None) is not SnapshotOpenAIResponsesProvider._open_verified
            or provider.max_retries != 0 or provider.token_preflight is not True
            or provider.require_snapshot_response is not True
            or recorder.require_model_admission is not True
            or recorder.failed or recorder.pending is not None):
        raise ContractError('configured-wire-native-binding-required')
    if provider.transport_recorder is not None:
        from .configured_human_recorded_transport import recorded_transport_identity
        recorded_transport_identity(provider)
    # A live recorder still has to validate the original admission event and
    # its persisted ledger in begin(); this check cannot replace that step.


def begin_original_generation(provider, recorder, request):
    require_native_recorder_binding(provider, recorder)
    admission = recorder.admitted_call
    if (provider.transport_recorder is not recorder
            or type(request.data) is not bytes or len(request.data) > LIMIT
            or request.full_url != 'https://api.openai.com/v1/responses'
            or request.get_method() != 'POST'
            or type(admission) is not tuple or len(admission) != 2
            or type(admission[1]) is not dict
            or admission[1].get('provider') != provider.provider_id
            or admission[1].get('model') != provider.model
            or admission[1].get('requested_role') not in ('planner', 'failure_analyst', 'builder')):
        raise ContractError('configured-wire-original-generation-required')
    # Preserve exact sent bytes, including their actual JSON key order. Native
    # begin() verifies the persisted concrete admission before encrypted write.
    return recorder.begin(admission[1]['requested_role'], provider.provider_id,
                          provider.model, request.data)


def finish_original_generation(provider, recorder, started, raw, *, status, complete):
    # No re-entry into current proof APIs after a failure/window expiry. The
    # original recorder's pending event is the sole finish binding.
    from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider
    from lightyear_factory.model_transport_records import ModelTransportRecorder
    if (type(provider) is not SnapshotOpenAIResponsesProvider
            or type(recorder) is not ModelTransportRecorder
            or provider.transport_recorder is not recorder
            or type(complete) is not bool
            or (raw is not None and (type(raw) is not bytes or len(raw) > LIMIT))
            or (raw is None and complete)):
        raise ContractError('configured-wire-original-finish-required')
    record = recorder.finish(started, raw, status=status, complete=complete)
    provider.last_transport_record = deepcopy(record)
    return record
