"""Compute a build verdict from the existing controller's persisted evidence.

This module starts no workers, transports, signing or publication. The caller
must supply the current admission and accounting from its bound runtime.
"""
import base64
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path

from .contracts import ContractError, canonical_hash
from .ledger import RunLedger


def compute_build_receipt(order, ledger, run_receipt, calls, runtime, run_dir):
    try:
        persisted = RunLedger(ledger.path)
        if persisted.events != ledger.events:
            raise ValueError('ledger')
        events = persisted.events
        by_hash = {e['event_sha256']: e for e in events}
        run_id = run_receipt['run_id']
        gaps = set()
        def require(condition, reason):
            if not condition:
                gaps.add(reason)
        def rows(kind):
            return [e for e in events if e['kind']==kind]
        require(run_receipt['work_order_sha256']==order.content_sha256, 'work-order-binding')
        attempts=run_receipt['attempts']
        require(type(attempts) is int and 1<=attempts<=order.max_attempts<=3
                and run_receipt['repair_loops']==max(0,attempts-1)<=2, 'attempt-budget')
        require(run_receipt['status']=='passed' and run_receipt['verification']['status']=='passed'
                and bool(run_receipt['verification']['gates'])
                and all(g['status']=='passed' for g in run_receipt['verification']['gates']), 'acceptance-gates')
        require(any(e['payload'].get('attempt')==attempts for e in rows('acceptance_gates_passed')), 'gate-ledger-binding')
        require(runtime.get('schema')=='factory-model-admission/1'
                and runtime.get('work_order_sha256')==order.content_sha256
                and runtime.get('provider_verified') is False, 'current-model-plan')
        security=run_receipt['execution_security']
        require(security.get('production_ready') is True and security.get('status')=='enforced'
                and security.get('work_order_sha256')==order.content_sha256
                and bool(security.get('gate_execution_sha256'))
                and security.get('secrets_persisted') is False
                and security.get('content_sha256')==canonical_hash(security, {'content_sha256'}), 'enforced-execution')
        package=run_receipt.get('candidate_package_finalization',{})
        require(package.get('schema')=='factory-candidate-package-finalization/1'
                and package.get('run_id')==run_id
                and package.get('content_sha256')==canonical_hash(package, {'content_sha256'})
                and sum(e['payload']==package for e in rows('candidate_package_finalized'))==1, 'final-package-binding')
        audits=[e for e in rows('candidate_authorship_audited')
                if e['payload'].get('content_sha256')==package.get('current_authorship_audit_sha256')]
        require(len(audits)==1 and audits[0]['payload'].get('cryptographically_verified') is True
                and audits[0]['payload'].get('qualifies_for_factory_receipt') is True
                and audits[0]['payload'].get('candidate_commit')==package.get('candidate_commit')
                and audits[0]['payload'].get('final_package_tree_sha256')==package.get('tree_sha256'), 'signed-history')
        scans=rows('model_isolation_scan_passed')
        require(bool(scans) and all(e['payload'].get('status')=='passed'
                and e['payload'].get('expected_window_count',0)>0
                and set(e['payload'].get('canary_classes',[]))=={'expected-state','reference-output','session-answer'}
                for e in scans), 'private-isolation-scans')
        scanned={(r['artifact'],r['sha256']) for e in scans for r in e['payload'].get('scanned',[])}
        labels={r[0] for r in scanned}
        for surface in ('controller-context','initial-workspace','builder-workspace','patched-workspace',
                        'pre-gate-workspace','post-gate-workspace','final-candidate-package'):
            require(any(label==surface or label.startswith(surface+'-') for label in labels), 'scan-'+surface)
        starts=rows('model-transport-started');ends=rows('model-transport-finished');admissions=rows('model_call_admitted')
        require({'planner','builder'}<={e['payload'].get('role') for e in starts}, 'required-model-roles')
        require(bool(starts) and len(starts)==len(ends)==len(calls), 'transport-accounting-count')
        used_starts=set();used_admissions=set();used_ends=set();artifact_hashes=[];total_bytes=0
        for call in calls:
            require(call.get('content_sha256')==canonical_hash(call, {'content_sha256'}), 'call-digest')
            ref=call.get('transport_record',{});end=by_hash.get(ref.get('end_event_sha256'))
            if end is None or end['kind']!='model-transport-finished':
                require(False,'call-transport-binding');continue
            finish=end['payload'];start=by_hash.get(finish.get('start_event_sha256'))
            admission=by_hash.get(finish.get('admission_event_sha256'))
            require(end['event_sha256'] not in used_ends,'transport-reuse');used_ends.add(end['event_sha256'])
            if start is None or admission is None or start['kind']!='model-transport-started' or admission['kind']!='model_call_admitted':
                require(False,'transport-admission-binding');continue
            require(start['event_sha256'] not in used_starts and admission['event_sha256'] not in used_admissions,'admission-reuse')
            used_starts.add(start['event_sha256']);used_admissions.add(admission['event_sha256'])
            require(admission['sequence']<start['sequence']<end['sequence'],'admission-order')
            approved=admission['payload'];proof=approved.get('approval',{})
            require(proof.get('provider_verified') is True
                    and all(proof.get(k)==runtime.get(k) for k in ('plan_sha256','decision_sha256','executable_commit','work_order_sha256'))
                    and all(approved.get(k)==finish.get(k)==start['payload'].get(k) for k in ('run_id','attempt','role','provider'))
                    and approved.get('model')==finish.get('configured_model_version')
                    and finish.get('run_id')==run_id
                    and 1<=finish.get('attempt',0)<=attempts, 'concrete-call-approval')
            require(ref==dict(finish,end_event_sha256=end['event_sha256']), 'accounted-transport-record')
            require(call.get('provider')==finish.get('provider') and call.get('model')==finish.get('configured_model_version')
                    and call.get('role')==finish.get('requested_role'), 'accounted-provider-role')
            for key in ('request','response'):
                artifact=finish.get(key)
                if artifact is None:
                    require(key=='response' and finish.get('response_complete') is False,'transport-artifact-absent');continue
                relative=artifact.get('path','')
                if not re.fullmatch(r'artifacts/[0-9]+-model-(?:request|response)\.encrypted\.json',relative):
                    raise ValueError('artifact-path')
                path=Path(run_dir)/relative
                if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (path,*path.parents)):
                    raise ValueError('artifact-link')
                info=path.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>12*1024*1024:
                    raise ValueError('artifact-limit')
                with path.open('rb') as handle:
                    raw=handle.read(12*1024*1024+1)
                    opened=os.fstat(handle.fileno())
                after=path.stat()
                identity=lambda v:(v.st_dev,v.st_ino,v.st_size,v.st_mtime_ns,v.st_nlink,v.st_mode)
                if identity(info)!=identity(opened) or identity(info)!=identity(after) or path.is_symlink():
                    raise ValueError('artifact-replaced')
                total_bytes+=len(raw)
                if total_bytes>128*1024*1024 or len(raw)!=info.st_size:
                    raise ValueError('artifact-total')
                require(hashlib.sha256(raw).hexdigest()==artifact.get('artifact_sha256'),'encrypted-artifact-digest')
                envelope=json.loads(raw);context=envelope['context']
                require(all(artifact.get(k)==v for k,v in context.items()) and context.get('run_id')==run_id
                        and context.get('role')==finish.get('role'), 'encrypted-artifact-context')
                require(hashlib.sha256(base64.b64decode(envelope['ciphertext_base64'],validate=True)).hexdigest()==artifact.get('ciphertext_sha256'), 'ciphertext-digest')
                surface=finish['role']+'-wire-'+('request' if key=='request' else finish['status'])
                require((surface,artifact.get('plaintext_sha256')) in scanned,'wire-byte-scan')
                artifact_hashes.append(artifact['artifact_sha256'])
        require(used_ends=={e['event_sha256'] for e in ends} and used_starts=={e['event_sha256'] for e in starts}
                and used_admissions=={e['event_sha256'] for e in admissions},'unaccounted-transports')
        intelligence=run_receipt['intelligence']
        require(len(calls)==intelligence.get('calls') and 0<len(calls)<=order.max_model_calls,'model-call-budget')
        require(intelligence.get('call_evidence_sha256')==[c.get('content_sha256') for c in calls], 'accounting-digests')
        require(intelligence.get('cost_estimate_available') is True,'cost-accounting')
        for name,cap in [('input_bytes',order.max_model_input_bytes),('output_bytes',order.max_model_output_bytes),
                         ('estimated_cost_usd',order.max_model_cost_usd),('elapsed_ms',order.max_elapsed_seconds*1000)]:
            value=intelligence.get(name)
            require(type(value) in (int,float) and math.isfinite(value) and 0<=value<=cap,'budget-'+name)
        for name in ('input_tokens','output_tokens'):
            value=intelligence.get(name)
            require(type(value) is int and value>=0 and all(type(c.get(name)) is int and c[name]>=0 for c in calls)
                    and value==sum(c[name] for c in calls), 'accounted-'+name)
        require(0<=intelligence.get('input_tokens',-1)+intelligence.get('output_tokens',-1)<=order.max_model_tokens,'token-budget')
        require(all(type(c.get('estimated_cost_usd')) in (int,float) and math.isfinite(c['estimated_cost_usd'])
                    and c['estimated_cost_usd']>=0 for c in calls)
                and abs(sum(c['estimated_cost_usd'] for c in calls)-intelligence['estimated_cost_usd'])<=0.0000001,'accounted-cost')
        result={'schema':'factory-build-receipt/1','run_id':run_id,'work_order_sha256':order.content_sha256,
                'status':'passed' if not gaps else 'blocked','qualifies_for_factory_receipt':not gaps,
                'attempts':attempts,'repair_loops':max(0,attempts-1),'reasons':sorted(gaps),
                'ledger_prefix_sha256':persisted.head_sha256,'ledger_event_count':len(events),
                'current_admission_sha256':canonical_hash(runtime),'execution_security_sha256':security.get('content_sha256'),
                'accounting_sha256':canonical_hash(intelligence),'candidate_package_sha256':package.get('content_sha256'),
                'admission_events':[e['event_sha256'] for e in admissions],
                'transport_events':[e['event_sha256'] for e in ends],
                'isolation_scan_events':[e['event_sha256'] for e in scans],
                'encrypted_artifact_sha256':artifact_hashes}
        result['content_sha256']=canonical_hash(result)
        return result
    except Exception:
        raise ContractError('factory-build-receipt-refused') from None
