"""Original pre-call clean context observation; no standalone admission authority.

The production caller is the native controller immediately after its original
context scan. Component predicates accept untrusted data and confer no trust.
Only fixed digests remain in the existing same-process origin registry.
"""
from hashlib import sha256
import json,sys
from pathlib import Path
from lightyear_factory.contracts import ContractError,WorkOrder
from lightyear_factory.model_admission import _bounded_regular_bytes
from .configured_receipt_answer_inputs import WORKER,WORKER_SHA256
from .configured_receipt_answer_stimulus import _clean_boundary


def _require(value,reason):
    if not value:raise ContractError('configured-clean-control-'+reason)


def _describe_clean_context(value,original,order,events):
    """Pure byte/ledger relationships; never a passed admission or scan."""
    _require(type(order) is WorkOrder and order.order_id=='configured-build-control','control-order')
    _require(type(original) is bytes and sha256(original).hexdigest()==WORKER_SHA256,'original-worker')
    _require(type(value) is dict and value.get('schema_version')=='1.0'
        and value.get('graph_content_sha256') is None and value.get('evidence_pack_sha256') is None
        and value.get('semantic_memory') is None and value.get('truncated') is False,'context-shape')
    rows=value.get('allowed_files');_require(type(rows) is list and len(rows)==1,'context-files')
    row=rows[0]
    _require(type(row) is dict and row.get('path')==WORKER and row.get('sha256')==WORKER_SHA256
        and type(row.get('bytes')) is int and row['bytes']==len(original)
        and row.get('content')==original.decode('utf-8') and row.get('truncated') is False,'context-worker')
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')
    _require(type(events) is list and len(events)>1,'events')
    _clean_boundary(events[:-1],order,original)
    last=events[-1];payload=last.get('payload',{})
    _require(last.get('kind')=='model_isolation_scan_passed' and payload.get('status')=='passed'
        and payload.get('scanned')==[dict(artifact='controller-context',sha256=sha256(raw).hexdigest())]
        and payload.get('normalization')=='casefold-whitespace-base64-hex-url/1'
        and type(payload.get('expected_window_count')) is int and payload['expected_window_count']>0,'original-scan-row')
    return sha256(raw).hexdigest(),len(raw),WORKER_SHA256,order.content_sha256


def record_original_clean_context(controller,order,workspace_root,value):
    from lightyear_factory.orchestrator import FactoryOrchestrator,_reconcile_accounting_journal
    from .configured_receipt_terminal import _require_origin,_ledger_bytes
    saved=_require_origin(controller)
    caller=sys._getframe(1);parent=caller.f_back
    try:
        _require(caller.f_code is FactoryOrchestrator._context.__code__
            and caller.f_locals.get('self') is controller and caller.f_locals.get('order') is order
            and caller.f_locals.get('workspace_root') is workspace_root and caller.f_locals.get('context') is value
            and parent is not None and parent.f_code is FactoryOrchestrator._run.__code__
            and parent.f_locals.get('self') is controller and parent.f_locals.get('order') is order,'original-boundary')
        _require('clean_context' not in saved,'repeat-refused')
        saved['clean_context']=None
        workspace=saved['workspace']();ledger=saved['ledger']();journal=saved['journal']()
        _require(saved['order']() is order and parent.f_locals.get('workspace') is workspace
            and workspace.root==Path(workspace_root).resolve(),'original-workspace')
        original=_bounded_regular_bytes(Path(controller.source_root)/WORKER,20000,'configured-clean-source')
        _require(_bounded_regular_bytes(workspace.root/WORKER,20000,'configured-clean-copy')==original,'original-copy')
        events=_ledger_bytes(_bounded_regular_bytes(ledger.path,32*1024*1024,'configured-clean-ledger'))
        _require(events==ledger.events,'original-ledger')
        descriptor=_describe_clean_context(value,original,order,events)
        accounting=_ledger_bytes(_bounded_regular_bytes(journal.path,32*1024*1024,'configured-clean-accounting'))
        _require(accounting==journal.events and accounting[0]['payload'].get('protocol')==5
            and all(r['kind'] in ('model_reservations','sanitized_accounting') for r in accounting),'pre-call-journal')
        replay=_reconcile_accounting_journal(accounting,saved['identity_sha256'])
        _require(replay.get('calls')==0 and not saved['budget']().calls
            and saved['provider']()._transport_started is False
            and controller._receipt_pending is False and not controller._receipt_transports,'pre-call-state')
        _require_origin(controller)
        _require(_ledger_bytes(_bounded_regular_bytes(ledger.path,32*1024*1024,'configured-clean-ledger'))==events
            and _ledger_bytes(_bounded_regular_bytes(journal.path,32*1024*1024,'configured-clean-accounting'))==accounting
            and _bounded_regular_bytes(workspace.root/WORKER,20000,'configured-clean-copy')==original,'changed-observation')
        saved['clean_context']=(descriptor,events[-1]['event_sha256'],controller.execution_context.admission_receipt['content_sha256'])
    finally:
        del caller,parent


def require_original_clean_context(controller,events):
    from .configured_receipt_terminal import _require_origin
    saved=_require_origin(controller);observed=saved.get('clean_context')
    _require(type(observed) is tuple and len(observed)==3,'observation-required')
    descriptor,event_digest,admission_digest=observed
    _require(type(descriptor) is tuple and len(descriptor)==4
        and descriptor[2]==WORKER_SHA256 and descriptor[3]==saved['order']().content_sha256
        and admission_digest==controller.execution_context.admission_receipt['content_sha256'],'observation-binding')
    matches=[r for r in events if r.get('event_sha256')==event_digest]
    _require(len(matches)==1 and matches[0].get('kind')=='model_isolation_scan_passed'
        and matches[0].get('payload',{}).get('scanned')==[dict(artifact='controller-context',sha256=descriptor[0])],'retained-original-scan')
    # No receipt, status or authority is returned. Original full success checks
    # remain responsible for later calls, accounting and terminal evidence.
