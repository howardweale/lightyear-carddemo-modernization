"""Bounded abort-file relationships only; never admission or crash attestation.

Returns unchanged original file bytes. Canonical hashes prove internal relations,
not authenticity or process death. No provider, context, signature, nonce API,
reconciliation append, resume, strict result or production qualification exists.
Authenticated remote consumption and original supervisor/outcome joins are owed.
"""
from pathlib import Path
import re
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_factory.model_admission import _bounded_regular_bytes
from .configured_receipt_terminal import _original_json,_ledger_bytes

LIMITS={'human-consumption.json':1024*1024,'human-admission.json':1024*1024,'admission-nonces.sha256':1024,
        'attempt-identity.json':65536,'events.jsonl':32*1024*1024,
        'attempt-accounting.jsonl':32*1024*1024}

def _require(ok,reason):
    if not ok:raise ContractError('configured-abort-'+reason)

def _digest(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None

def check_abort_file_relations(raw,*,_case_id='configured-build-control'):
    """Pure structural checks; successful return supplies no authority."""
    _require(type(raw) is dict and set(raw)==set(LIMITS),'file-set')
    _require(all(type(raw[k]) is bytes and 0<len(raw[k])<=v for k,v in LIMITS.items()),'size')
    admission=_original_json(raw['human-admission.json'])
    identity=_original_json(raw['attempt-identity.json'])
    consumption=_original_json(raw['human-consumption.json'])
    from .configured_receipt_case import consumption_tools
    consumption_message_bytes,check_consumption_admission_relations,_=consumption_tools(_case_id)
    from .contracts import ExecutionContractError
    try:
        _require(consumption_message_bytes(consumption)==raw['human-consumption.json'],'consumption-original-message')
        check_consumption_admission_relations(consumption,admission)
    except ExecutionContractError:
        raise ContractError('configured-abort-consumption-binding') from None
    for row in (admission,identity):
        _require(type(row) is dict and row.get('content_sha256')==canonical_hash(row,{'content_sha256'}),'digest')
    _require(admission.get('schema')=='factory-human-drill-context-admission/1'
             and admission.get('status')=='passed' and admission.get('stub_only') is False
             and admission.get('output_qualified') is False and admission.get('resume_allowed') is False,'admission-shape')
    for key in ('nonce_sha256','work_order_sha256','plan_sha256','decision_sha256',
                'trusted_journal_head','consumption_record_sha256'):
        _require(_digest(admission.get(key)),'admission-binding-shape')
    _require(identity.get('schema')=='factory-attempt-identity/1'
        and identity.get('attempt_id')=='drill-'+admission['nonce_sha256'][:32]
        and identity.get('admission_receipt_sha256')==admission['content_sha256']
        and identity.get('consumed_nonce_sha256')==admission['nonce_sha256']
        and identity.get('work_order_sha256')==admission['work_order_sha256']
        and _digest(identity.get('sealed_workspace_sha256'))
        and _digest(identity.get('workspace_inventory_sha256')),'identity-binding')
    # This mirror is necessary but not proof of genuine remote consumption.
    _require(raw['admission-nonces.sha256']==(admission['nonce_sha256']+'\n').encode('ascii'),'nonce-mirror')
    events=_ledger_bytes(raw['events.jsonl'])
    journal=_ledger_bytes(raw['attempt-accounting.jsonl'])
    _require(bool(events) and bool(journal),'empty-ledger')
    _require(not any(e.get('state') in ('PASSED','BLOCKED','INTERRUPTED')
                     or e.get('kind') in ('interrupted_attempt','factory_build_receipt_computed') for e in events),'terminal-attempt')
    joins=(('work_order_accepted','work_order_sha256',identity['work_order_sha256']),
           ('hardened_admission_bound','admission_receipt_sha256',admission['content_sha256']),
           ('workspace_read_manifest','sha256',identity['workspace_inventory_sha256']))
    for kind,key,value in joins:
        rows=[e for e in events if e.get('kind')==kind]
        _require(len(rows)==1 and rows[0].get('payload',{}).get(key)==value,'run-ledger-binding')
    _require(journal[0].get('kind')=='model_reservations'
        and journal[0].get('payload',{}).get('protocol')==5
        and journal[0]['payload'].get('count_bound_profile')=='request-bytes-v1','physical-journal-header')
    _require(all(e.get('payload',{}).get('attempt_identity_sha256')==identity['content_sha256'] for e in journal),'accounting-identity')
    # The existing replay enforces reservation/observation order and unresolved
    # conservative holds. Never manufacture a resolved or passing accounting row.
    from lightyear_factory.orchestrator import _reconcile_accounting_journal
    _reconcile_accounting_journal(journal,identity['content_sha256'])
    return None

def read_abort_candidate_files(runs_root,*,_case_id='configured-build-control'):
    root=Path(runs_root)
    _require(root.is_absolute() and root.is_dir(),'absolute-root')
    _require(not any(p.casefold()=='onedrive' for p in root.parts),'onedrive')
    _require(all(not p.is_symlink() and not getattr(p,'is_junction',lambda:False)()
                 for p in (root,*root.parents)),'redirected-root')
    _require(all(not (p/'.git').exists() for p in (root,*root.parents)),'source-root')
    first=_bounded_regular_bytes(root/'human-admission.json',LIMITS['human-admission.json'],'configured-abort-admission')
    admission=_original_json(first)
    _require(type(admission) is dict and _digest(admission.get('nonce_sha256')),'nonce-shape')
    run=root/('drill-'+admission['nonce_sha256'][:32])
    paths={name:(root if name in ('human-admission.json','human-consumption.json','admission-nonces.sha256') else run)/name for name in LIMITS}
    def no_terminal():
        _require(all(not (run/name).exists() and not (run/name).is_symlink()
                     for name in ('receipt.json','summary.json')),'terminal-files')
    no_terminal()
    raw={name:_bounded_regular_bytes(paths[name],limit,'configured-abort-file') for name,limit in LIMITS.items()}
    _require(raw['human-admission.json']==first,'admission-changed')
    check_abort_file_relations(raw,_case_id=_case_id)
    no_terminal()
    _require(all(_bounded_regular_bytes(paths[k],LIMITS[k],'configured-abort-file')==v for k,v in raw.items()),'changed-during-read')
    # Read stability is not a lease or proof that the process has exited. The
    # future original supervisor must establish death and authenticate retention.
    return raw

def read_abort_candidate_observations(runs_root):
    """Join original stable files to service observations, never qualify an abort.

    This requires a locally retained admission and cannot recover a reservation
    that failed before returning. Supervisor death and authenticated outcome
    provenance remain separate prerequisites. No retry or context is created.
    """
    from .configured_consumption_observation import observe_existing_consumption
    raw=read_abort_candidate_files(runs_root)
    observed=observe_existing_consumption(_original_json(raw['human-consumption.json']),
                                          _original_json(raw['human-admission.json']))
    _require(read_abort_candidate_files(runs_root)==raw,'changed-during-service-read')
    return {'original_files':raw,'service_observations':observed}
