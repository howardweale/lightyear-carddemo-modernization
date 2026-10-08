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

    @contextmanager
    def _open_verified(self, request, **kwargs):
        with self._transport_opener(request, **kwargs) as response:
            if request.full_url != 'https://api.openai.com/v1/responses':
                yield response
                return
            raw = response.read()
            try:
                verify_response(self, json.loads(raw.decode('utf-8')))
            except ValueError as exc:
                raise ContractError(str(exc)) from None
            with BytesIO(raw) as verified:
                verified.headers = getattr(response, 'headers', {})
                yield verified
