"""Read-only native replay of retained public terminal accounting, not origin."""
import base64
from copy import deepcopy
import json

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.orchestrator import (
    _reconcile_accounting_journal, _validate_reconciliation_accounting)
from tools.ci.p5_terminal_evidence import validate as validate_relations


def replay(retained):
    """Hash-chain checks precede native semantics; legacy replay grants no send."""
    validate_relations(retained)
    raw = base64.b64decode(retained['documents']['attempt-accounting.jsonl']['base64'], validate=True)
    events = [json.loads(line) for line in raw.splitlines()]
    accounting = _reconcile_accounting_journal(events, retained['attempt_identity_sha256'])
    receipt_raw = base64.b64decode(retained['documents']['receipt.json']['base64'], validate=True)
    receipt_accounting = json.loads(receipt_raw)['failure_accounting']
    _validate_reconciliation_accounting(receipt_accounting)
    snapshots = [event['payload']['accounting'] for event in events
                 if event['kind'] == 'sanitized_accounting']
    if not snapshots:
        raise ValueError('terminal-accounting-checkpoint-missing')
    checkpoint = snapshots[-1]
    _validate_reconciliation_accounting(checkpoint)
    # Native receipt creation follows the checkpoint, so elapsed time can grow.
    # Compare canonical JSON to reject Python's bool/int/float equality aliases.
    reported = {key: value for key, value in receipt_accounting.items() if key != 'duration_ms'}
    observed = {key: value for key, value in checkpoint.items() if key != 'duration_ms'}
    if (canonical_hash(reported) != canonical_hash(observed)
            or receipt_accounting['duration_ms'] < checkpoint['duration_ms']):
        raise ValueError('terminal-accounting-receipt-checkpoint-mismatch')
    if accounting.get('billing_final') is not False:
        raise ValueError('terminal-accounting-billing-final-refused')
    result = dict(schema='p5-public-terminal-accounting-replay/1',
        retained_evidence_sha256=retained['content_sha256'],
        accounting_file_sha256=retained['documents']['attempt-accounting.jsonl']['sha256'],
        identity_sha256=retained['attempt_identity_sha256'],
        accounting_head_sha256=retained['accounting_head_sha256'],
        journal_protocol=events[0]['payload'].get('protocol'),
        replay_scope='historical retained bytes only; no send or recovery execution',
        native_replay_completed=True, replayed_accounting=deepcopy(accounting),
        receipt_checkpoint_fields_match=True,
        checkpoint_duration_ms=checkpoint['duration_ms'],
        receipt_duration_ms=receipt_accounting['duration_ms'],
        controller_origin_verified=False, execution_authorized=False,
        resume_allowed=False, production_qualified=False, qualifies_for_factory_receipt=False,
        expected_refusal_verified=False, actual_provider_cost_verified=False)
    result['content_sha256'] = canonical_hash(result)
    return result


def validate(value, retained):
    try:
        expected = replay(retained)
        if (type(value) is not dict
                or value.get('content_sha256') != canonical_hash(value, {'content_sha256'})
                or value != expected):
            raise ValueError('terminal-accounting-replay-mismatch')
        return True
    except (KeyError, TypeError, ValueError, ContractError):
        raise ValueError('terminal-accounting-replay-invalid') from None
