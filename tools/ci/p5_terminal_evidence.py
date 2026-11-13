"""Read-only relations for retained public refusal evidence, never admission.

The caller supplies original file bytes from a public drill. These functions
neither read a Factory root nor execute, sign, authorize, replay or resume a run.
They do not establish controller origin or satisfy strict P5 qualification.
"""
import base64
from hashlib import sha256
import json

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_execution.public_drill_runtime import verify_receipt_tail


FILES = ('receipt.json', 'summary.json', 'events.jsonl',
         'attempt-identity.json', 'attempt-accounting.jsonl')
LIMIT = 2 * 1024 * 1024


def _require(condition):
    if not condition:
        raise ValueError('p5-terminal-evidence-invalid')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite')))


def _chain(raw):
    _require(raw.endswith(b'\n') and all(line.strip() for line in raw.splitlines()))
    rows = [_json(line) for line in raw.splitlines()]
    _require(bool(rows))
    previous = None
    for index, event in enumerate(rows, 1):
        _require(type(event['sequence']) is int and event['sequence'] == index)
        _require(event['previous_sha256'] == previous)
        _require(event['event_sha256'] == canonical_hash(event, {'event_sha256'}))
        previous = event['event_sha256']
    return rows


def validate(value):
    """Validate retained byte relationships only; self-hashes are not origin."""
    try:
        _require(set(value) == {'schema', 'documents', 'run_id', 'receipt_sha256',
            'attempt_identity_sha256', 'event_head_sha256', 'accounting_head_sha256',
            'controller_origin_verified', 'execution_authorized', 'production_qualified',
            'qualifies_for_factory_receipt', 'resume_allowed', 'accounting_semantics_verified',
            'expected_refusal_verified', 'content_sha256'})
        _require(value['schema'] == 'p5-public-terminal-evidence-relations/1')
        _require(value['content_sha256'] == canonical_hash(value, {'content_sha256'}))
        for field in ('controller_origin_verified', 'execution_authorized', 'production_qualified',
                      'qualifies_for_factory_receipt', 'resume_allowed',
                      'accounting_semantics_verified', 'expected_refusal_verified'):
            _require(value[field] is False)
        docs = value['documents']
        _require(type(docs) is dict and set(docs) == set(FILES))
        originals = {}
        for name in FILES:
            row = docs[name]
            _require(set(row) == {'base64', 'bytes', 'sha256'})
            _require(type(row['bytes']) is int and 0 < row['bytes'] <= LIMIT)
            _require(type(row['base64']) is str and len(row['base64']) <= 4*((LIMIT+2)//3))
            raw = base64.b64decode(row['base64'], validate=True)
            _require(len(raw) == row['bytes'] and sha256(raw).hexdigest() == row['sha256'])
            originals[name] = raw
        receipt = _json(originals['receipt.json'])
        summary = _json(originals['summary.json'])
        identity = _json(originals['attempt-identity.json'])
        events = _chain(originals['events.jsonl'])
        accounting = _chain(originals['attempt-accounting.jsonl'])
        _require(receipt['receipt_type'] == 'lightyear-autonomous-factory-run')
        _require(receipt['status'] == summary['status'] == 'blocked')
        _require(receipt['reason'] == summary['reason'] == 'factory-isolation-run-refused')
        _require(type(receipt['attempts']) is int and 0 <= receipt['attempts'] <= 3)
        _require(type(summary['attempts']) is int and summary['attempts'] == receipt['attempts'])
        _require(type(receipt['repair_loops']) is int
                 and receipt['repair_loops'] == max(0, receipt['attempts']-1))
        _require(receipt.get('qualifies_for_factory_receipt') is not True)
        _require(receipt.get('factory_build_receipt', {}).get('qualifies_for_factory_receipt') is not True)
        _require(receipt['content_sha256'] == canonical_hash(receipt, {'content_sha256'}))
        _require(value['receipt_sha256'] == summary['receipt_sha256'] == receipt['content_sha256'])
        _require(identity['schema'] == 'factory-attempt-identity/1')
        _require(identity['content_sha256'] == canonical_hash(identity, {'content_sha256'}))
        _require(value['attempt_identity_sha256'] == identity['content_sha256'])
        _require(type(value['run_id']) is str and bool(value['run_id']))
        _require(value['run_id'] == identity['attempt_id'])
        if 'run_id' in receipt:
            _require(receipt['run_id'] == value['run_id'])
        _require(receipt['work_order_sha256'] == identity['work_order_sha256'])
        for kind, field, expected in (
                ('work_order_accepted', 'work_order_sha256', identity['work_order_sha256']),
                ('hardened_admission_bound', 'admission_receipt_sha256', identity['admission_receipt_sha256']),
                ('workspace_read_manifest', 'sha256', identity['workspace_inventory_sha256'])):
            matching = [event for event in events if event['kind'] == kind]
            _require(len(matching) == 1 and matching[0]['payload'].get(field) == expected)
        snapshot = verify_receipt_tail(receipt, summary, events)
        _require(events[snapshot-1]['state'] == 'BLOCKED')
        _require(not any(event['state'] in ('PASSED', 'BLOCKED', 'INTERRUPTED')
                         for event in events[:snapshot-1]))
        _require(value['event_head_sha256'] == events[-1]['event_sha256'])
        _require(value['accounting_head_sha256'] == accounting[-1]['event_sha256'])
        _require(events[snapshot-1]['kind'] == 'controller_error')
        _require(events[snapshot-1]['payload'] == {'reason': 'factory-isolation-run-refused'})
        _require(all(event['payload']['attempt_identity_sha256'] == identity['content_sha256']
                     for event in accounting))
        # This is deliberately not a protocol-specific accounting replay.
        # Consumers must still perform native replay and authenticated origin review.
        return True
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, UnicodeError, ContractError):
        raise ValueError('p5-terminal-evidence-invalid') from None


def retain(originals):
    """Encode exact caller-supplied bytes without reading or modifying files."""
    _require(type(originals) is dict and set(originals) == set(FILES))
    _require(all(type(raw) is bytes and 0 < len(raw) <= LIMIT for raw in originals.values()))
    receipt = _json(originals['receipt.json'])
    identity = _json(originals['attempt-identity.json'])
    events = _chain(originals['events.jsonl'])
    accounting = _chain(originals['attempt-accounting.jsonl'])
    value = dict(schema='p5-public-terminal-evidence-relations/1', documents={
        name: dict(base64=base64.b64encode(raw).decode('ascii'), bytes=len(raw),
                   sha256=sha256(raw).hexdigest()) for name, raw in originals.items()},
        run_id=identity['attempt_id'], receipt_sha256=receipt['content_sha256'],
        attempt_identity_sha256=identity['content_sha256'], event_head_sha256=events[-1]['event_sha256'],
        accounting_head_sha256=accounting[-1]['event_sha256'], controller_origin_verified=False,
        execution_authorized=False, production_qualified=False, qualifies_for_factory_receipt=False,
        resume_allowed=False, accounting_semantics_verified=False, expected_refusal_verified=False)
    value['content_sha256'] = canonical_hash(value)
    validate(value)
    return value
