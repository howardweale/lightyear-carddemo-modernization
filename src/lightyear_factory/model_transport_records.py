"""Opt-in exact transport bytes in the existing run artifacts and RunLedger.

No network, retry, signing, spend approval or candidate generation lives here.
The controller still must enforce isolation and join measured/reserved accounting.
"""
from datetime import datetime, timezone
import time
from .contracts import ContractError
from .model_versions import require_snapshot


class ModelTransportRecorder:
    def __init__(self, store, ledger, *, key, key_id, attempt):
        if type(attempt) is not int or not 1 <= attempt <= 3:
            raise ContractError('transport-record-attempt')
        self.store, self.ledger = store, ledger
        self.key, self.key_id, self.attempt = key, key_id, attempt
        self.pending = None
        self.failed = False

    def begin(self, role, provider, model, raw):
        if self.failed or self.pending is not None:
            raise ContractError('transport-recorder-unavailable')
        if role not in ('planner', 'builder', 'analyst'):
            raise ContractError('transport-record-role')
        require_snapshot(model)
        started = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()
        try:
            request = self.store.write_encrypted('model-request', role, raw,
                                                key=self.key, key_id=self.key_id)
            public = dict(schema='factory-model-transport/1', run_id=self.store.run_id,
                          role=role, attempt=self.attempt, provider=provider,
                          configured_model_version=model, started_at=started,
                          request=request, status='started')
            event = self.ledger.append('RUNNING', 'model-transport-started', public)
        except Exception:
            self.failed = True
            raise ContractError('transport-record-persistence-failed') from None
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
