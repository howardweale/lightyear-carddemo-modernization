"""Original terminal byte relationships after child reap; no outcome authority.

Retained copies are not authenticated origin evidence. This reader cannot replace
the same-process origin checks, attest descendant death or qualify any strict case.
It never reenters admission/proof, signs, resumes or reconciles by writing records.
"""
from pathlib import Path
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.model_admission import _bounded_regular_bytes
from .configured_receipt_terminal import _original_json, _ledger_bytes
from .configured_abort_preflight_join import match_abort_preflight
from .configured_consumption_evidence import consumption_message_bytes, check_consumption_admission_relations
from .configured_consumption_observation import observe_existing_consumption

TERMINAL_LIMITS = {'receipt.json': 1024*1024, 'summary.json': 1024*1024,
    'attempt-identity.json': 65536, 'events.jsonl': 32*1024*1024,
    'attempt-accounting.jsonl': 32*1024*1024}
ROOT_LIMITS = {'human-admission.json': 1024*1024, 'human-consumption.json': 1024*1024,
    'admission-nonces.sha256': 1024}


def _require(value, reason):
    if not value: raise ContractError('configured-terminal-preflight-'+reason)


def match_terminal_records(admission, identity, receipt, summary, events):
    """Pure relationships only, including ordinary blocked native receipts."""
    for row in (admission, identity, receipt):
        _require(type(row) is dict and row.get('content_sha256') ==
            canonical_hash(row, {'content_sha256'}), 'record-digest')
    _require(admission.get('schema') == 'factory-human-drill-context-admission/1'
        and admission.get('status') == 'passed' and admission.get('stub_only') is False
        and admission.get('output_qualified') is False and admission.get('resume_allowed') is False,
        'admission-shape')
    nonce = admission.get('nonce_sha256')
    import re
    _require(type(nonce) is str and re.fullmatch('[0-9a-f]{64}', nonce), 'nonce')
    run_id = 'drill-'+nonce[:32]
    _require(identity.get('schema') == 'factory-attempt-identity/1'
        and identity.get('attempt_id') == run_id
        and identity.get('admission_receipt_sha256') == admission['content_sha256']
        and identity.get('consumed_nonce_sha256') == nonce
        and identity.get('work_order_sha256') == admission.get('work_order_sha256'), 'identity-binding')
    _require(receipt.get('receipt_type') == 'lightyear-autonomous-factory-run'
        and receipt.get('status') in ('passed', 'blocked')
        and receipt.get('work_order_sha256') == identity.get('work_order_sha256')
        and ('run_id' not in receipt or receipt['run_id'] == run_id)
        and type(summary) is dict and summary.get('receipt_sha256') == receipt['content_sha256']
        and summary.get('status') == receipt['status'], 'receipt-binding')
    # Native isolation-refusal receipts omit run_id/execution_security. Their
    # binding is through the original identity, work order and ledger snapshot;
    # omission is not filled with invented fields or interpreted as success.
    _require(type(events) is list and bool(events), 'events')
    for kind, key, value in (
        ('work_order_accepted', 'work_order_sha256', identity['work_order_sha256']),
        ('hardened_admission_bound', 'admission_receipt_sha256', admission['content_sha256']),
        ('workspace_read_manifest', 'sha256', identity.get('workspace_inventory_sha256'))):
        rows = [e for e in events if e.get('kind') == kind]
        _require(value is not None and len(rows) == 1 and rows[0].get('payload', {}).get(key) == value,
            'ledger-binding')
    from .configured_receipt_build_bindings import verify_configured_terminal_build as verify_receipt_tail
    verify_receipt_tail(receipt, summary, events)
    return None


def match_terminal_count_accounting(receipt, replay):
    """Join an asserted count report to native replay; no authority or billing finality."""
    _require(type(receipt) is dict and type(replay) is dict, 'count-records')
    expected = replay.get('count_financial_accounting')
    _require(type(expected) is dict and expected.get('content_sha256') ==
        canonical_hash(expected, {'content_sha256'}), 'count-replay')
    if 'count_financial_accounting' not in receipt:
        # This native early isolation-refusal form predates the full receipt
        # construction. Absence stays absence: never synthesize a count report.
        _require(receipt.get('status') == 'blocked'
            and receipt.get('reason') == 'factory-isolation-run-refused'
            and receipt.get('qualifies_for_factory_receipt') is False
            and not any(k in receipt for k in ('run_id', 'execution_security', 'intelligence')),
            'count-report-missing')
        from lightyear_factory.orchestrator import _validate_reconciliation_accounting
        _validate_reconciliation_accounting(receipt.get('failure_accounting'))
        return None
    report = receipt['count_financial_accounting']
    _require(type(report) is dict and report.get('content_sha256') ==
        canonical_hash(report, {'content_sha256'}), 'count-report-digest')
    # Canonical JSON hashes distinguish Boolean values from integer zero/one;
    # plain Python dictionary equality would accept those substitutions.
    _require(canonical_hash(report) == canonical_hash(expected), 'count-report-binding')
    return None


def match_terminal_failure_accounting(receipt, accounting):
    """Compare an asserted failure snapshot with the original final checkpoint."""
    _require(type(receipt) is dict, 'failure-receipt')
    if 'failure_accounting' not in receipt:
        # Native final package qualification may block a formerly passed receipt
        # without adding a failure snapshot. Absence supplies no accounting claim.
        return None
    from lightyear_factory.orchestrator import _validate_reconciliation_accounting
    reported = receipt['failure_accounting']
    _validate_reconciliation_accounting(reported)
    _require(type(accounting) is list, 'failure-journal')
    snapshots = [e['payload']['accounting'] for e in accounting
        if e.get('kind') == 'sanitized_accounting']
    _require(bool(snapshots), 'failure-checkpoint-missing')
    checkpoint = snapshots[-1]
    _validate_reconciliation_accounting(checkpoint)
    # Both native failure constructors checkpoint before sampling the receipt.
    # Non-model scan names return without appending an accounting checkpoint.
    # Do not compare against replay's enriched pending/unknown result instead.
    reported_fields = {k: v for k, v in reported.items() if k != 'duration_ms'}
    observed_fields = {k: v for k, v in checkpoint.items() if k != 'duration_ms'}
    _require(canonical_hash(reported_fields) == canonical_hash(observed_fields)
        and reported['duration_ms'] >= checkpoint['duration_ms'], 'failure-checkpoint-binding')
    return None


def read_terminal_candidate_files(runs_root):
    root = Path(runs_root)
    _require(root.is_absolute() and root.is_dir()
        and not any(p.casefold() == 'onedrive' for p in root.parts), 'root')
    _require(not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
        for p in (root, *root.parents)), 'redirected-root')
    _require(not any((p/'.git').exists() for p in (root, *root.parents)), 'source-root')
    first = _bounded_regular_bytes(root/'human-admission.json', ROOT_LIMITS['human-admission.json'],
        'configured-terminal-preflight-admission')
    admission = _original_json(first)
    import re
    nonce = admission.get('nonce_sha256') if type(admission) is dict else None
    _require(type(nonce) is str and re.fullmatch('[0-9a-f]{64}', nonce), 'nonce')
    run = root/('drill-'+nonce[:32]); retained = root/'terminal-originals'
    limits = {**ROOT_LIMITS, **TERMINAL_LIMITS}
    paths = {k: (root if k in ROOT_LIMITS else run)/k for k in limits}
    raw = {k: _bounded_regular_bytes(paths[k], limit, 'configured-terminal-preflight-file')
        for k, limit in limits.items()}
    _require(raw['human-admission.json'] == first, 'admission-changed')
    def compare_retained():
        _require(retained.is_dir() and {p.name for p in retained.iterdir()} == set(TERMINAL_LIMITS),
            'retained-inventory')
        _require(all(_bounded_regular_bytes(retained/k, limit, 'configured-terminal-preflight-retained')
            == raw[k] for k, limit in TERMINAL_LIMITS.items()), 'retained-bytes')
    compare_retained()
    identity = _original_json(raw['attempt-identity.json'])
    events = _ledger_bytes(raw['events.jsonl'])
    match_terminal_records(admission, identity, _original_json(raw['receipt.json']),
        _original_json(raw['summary.json']), events)
    consumption = _original_json(raw['human-consumption.json'])
    _require(consumption_message_bytes(consumption) == raw['human-consumption.json'], 'consumption-bytes')
    check_consumption_admission_relations(consumption, admission)
    _require(raw['admission-nonces.sha256'] == (nonce+'\n').encode('ascii'), 'nonce-mirror')
    accounting = _ledger_bytes(raw['attempt-accounting.jsonl'])
    _require(accounting[0].get('kind') == 'model_reservations'
        and accounting[0].get('payload', {}).get('protocol') == 5
        and accounting[0]['payload'].get('count_bound_profile') == 'request-bytes-v1', 'accounting-header')
    from lightyear_factory.orchestrator import _reconcile_accounting_journal
    replay = _reconcile_accounting_journal(accounting, identity['content_sha256'])
    match_terminal_count_accounting(_original_json(raw['receipt.json']), replay)
    match_terminal_failure_accounting(_original_json(raw['receipt.json']), accounting)
    compare_retained()
    _require(all(_bounded_regular_bytes(paths[k], limits[k], 'configured-terminal-preflight-stable')
        == value for k, value in raw.items()), 'files-changed')
    return raw


def read_preflight_bound_terminal(runs_root, review, live_ci, *, runtime):
    raw = read_terminal_candidate_files(runs_root)
    admission = _original_json(raw['human-admission.json'])
    match_abort_preflight(admission, review, live_ci)
    from .configured_terminal_runtime_join import match_terminal_runtime
    match_terminal_runtime(_original_json(raw['receipt.json']),admission,
        _original_json(raw['attempt-identity.json']),runtime)
    observed = observe_existing_consumption(_original_json(raw['human-consumption.json']), admission)
    _require(read_terminal_candidate_files(runs_root) == raw, 'changed-during-service-read')
    return {'original_files': raw, 'service_observations': observed}
