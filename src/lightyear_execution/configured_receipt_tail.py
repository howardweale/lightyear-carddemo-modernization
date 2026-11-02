"""Exact native full-build receipt snapshot/tail relationships, not authority.

The public scripted receipt snapshots before three scans. Native candidate
finalization advances the full-build snapshot to factory_build_receipt_computed,
after the earlier before-memory scan; only two final scans follow. Keep those
protocols separate. Original producers, public verifier and schemas are unchanged.
"""
import json
from hashlib import sha256
from lightyear_factory.contracts import ContractError,canonical_hash

def _require(ok,reason):
    if not ok:raise ContractError('configured-receipt-tail-'+reason)

def _scan(event,name,value):
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')
    _require(type(event) is dict and event.get('kind')=='model_isolation_scan_passed'
        and type(event.get('payload')) is dict and event['payload'].get('status')=='passed'
        and event['payload'].get('scanned')==[dict(artifact=name,sha256=sha256(raw).hexdigest())],
        'scan-binding')

def verify_configured_receipt_tail(receipt,summary,events):
    """Return the original snapshot count. No admission, outcome or strict pass."""
    _require(type(receipt) is dict,'receipt')
    if 'factory_build_receipt' not in receipt:
        # Preserve the original early-refusal/public receipt behavior exactly.
        from .public_drill_runtime import verify_receipt_tail
        return verify_receipt_tail(receipt,summary,events)
    _require(type(summary) is dict and type(events) is list and bool(events)
        and all(type(e) is dict for e in events),'records')
    _require(receipt.get('content_sha256')==canonical_hash(receipt,{'content_sha256'})
        and summary.get('receipt_sha256')==receipt['content_sha256']
        and summary.get('status')==receipt.get('status'),'receipt-digest')
    build=receipt['factory_build_receipt']
    _require(type(build) is dict and build.get('schema')=='factory-build-receipt/1'
        and build.get('content_sha256')==canonical_hash(build,{'content_sha256'})
        and type(build.get('qualifies_for_factory_receipt')) is bool
        and build.get('status')==('passed' if build['qualifies_for_factory_receipt'] else 'blocked')
        and receipt.get('status')==build['status']
        and type(receipt.get('run_id')) is str and bool(receipt['run_id'])
        and build.get('run_id')==receipt['run_id']
        and build.get('work_order_sha256')==receipt.get('work_order_sha256'),'build-binding')
    heads=[i for i,e in enumerate(events) if e.get('event_sha256')==receipt.get('ledger_head_sha256')]
    _require(len(heads)==1,'snapshot')
    index=heads[0]
    _require(type(receipt.get('event_count')) is int and receipt['event_count']==index+1,
        'snapshot-count')
    computed=events[index]
    _require(computed.get('state')=='VERIFYING' and computed.get('kind')=='factory_build_receipt_computed'
        and type(computed.get('payload')) is dict
        and canonical_hash(computed['payload'])==canonical_hash(build)
        and sum(e.get('kind')=='factory_build_receipt_computed' for e in events)==1,'computed-binding')
    # compute_build_receipt pins the prior prefix. The native scanner adds one
    # scan, then the controller appends this computed build event.
    count=build.get('ledger_event_count')
    _require(type(count) is int and count>0 and index==count+1
        and events[count-1].get('event_sha256')==build.get('ledger_prefix_sha256'),'build-prefix')
    _scan(events[count],'factory-build-receipt',build)
    tail=events[index+1:]
    _require(len(tail)==2,'exact-two-final-scans')
    _scan(tail[0],'run-receipt',receipt)
    _scan(tail[1],'run-summary',summary)
    return index+1
