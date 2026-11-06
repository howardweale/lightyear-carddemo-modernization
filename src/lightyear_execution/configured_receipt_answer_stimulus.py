"""Fixed copied-public-worker stimulus at the original assembler boundary.

No caller bytes/callback, new receipt schema, outcome or execution authority.
Only a genuinely live original answer controller may mutate its copied worker.
Pure component helpers and diagnostic hashes never establish admission/no-send.
"""
from hashlib import sha256
import json,os,stat,sys
from pathlib import Path
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_factory.model_admission import _bounded_regular_bytes
from .configured_receipt_answer_inputs import WORKER,WORKER_SHA256,validate_answer_workspace_scope

def _require(ok,reason):
    if not ok:raise ContractError('configured-answer-stimulus-'+reason)

def _fragment(values):
    _require(type(values) is tuple and 3<=len(values)<=32
        and all(type(v) is str for v in values),'public-values')
    value=''.join(values[0].casefold().split())[:40]
    _require(len(value)==40 and all(33<=ord(c)<=126 for c in value),'fixed-ascii-window')
    return value

def _stimulus_bytes(original,values):
    _require(type(original) is bytes and sha256(original).hexdigest()==WORKER_SHA256,'original-worker')
    # Fixed normalized fragment, from the first signed public isolation value.
    # Spacing/case alteration exercises native normalization; no executable code.
    fragment=_fragment(values)
    proposed=original+b'\n# configured answer fragment: '+(' '.join(fragment.upper())).encode('ascii')+b'\n'
    _require(len(proposed)<=20000,'file-budget')
    return proposed

def _clean_boundary(events,order,original):
    """Pure relationship predicate; untrusted rows never confer authority."""
    _require(type(events) is list and bool(events),'events')
    def single(kind):
        found=[(i,r['payload']) for i,r in enumerate(events) if r.get('kind')==kind]
        _require(len(found)==1,'boundary-event');return found[0]
    manifest_i,manifest=single('workspace_read_manifest')
    accepted_i,accepted=single('work_order_accepted')
    bound_i,bound=single('candidate_controller_bound')
    isolated_i,isolated=single('workspace_isolated')
    scan_rows=[(i,s) for i,r in enumerate(events) if r.get('kind')=='model_isolation_scan_passed'
        for s in r.get('payload',{}).get('scanned',[]) if s.get('artifact')=='initial-workspace-file']
    order_rows=[(i,s) for i,r in enumerate(events) if r.get('kind')=='model_isolation_scan_passed'
        for s in r.get('payload',{}).get('scanned',[]) if s.get('artifact')=='approved-work-order']
    _require(len(scan_rows)==len(order_rows)==1,'initial-scans')
    scan_i,scan=scan_rows[0];order_i,order_scan=order_rows[0]
    _require(manifest_i<scan_i<order_i<accepted_i<bound_i<isolated_i==len(events)-1,'boundary-order')
    expected={WORKER:WORKER_SHA256}
    _require(sha256(original).hexdigest()==WORKER_SHA256
        and manifest.get('files')==expected and manifest.get('sha256')==canonical_hash(expected)
        and scan.get('sha256')==WORKER_SHA256
        and order_scan.get('sha256')==sha256(json.dumps(order.to_dict(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        and accepted.get('work_order_sha256')==bound.get('order_sha256')==order.content_sha256
        and isolated.get('allowed_paths')==[WORKER]
        and isolated.get('initial_snapshot_sha256')==canonical_hash(expected),'clean-binding')

def _replace_copied_bytes(path,original,proposed):
    """Bounded file operation, not an admission entry; production caller is fixed."""
    _require(type(original) is bytes and sha256(original).hexdigest()==WORKER_SHA256
        and type(proposed) is bytes and len(original)<len(proposed)<=20000
        and proposed.startswith(original),'write-shape')
    _require(_bounded_regular_bytes(path,20000,'configured-answer-stimulus-file')==original,'changed-before-write')
    info=path.stat();identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_nlink)
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink==1,'regular-worker')
    flags=os.O_RDWR|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags)
    with os.fdopen(fd,'r+b') as stream:
        _require(identity(os.fstat(stream.fileno()))==identity(info)
            and stream.read(20001)==original,'replaced-worker')
        _require(identity(path.stat())==identity(info),'replaced-worker')
        stream.seek(0);stream.write(proposed);stream.truncate();stream.flush();os.fsync(stream.fileno())
        final=os.fstat(stream.fileno())
    _require((final.st_dev,final.st_ino)==(info.st_dev,info.st_ino)
        and _bounded_regular_bytes(path,20000,'configured-answer-stimulus-file')==proposed,'write-readback')

def prepare_original_answer_fragment(controller,order,workspace_root):
    from lightyear_factory.orchestrator import FactoryOrchestrator,_reconcile_accounting_journal
    from .configured_receipt_context import ConfiguredReceiptExecutionContext
    from .configured_receipt_case import is_answer_order
    _require(type(controller) is FactoryOrchestrator
        and type(controller.execution_context) is ConfiguredReceiptExecutionContext
        and is_answer_order(order),'original-answer-owner')
    caller=sys._getframe(1);parent=caller.f_back
    try:
        _require(caller.f_code is FactoryOrchestrator._context.__code__
            and caller.f_locals.get('self') is controller and caller.f_locals.get('order') is order
            and caller.f_locals.get('workspace_root') is workspace_root
            and parent is not None and parent.f_code is FactoryOrchestrator._run.__code__
            and parent.f_locals.get('self') is controller and parent.f_locals.get('order') is order,'original-boundary')
        from .configured_receipt_terminal import _require_origin,_ledger_bytes
        from .configured_receipt_controller import verify_configured_controller
        saved=_require_origin(controller);context=controller.execution_context
        workspace=saved['workspace']();ledger=saved['ledger']();journal=saved['journal']()
        _require(saved['order']() is order and context._order is order
            and parent.f_locals.get('workspace') is workspace
            and workspace.root==Path(workspace_root).resolve()
            and not workspace.root.is_relative_to(Path(controller.source_root).resolve()),'workspace-owner')
        _require('answer_stimulus' not in saved,'repeat-refused')
        verify_configured_controller(controller,order)
        validate_answer_workspace_scope(order,context._manifest)
        source=Path(controller.source_root)/WORKER;target=workspace.root/WORKER
        original=_bounded_regular_bytes(source,20000,'configured-answer-source')
        _require(_bounded_regular_bytes(target,20000,'configured-answer-copy')==original,'original-copy')
        _require(_ledger_bytes(_bounded_regular_bytes(ledger.path,32*1024*1024,'configured-answer-ledger'))==ledger.events,'original-ledger')
        _clean_boundary(ledger.events,order,original)
        accounting=_ledger_bytes(_bounded_regular_bytes(journal.path,32*1024*1024,'configured-answer-accounting'))
        _require(accounting==journal.events and accounting[0]['payload'].get('protocol')==5
            and all(r['kind'] in ('model_reservations','sanitized_accounting') for r in accounting),'pre-call-journal')
        replay=_reconcile_accounting_journal(accounting,saved['identity_sha256'])
        _require(replay.get('calls')==0 and not saved['budget']().calls
            and saved['provider']()._transport_started is False
            and controller._receipt_pending is False and not controller._receipt_transports,'pre-call-state')
        values=context.public_expected_values(order)
        proposed=_stimulus_bytes(original,values)
        # Tombstone before writing: partial write/expiry/readback errors never retry.
        saved['answer_stimulus']=None
        verify_configured_controller(controller,order)
        _require(_bounded_regular_bytes(source,20000,'configured-answer-source')==original,'source-changed')
        _replace_copied_bytes(target,original,proposed)
        _require(_bounded_regular_bytes(source,20000,'configured-answer-source')==original,'source-changed')
        saved['answer_stimulus']=(sha256(proposed).hexdigest(),len(proposed),sha256(_fragment(values).encode()).hexdigest())
    finally:
        del caller,parent

def _match_intended_fragment(value,proposed,values,normalized):
    """Pure original-context relationships, not a scanner or outcome verifier."""
    _require(type(value) is dict and value.get('schema_version')=='1.0'
        and value.get('graph_content_sha256') is None and value.get('evidence_pack_sha256') is None
        and value.get('semantic_memory') is None and value.get('truncated') is False,'assembled-shape')
    rows=value.get('allowed_files');_require(type(rows) is list and len(rows)==1,'assembled-files')
    row=rows[0];fragment=_fragment(values)
    _require(type(row) is dict and row.get('path')==WORKER
        and type(row.get('bytes')) is int and row['bytes']==len(proposed)
        and row.get('sha256')==sha256(proposed).hexdigest() and row.get('truncated') is False
        and row.get('content')==proposed.decode('utf-8')
        and type(normalized) is str and fragment in normalized,'intended-fragment')
    return sha256(proposed).hexdigest(),len(proposed),sha256(fragment.encode()).hexdigest()

def describe_original_answer_match(controller,value,normalized):
    from .configured_receipt_terminal import _require_origin
    saved=_require_origin(controller);context=controller.execution_context
    original=_bounded_regular_bytes(Path(controller.source_root)/WORKER,20000,'configured-answer-source')
    proposed=_stimulus_bytes(original,context._binding['values'])
    _require(saved.get('answer_stimulus')==_match_intended_fragment(value,proposed,context._binding['values'],normalized),'missing-stimulus')
    _require(_bounded_regular_bytes(saved['workspace']().root/WORKER,20000,'configured-answer-copy')==proposed,'copy-changed')
    return saved['answer_stimulus']
