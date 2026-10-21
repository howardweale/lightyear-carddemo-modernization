"""Opt-in exact transport bytes in the existing run artifacts and RunLedger.

No network, retry, signing, spend approval or candidate generation lives here.
The controller still must enforce isolation and join measured/reserved accounting.
"""
from datetime import datetime, timezone
import time
import json
import re
from .contracts import ContractError, canonical_hash
from .model_versions import require_snapshot


class ModelTransportRecorder:
    def __init__(self, store, ledger, *, key, key_id, attempt, isolation_scan=None,
                 work_order_sha256=None, require_model_admission=False):
        if type(attempt) is not int or not 1 <= attempt <= 3:
            raise ContractError('transport-record-attempt')
        self.store, self.ledger = store, ledger
        self.key, self.key_id, self.attempt = key, key_id, attempt
        if isolation_scan is not None and not callable(isolation_scan):
            raise ContractError('transport-isolation-scanner')
        self.isolation_scan = isolation_scan
        if (type(require_model_admission) is not bool or (require_model_admission and
                (not callable(isolation_scan) or not isinstance(work_order_sha256,str)
                 or not re.fullmatch('[0-9a-f]{64}',work_order_sha256)))):
            raise ContractError('transport-model-admission-binding')
        self.require_model_admission = require_model_admission
        self.work_order_sha256 = work_order_sha256
        self.admitted_call = None
        self.pending = None
        self.failed = False

    def _inspect(self, surface, raw):
        if self.isolation_scan is None or raw is None:
            return
        try:
            self.isolation_scan(surface, raw)
        except Exception:
            self.failed = True
            # Do not expose callback details or permit another transport after refusal.
            raise ContractError('transport-isolation-refused') from None

    def bind_model_admission(self, runtime, approval, role, provider, model):
        """Retain the existing verifier's concrete approval before its transport starts."""
        if not self.require_model_admission:
            raise ContractError('transport-model-admission-not-required')
        try:
            canonical_role = 'analyst' if role=='failure_analyst' else role
            if (self.failed or self.pending is not None or self.admitted_call is not None
                    or canonical_role not in ('planner','builder','analyst')
                    or approval.get('schema')!='factory-model-admission/1'
                    or runtime.get('schema')!='factory-model-admission/1'
                    or approval.get('provider_verified') is not True
                    or runtime.get('provider_verified') is not False
                    or approval.get('role')!=canonical_role
                    or approval.get('provider')!=provider or approval.get('model')!=model
                    or approval.get('work_order_sha256')!=self.work_order_sha256):
                raise ValueError('binding')
            keys=('plan_sha256','decision_sha256','trusted_journal_head','executable_commit','work_order_sha256')
            for name in keys:
                size=40 if name=='executable_commit' else 64
                if (runtime.get(name)!=approval.get(name) or not isinstance(approval.get(name),str)
                        or not re.fullmatch('[0-9a-f]{'+str(size)+'}',approval[name])):
                    raise ValueError('proof')
            if not isinstance(runtime.get('workspace_read_manifest'),dict):
                raise ValueError('runtime')
            payload={'schema':'factory-call-admission/1','run_id':self.store.run_id,
                     'attempt':self.attempt,'role':canonical_role,'requested_role':role,
                     'provider':provider,'model':model,'approval':dict(approval),
                     'runtime_sha256':canonical_hash(runtime)}
            self._inspect('model-call-admission',json.dumps(payload,sort_keys=True).encode('utf-8'))
            event=self.ledger.append('RUNNING','model_call_admitted',payload)
            self.admitted_call=(event['event_sha256'],payload)
        except Exception:
            self.failed=True
            raise ContractError('transport-model-admission-refused') from None

    def begin(self, role, provider, model, raw):
        if self.failed or self.pending is not None:
            raise ContractError('transport-recorder-unavailable')
        requested_role = role
        if role == 'failure_analyst':
            role = 'analyst'
        if role not in ('planner', 'builder', 'analyst'):
            raise ContractError('transport-record-role')
        require_snapshot(model)
        admission = self.admitted_call
        if self.require_model_admission:
            expected={'role':role,'requested_role':requested_role,'provider':provider,
                      'model':model,'attempt':self.attempt,'run_id':self.store.run_id}
            if admission is None or any(admission[1].get(k)!=v for k,v in expected.items()):
                self.failed=True
                raise ContractError('transport-model-admission-required')
            try:
                persisted = type(self.ledger)(self.ledger.path)
                matches=[e for e in persisted.events if e['event_sha256']==admission[0]
                         and e['kind']=='model_call_admitted' and e['payload']==admission[1]]
                if persisted.events!=self.ledger.events or len(matches)!=1:
                    raise ValueError('ledger')
            except Exception:
                self.failed=True
                raise ContractError('transport-model-admission-ledger') from None
        self._inspect(role + '-wire-request', raw)
        started = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()
        try:
            request = self.store.write_encrypted('model-request', role, raw,
                                                key=self.key, key_id=self.key_id)
            public = dict(schema='factory-model-transport/1', run_id=self.store.run_id,
                          role=role, requested_role=requested_role,
                          attempt=self.attempt, provider=provider,
                          configured_model_version=model, started_at=started,
                          request=request, status='started')
            if admission is not None:
                public['admission_event_sha256'] = admission[0]
            event = self.ledger.append('RUNNING', 'model-transport-started', public)
        except Exception:
            self.failed = True
            raise ContractError('transport-record-persistence-failed') from None
        self.admitted_call = None
        self.pending = (event['event_sha256'], public, clock)
        return dict(public, start_event_sha256=event['event_sha256'])

    def finish(self, started, raw, *, status, complete):
        if self.failed or self.pending is None or started['start_event_sha256'] != self.pending[0]:
            raise ContractError('transport-record-not-pending')
        if status not in ('response', 'http-error', 'transport-error') or type(complete) is not bool:
            raise ContractError('transport-record-outcome')
        if raw is None and complete:
            raise ContractError('transport-record-response-absent')
        event_hash, public, clock = self.pending
        self._inspect(public['role'] + '-wire-' + status, raw)
        try:
            response = None if raw is None else self.store.write_encrypted(
                'model-response', public['role'], raw, key=self.key, key_id=self.key_id)
            record = dict(public, start_event_sha256=event_hash, status=status,
                          ended_at=datetime.now(timezone.utc).isoformat(),
                          elapsed_ms=int((time.monotonic()-clock)*1000),
                          response=response, response_complete=complete)
            event = self.ledger.append('RUNNING', 'model-transport-finished', record)
        except Exception:
            self.failed = True
            raise ContractError('transport-record-persistence-failed') from None
        self.pending = None
        return dict(record, end_event_sha256=event['event_sha256'])
