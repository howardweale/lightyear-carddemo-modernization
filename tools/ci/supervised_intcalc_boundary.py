"""No-send engineering boundary using existing factory contracts and broker.

No model client, credentials, admission override, approval or run entry.
Every result is supervised engineering, never qualification evidence.
"""
import copy
from decimal import Decimal
import hashlib
import json
import re

from lightyear_factory.agents import BUILDER_SCHEMA
from lightyear_factory.contracts import ContractError
from lightyear_factory.patches import PatchBroker
from lightyear_factory.providers import _validate_schema

LABEL = 'supervised engineering run, not a qualified production run'
MODEL = 'gpt-5.4-2026-03-05'
PATH = 'factory/benchmarks/intcalc_candidate.py'
# Filled only from committed public source during static preparation.
PUBLIC_SOURCE_SHA256 = '4c4681f5ea294fd2c8c63193548611c241eb5d06224d0d49ef5694cd057d2799'
LINE = re.compile(rb'^MONTHS_PERCENT = ([1-9][0-9]{0,6})$', re.MULTILINE)


def _require(ok, reason):
    if not ok:
        raise ContractError('supervised-intcalc-' + reason)


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, 'duplicate-json-key')
        result[key] = value
    return result


def _json(raw, limit):
    _require(type(raw) is bytes and 0 < len(raw) <= limit, 'json-size')
    def bad_constant(value):
        raise ContractError('supervised-intcalc-nonfinite-json')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=bad_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ContractError('supervised-intcalc-invalid-json') from error


def checked_candidate(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= 16384, 'candidate-size')
    matches = list(LINE.finditer(raw))
    _require(len(matches) == 1, 'literal-line')
    match = matches[0]
    _require(1 <= int(match[1]) <= 1000000, 'literal-range')
    normalized = raw[:match.start()] + b'MONTHS_PERCENT = 1200' + raw[match.end():]
    _require(hashlib.sha256(normalized).hexdigest() == PUBLIC_SOURCE_SHA256,
             'candidate-outside-literal')
    return match[0]


def generation_request(raw):
    """Construct one bounded request. This function cannot send it."""
    checked_candidate(raw)
    body = dict(model=MODEL, service_tier='flex', store=False, background=False,
                stream=False, tools=[], tool_choice='none', truncation='disabled',
                max_output_tokens=4096,
                instructions=LABEL + '. Repair only the MONTHS_PERCENT integer literal. '
                'Monthly interest is annual percentage interest apportioned over twelve months. '
                'Preserve all other source bytes. Return the existing builder JSON contract. '
                'Do not claim qualification or request tools or private verifier data.',
                input=raw.decode('utf-8'),
                text={'format': {'type': 'json_schema', 'name': 'factory_builder',
                      'strict': True, 'schema': copy.deepcopy(BUILDER_SCHEMA)}})
    encoded = json.dumps(body, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    _require(len(encoded) <= 32768, 'request-size')
    return encoded


def documented_two_call_envelope():
    """Documented tariff assumption, NOT an implemented send/account limit."""
    return Decimal(2) * (Decimal('1.05') * Decimal('5.50')
                         + Decimal('0.128') * Decimal('24.75'))


def checked_proposal(candidate, proposal):
    current = checked_candidate(candidate).decode('ascii')
    _require(type(proposal) is dict, 'proposal-object')
    _validate_schema(proposal, BUILDER_SCHEMA, 'engineering_builder')
    _require(proposal['blocked_reason'] is None and len(proposal['edits']) == 1,
             'one-unblocked-edit')
    edit = proposal['edits'][0]
    _require(edit['path'] == PATH and edit['find'] == current, 'edit-scope')
    try:
        replacement = edit['replace'].encode('ascii')
    except UnicodeError as error:
        raise ContractError('supervised-intcalc-edit-literal') from error
    _require(LINE.fullmatch(replacement) is not None, 'edit-literal')
    proposed = candidate.replace(current.encode('ascii'), replacement, 1)
    checked_candidate(proposed)
    _require(proposed != candidate, 'edit-no-change')
    return proposed


def response_proposal(raw, candidate):
    """Accept only one completed Flex text result; never follow tools/refusals."""
    value = _json(raw, 1048576)
    _require(type(value) is dict and value.get('model') == MODEL
             and value.get('service_tier') == 'flex'
             and value.get('status') == 'completed', 'response-identity')
    output = value.get('output')
    _require(type(output) is list and 1 <= len(output) <= 16, 'response-output')
    texts = []
    for item in output:
        _require(type(item) is dict, 'response-item')
        if item.get('type') == 'reasoning':
            continue
        _require(item.get('type') == 'message' and item.get('role') == 'assistant'
                 and item.get('status') == 'completed', 'response-message')
        content = item.get('content')
        _require(type(content) is list and len(content) == 1, 'response-content')
        part = content[0]
        _require(type(part) is dict and part.get('type') == 'output_text'
                 and type(part.get('text')) is str, 'response-text')
        texts.append(part['text'])
    _require(len(texts) == 1, 'response-ambiguous')
    usage = value.get('usage')
    _require(type(usage) is dict, 'response-usage')
    for key, limit in (('input_tokens', 1050000), ('output_tokens', 4096)):
        _require(type(usage.get(key)) is int and 0 <= usage[key] <= limit,
                 'response-token-range')
    proposal = _json(texts[0].encode('utf-8'), 65536)
    checked_proposal(candidate, proposal)
    return proposal


def apply_checked_proposal(order, workspace, candidate, proposal):
    """Use the original broker only after whole-source and exact literal checks."""
    _require(order.allowed_paths == (PATH,) and order.max_files_changed == 1,
             'work-order-scope')
    _require(workspace.allowed_paths == (PATH,), 'workspace-scope')
    expected = checked_proposal(candidate, proposal)
    path = workspace.resolve(PATH)
    _require(path.read_bytes() == candidate, 'workspace-candidate-changed')
    result = PatchBroker().apply(order, workspace, proposal['edits'])
    _require(path.read_bytes() == expected, 'broker-result-changed')
    return dict(label=LABEL, broker=result,
                candidate_sha256=hashlib.sha256(expected).hexdigest(),
                qualification_evidence=False)
