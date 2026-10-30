"""Prospective graph evaluations require a dated, response-verified snapshot."""
import re
from datetime import date

def require_snapshot(value):
    if not isinstance(value,str):raise ValueError('dated model snapshot required')
    # Explicit numbered Gemini versions, never preview/latest or unversioned aliases.
    if re.fullmatch(r'gemini-[0-9]+\.[0-9]+-[a-z]+(?:-[a-z]+)*-[0-9]{3}',value):return value
    match=re.search(r'(?:^|[-_])(20[0-9]{2})-?([01][0-9])-?([0-3][0-9])$',value)
    if not match:raise ValueError('dated model snapshot required; aliases are not admitted')
    date(*map(int,match.groups()))
    return value

def verify_response(provider,response):
    if getattr(provider,'require_snapshot_response',False):
        require_snapshot(provider.model)
        actual=response.get('modelVersion') if provider.provider_id=='gemini-generate-content' else response.get('model')
        if actual!=provider.model:raise ValueError('response model snapshot differs or absent')


# Keep the historical MS70 provider bytes unchanged; prospective graph runs use
# this adapter to verify the raw response before the base provider interprets it.
from contextlib import contextmanager
from io import BytesIO
import json
from .providers import OpenAIResponsesProvider
from .contracts import ContractError


class SnapshotOpenAIResponsesProvider(OpenAIResponsesProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        require_snapshot(self.model)
        self.require_snapshot_response = True
        self._transport_opener = self.opener
        self.opener = self._open_verified
        self.transport_recorder = None
        self.last_transport_record = None
        self._transport_started = False
        self._recorded_call_active = False
        self._recorded_role = None

    def bind_transport_recorder(self, recorder):
        # Opt-in only, before the first call. Old unrecorded execution remains
        # unchanged. No injected-opener marker is cleared or overridden.
        from lightyear_execution.configured_human_wire import require_native_recorder_binding
        if (self.transport_recorder is not None or self.last_transport_record is not None
                or self._transport_started or self._recorded_call_active):
            raise ContractError('configured-wire-recorder-reuse')
        require_native_recorder_binding(self, recorder)
        if recorder.admitted_call is not None:
            raise ContractError('configured-wire-bind-before-admission')
        from lightyear_execution.configured_human_recorded_transport import bind_native_recorded_transport
        bind_native_recorded_transport(self)
        self.transport_recorder = recorder

    def complete(self, role, instruction, payload, schema):
        self._transport_started = True
        recorder = self.transport_recorder
        if recorder is None:
            return super().complete(role, instruction, payload, schema)
        from lightyear_execution.configured_human_wire import require_native_recorder_binding
        require_native_recorder_binding(self, recorder)
        admission = recorder.admitted_call
        if (self._recorded_call_active or type(admission) is not tuple
                or len(admission) != 2 or type(admission[1]) is not dict
                or admission[1].get('requested_role') != role):
            raise ContractError('configured-wire-current-role-admission-required')
        self.last_transport_record = None
        self._recorded_call_active = True
        self._recorded_role = role
        try:
            result = super().complete(role, instruction, payload, schema)
            record = self.last_transport_record
            if (record is None or record.get('status') != 'response'
                    or record.get('response_complete') is not True
                    or record.get('requested_role') != role
                    or recorder.pending is not None or recorder.admitted_call is not None):
                raise ContractError('configured-wire-complete-original-record-required')
            from copy import deepcopy
            from .contracts import canonical_hash
            evidence = dict(result.evidence, transport_record=deepcopy(record))
            evidence['content_sha256'] = canonical_hash(evidence, {'content_sha256'})
            return type(result)(result.content, evidence)
        finally:
            self._recorded_role = None
            self._recorded_call_active = False

    @contextmanager
    def _open_recorded_generation(self, request, **kwargs):
        from lightyear_execution.configured_human_wire import (
            begin_original_generation, finish_original_generation, bounded_response_bytes)
        from urllib.error import HTTPError
        recorder = self.transport_recorder
        if (not self._recorded_call_active or recorder is None
                or recorder.admitted_call is None
                or recorder.admitted_call[1].get('requested_role') != self._recorded_role):
            raise ContractError('configured-wire-active-call-required')
        started = begin_original_generation(self, recorder, request)
        self.last_transport_record = started
        raw = None; complete = False; headers = None
        try:
            from lightyear_execution.configured_human_recorded_transport import open_native_recorded_transport
            with open_native_recorded_transport(self, request, kwargs) as response:
                raw, complete = bounded_response_bytes(response)
                headers = getattr(response, 'headers', {})
        except HTTPError as error:
            try:
                raw, complete = bounded_response_bytes(error)
            except Exception:
                raw = None; complete = False
            finally:
                try: error.close()
                except Exception: pass
            finish_original_generation(self, recorder, started, raw,
                                       status='http-error', complete=complete)
            # No retry in the admitted recorded path. The exact encrypted body
            # is retained; credential-bearing exception details are not emitted.
            raise ContractError('configured-wire-http-refused') from None
        except Exception:
            finish_original_generation(self, recorder, started, raw,
                                       status='transport-error', complete=complete)
            raise ContractError('configured-wire-transport-refused') from None
        finish_original_generation(self, recorder, started, raw,
                                   status='response', complete=complete)
        if not complete:
            raise ContractError('configured-wire-incomplete-response')
        # Preserve the native physical-journal and snapshot checks. A retained
        # response is not automatically a valid provider result or qualification.
        from .transport_journal import report_transport_payload
        report_transport_payload(raw)
        try:
            verify_response(self, json.loads(raw.decode('utf-8')))
        except (ValueError, TypeError) as error:
            raise ContractError('configured-wire-snapshot-response-refused') from None
        with BytesIO(raw) as verified:
            verified.headers = headers
            yield verified

    @contextmanager
    def _open_verified(self, request, **kwargs):
        if self.transport_recorder is not None:
            from lightyear_execution.configured_human_recorded_transport import (
                require_recorded_request, open_native_recorded_transport)
            require_recorded_request(request)
            if request.full_url == 'https://api.openai.com/v1/responses':
                with self._open_recorded_generation(request, **kwargs) as response:
                    yield response
            else:
                # The native count-charge/physical journal still owns this
                # count. No redirect may add an unreserved second request.
                from lightyear_execution.configured_human_wire import bounded_count_response
                with open_native_recorded_transport(self, request, kwargs) as response:
                    # Bound the original body and prove framing before the base
                    # count parser can report a count to either accounting scope.
                    with bounded_count_response(response) as buffered:
                        yield buffered
            return
        with self._transport_opener(request, **kwargs) as response:
            if request.full_url != 'https://api.openai.com/v1/responses':
                yield response
                return
            raw = response.read()
            from .transport_journal import report_transport_payload
            report_transport_payload(raw)
            try:
                verify_response(self, json.loads(raw.decode('utf-8')))
            except ValueError as exc:
                raise ContractError(str(exc)) from None
            with BytesIO(raw) as verified:
                verified.headers = getattr(response, 'headers', {})
                yield verified
