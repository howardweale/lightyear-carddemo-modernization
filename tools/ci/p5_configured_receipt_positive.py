"""One genuine main receipt invocation and original evidence checks.

Requires the separately approved live proof, execution gate and secret scopes.
No fake proof, injected verifier, retry, secondary invocation or strict result.
A successful process means these component checks passed, not 19-case GO.
"""
import json,os,sys
from pathlib import Path

def require(value,reason):
    if not value:raise ValueError(reason)

def _observe_failed_dispatch_registry_state(run):
    # The original dispatcher has unwound its own terminal-retention/release
    # finally blocks. Observe only; never re-enter proof, release or admission.
    # Fixed log text cannot establish admission, key erasure or a case outcome.
    state='configured-failure-matching-registry-observation-unavailable'
    try:
        from lightyear_execution.configured_receipt_release import require_no_retained_receipt_attempt
        require_no_retained_receipt_attempt(run)
        state='configured-failure-matching-registry-absence-observed'
    except BaseException:
        # Preserve the original dispatch exception even if observation fails.
        # No exception values, run paths, provider/key values or hashes emitted.
        pass
    try:
        print(state,file=sys.stderr,flush=True)
    except BaseException:
        # Missing log output remains unknown; it must not replace the cause.
        pass

def main(argv=None):
    require(os.environ.get('GITHUB_ACTIONS')=='true','receipt-positive-ci-only')
    from lightyear_factory.cli import build_parser
    from lightyear_factory.contracts import canonical_hash
    from lightyear_factory.model_admission import _bounded_regular_bytes
    from lightyear_execution.configured_receipt_dispatch import _prepare,_dispatch_paths,dispatch_configured_receipt
    from lightyear_execution.configured_receipt_terminal import _original_json,_ledger_bytes
    from lightyear_execution.configured_receipt_build_bindings import verify_configured_terminal_build as verify_receipt_tail
    arguments=list(sys.argv[1:] if argv is None else argv)
    args=build_parser().parse_args(['human-configured-receipt-execute',*arguments])
    before=_prepare(args);root,_=_dispatch_paths(args,before)
    review=before['review'];expected_id='drill-'+review['drill_binding']['nonce_sha256'][:32]
    # Exactly one original dispatcher call. Its own same-process checks enforce
    # three genuine roles, six count/generation sends and native signed receipt.
    # Any exception is terminal for this attempted case; no retry or recovery.
    try:
        returned=dispatch_configured_receipt(args)
    except BaseException:
        _observe_failed_dispatch_registry_state(root/expected_id)
        raise
    run=root/expected_id;retained=root/'terminal-originals'
    from lightyear_execution.configured_receipt_release import require_no_retained_receipt_attempt
    require_no_retained_receipt_attempt(run)
    sizes={'receipt.json':1024*1024,'summary.json':1024*1024,'attempt-identity.json':65536,
           'events.jsonl':32*1024*1024,'attempt-accounting.jsonl':32*1024*1024}
    raw={name:_bounded_regular_bytes(run/name,limit,'receipt-positive-original') for name,limit in sizes.items()}
    for name,limit in sizes.items():
        require(_bounded_regular_bytes(retained/name,limit,'receipt-positive-retained')==raw[name],
                'receipt-positive-retained-byte-mismatch')
    receipt=_original_json(raw['receipt.json']);summary=_original_json(raw['summary.json'])
    identity=_original_json(raw['attempt-identity.json']);events=_ledger_bytes(raw['events.jsonl'])
    _ledger_bytes(raw['attempt-accounting.jsonl'])
    admission=_original_json(_bounded_regular_bytes(root/'human-admission.json',1024*1024,'receipt-positive-admission'))
    for value in (receipt,identity,admission):
        require(type(value) is dict and value.get('content_sha256')==canonical_hash(value,{'content_sha256'}),
                'receipt-positive-record-digest')
    require(returned==receipt and receipt.get('run_id')==expected_id and receipt.get('status')=='passed'
            and receipt.get('work_order_sha256')==before['order'].content_sha256,
            'receipt-positive-original-return-binding')
    verify_receipt_tail(receipt,summary,events)
    require(identity.get('attempt_id')==expected_id
            and identity.get('consumed_nonce_sha256')==admission.get('nonce_sha256')==review['drill_binding']['nonce_sha256']
            and identity.get('admission_receipt_sha256')==admission['content_sha256']
            and receipt.get('execution_security',{}).get('admission_receipt_sha256')==admission['content_sha256'],
            'receipt-positive-original-admission-binding')
    require(all(admission.get(k)==review['verified_model_admission'][k] for k in
                ('plan_sha256','decision_sha256','trusted_journal_head')),
            'receipt-positive-genuine-proof-binding')
    verdict=receipt.get('factory_build_receipt',{})
    matches=[(index,row) for index,row in enumerate(events) if row['kind']=='factory_build_receipt_computed']
    require(len(matches)==1 and matches[0][1]['payload']==verdict
            and verdict.get('schema')=='factory-build-receipt/1'
            and verdict.get('status')=='passed' and verdict.get('qualifies_for_factory_receipt') is True
            and verdict.get('reasons')==[] and verdict.get('run_id')==expected_id
            and verdict.get('content_sha256')==canonical_hash(verdict,{'content_sha256'}),
            'receipt-positive-original-full-verdict-required')
    index,event=matches[0]
    require(verdict.get('ledger_event_count')==index-1
            and verdict.get('ledger_prefix_sha256')==events[index-2]['event_sha256']
            and verdict.get('execution_security_sha256')==receipt['execution_security']['content_sha256']
            and verdict.get('accounting_sha256')==canonical_hash(receipt['intelligence'])
            and verdict.get('candidate_package_sha256')==receipt['candidate_package_finalization']['content_sha256'],
            'receipt-positive-verdict-ledger-package-binding')
    after=_prepare(args)
    require(after['review']==review,'receipt-positive-proof-or-input-changed')
    require(all(_bounded_regular_bytes(run/name,limit,'receipt-positive-stable')==raw[name]
                for name,limit in sizes.items()),'receipt-positive-original-bytes-changed')
    # No new receipt/schema or qualification flags. Emit the unchanged original.
    print(json.dumps(receipt,sort_keys=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
