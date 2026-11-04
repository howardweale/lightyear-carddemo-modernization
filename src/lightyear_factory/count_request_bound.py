"""Proposed engineering count hold, not a provider billing guarantee.

Numbers and limitation COUNT-REQUEST-BOUND-01 await operator approval.
The exact request is bounded before any send. No tokenizer/model is invoked.
"""
from hashlib import sha256
import json

from .contracts import ContractError, canonical_hash
from .count_charge_account import CountInputBound


MODEL = 'gpt-5.4-2026-03-05'
MARGIN = 2
PER_MESSAGE_ALLOWANCE = 1024
LOGICAL_MESSAGES = 2  # one instructions message and one input string, even empty
CONTEXT_WINDOW = 1050000
LIMITATION = 'COUNT-REQUEST-BOUND-01'


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError('count-bound-duplicate-json-key')
        result[key] = value
    return result


def _constant(value):
    raise ContractError('count-bound-nonfinite-json')


def bound_basis(request_sha256, request_bytes):
    if (not isinstance(request_sha256, str) or len(request_sha256) != 64
            or any(c not in '0123456789abcdef' for c in request_sha256)
            or type(request_bytes) is not int or request_bytes < 1):
        raise ContractError('count-bound-request-identity')
    tokens = request_bytes*MARGIN + LOGICAL_MESSAGES*PER_MESSAGE_ALLOWANCE
    if tokens > CONTEXT_WINDOW:
        raise ContractError('count-bound-exceeds-context-before-send')
    return dict(schema='factory-count-request-bound/1', model=MODEL,
        endpoint='https://api.openai.com/v1/responses/input_tokens',
        request_sha256=request_sha256, request_bytes=request_bytes,
        margin=MARGIN, logical_messages=LOGICAL_MESSAGES,
        per_message_allowance=PER_MESSAGE_ALLOWANCE, input_tokens=tokens,
        context_window=CONTEXT_WINDOW, limitation_id=LIMITATION,
        provider_bound_proven=False, billing_final=False)


def request_bound_basis(raw):
    if type(raw) is not bytes:
        raise ContractError('count-bound-immutable-bytes-required')
    # Length refusal precedes parsing as well as every possible transport.
    basis = bound_basis(sha256(raw).hexdigest(), len(raw))
    try:
        body = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)
        if (type(body) is not dict or set(body) != {'model','instructions','input','text'}
                or body['model'] != MODEL or type(body['instructions']) is not str
                or type(body['input']) is not str or type(body['text']) is not dict
                or set(body['text']) != {'format'}):
            raise ContractError('count-bound-unsupported-request-surface')
        fmt = body['text']['format']
        if (type(fmt) is not dict or set(fmt) != {'type','name','schema','strict'}
                or fmt['type'] != 'json_schema' or fmt['strict'] is not True
                or fmt['name'] not in {'lightyear_planner_artifact','lightyear_builder_artifact',
                                       'lightyear_failure_analyst_artifact'}
                or type(fmt['schema']) is not dict):
            raise ContractError('count-bound-unsupported-format')
        # Reject unpaired surrogates and non-finite nested values; do not rewrite q.
        json.dumps(body,ensure_ascii=False,allow_nan=False).encode('utf-8')
    except (ValueError,UnicodeError,RecursionError):
        raise ContractError('count-bound-invalid-json') from None
    return basis


def serialized_count_bound(raw):
    basis = request_bound_basis(raw)
    return CountInputBound(basis['request_sha256'],basis['input_tokens'],canonical_hash(basis),
                           json.dumps(basis,sort_keys=True,separators=(',',':')))


def validate_retained_basis(basis, request_sha256, tokens, evidence_sha256):
    if (type(basis) is not dict or basis != bound_basis(request_sha256,basis.get('request_bytes'))
            or tokens != basis['input_tokens'] or evidence_sha256 != canonical_hash(basis)):
        raise ContractError('count-bound-retained-basis-mismatch')
    return dict(basis)
