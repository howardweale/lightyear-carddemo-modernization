"""Controller-owned phase capture for one attempt; no admission or send proof.

This optional observer retains incomplete classifications. Local observations
and receipt hashes do not authenticate native cleanup, physical sends or billing.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import time

from .contracts import canonical_hash
from .journal_metrics import MetricsError
from .metrics_execution_joins import ExecutionReference, collect_execution_joins
from .phase_metrics import PhaseBinding, collect_phase_metrics


def require(value, reason):
    if not value:
        raise MetricsError(reason)


@dataclass(frozen=True)
class CaptureIdentity:
    exact_e: str
    campaign_id: str
    case_id: str
    execution_id: str
    order_sha256: str
    attempt_identity_sha256: str
    clock_instance_id: str
    receipt_sha256: str | None = None

    def validate(self):
        PhaseBinding(self.exact_e, self.execution_id, self.attempt_identity_sha256,
                     self.clock_instance_id, "0" * 64, ("build", "verify")).validate()
        ExecutionReference(self.case_id, self.execution_id,
                           self.attempt_identity_sha256, self.receipt_sha256).validate()
        require(type(self.campaign_id) is str and
                re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.campaign_id),
                "capture-campaign")
        require(type(self.order_sha256) is str and
                re.fullmatch(r"[0-9a-f]{64}", self.order_sha256), "capture-order")


class ControllerPhaseCapture:
    def __init__(self, identity, *, clock=time.monotonic_ns):
        require(type(identity) is CaptureIdentity, "capture-identity")
        identity.validate()
        require(callable(clock), "capture-clock")
        self._identity = identity
        self._clock = clock
        self._state = "new"
        self._events = []
        self._candidate = None
        self._transport = None
        self._transport_consumed = False

    @property
    def identity(self):
        return self._identity

    def start(self, run_id, order_sha256, attempt):
        require(self._state == "new", "capture-consumed")
        self._state = "consumed"
        require(run_id == self.identity.execution_id and
                order_sha256 == self.identity.order_sha256 and
                type(attempt) is int and attempt == 1, "capture-cross-attempt")
        self._state = "building"
        self._boundary("build", "start")

    def _boundary(self, phase, boundary):
        tick = self._clock()
        require(type(tick) is int and 0 <= tick <= 2**63 - 1 and
                (not self._events or tick >= self._events[-1]["monotonic_ns"]),
                "capture-clock-regression")
        event = dict(schema="factory-monotonic-phase/1",
                     sequence=len(self._events) + 1,
                     previous_sha256=(self._events[-1]["event_sha256"]
                                      if self._events else None),
                     event_id=f"controller-phase-{len(self._events) + 1}",
                     exact_e=self.identity.exact_e,
                     execution_id=self.identity.execution_id,
                     attempt_identity_sha256=self.identity.attempt_identity_sha256,
                     clock_instance_id=self.identity.clock_instance_id,
                     phase=phase, boundary=boundary, monotonic_ns=tick)
        event["event_sha256"] = canonical_hash(event)
        self._events.append(event)

    def built(self):
        require(self._state == "building", "capture-build-order")
        self._state = "built"
        self._boundary("build", "end")

    def candidate(self, commit):
        require(self._state == "built" and self._candidate is None,
                "capture-candidate-order")
        require(type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit),
                "capture-candidate")
        self._candidate = commit

    def transport(self, events):
        """Project only public digest fields from the controller's ledger slice.

        A model-transport-started event precedes transport. It is NOT evidence
        of a physical send, even if a matching complete response exists.
        """
        require(self._state == "built" and not self._transport_consumed,
                "capture-transport-order")
        self._transport_consumed = True
        rows = [row for row in events if row["kind"] == "model-transport-finished"
                and row["payload"].get("role") == "builder"]
        require(len(rows) <= 1, "capture-ambiguous-transport")
        if not rows:
            return
        event = rows[0]
        payload = event["payload"]
        require(payload.get("run_id") == self.identity.execution_id and
                payload.get("attempt") == 1, "capture-cross-attempt")
        require(payload.get("status") == "response" and
                payload.get("response_complete") is True, "capture-transport-incomplete")
        request = payload.get("request", {})
        values = (event.get("event_sha256"), payload.get("start_event_sha256"),
                  request.get("artifact_sha256"))
        require(all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
                    for value in values), "capture-transport-digest")
        self._transport = dict(response_event_sha256=values[0],
                               request_event_sha256=values[1],
                               request_artifact_sha256=values[2],
                               physical_send_id=None,
                               physical_send_status="unknown",
                               physical_send_missing_reason="authenticated-send-event-absent")

    def verifying(self):
        require(self._state == "built", "capture-verify-order")
        self._state = "verifying"
        self._boundary("verify", "start")

    def verified(self):
        require(self._state == "verifying", "capture-verified-order")
        self._state = "verified"
        self._boundary("verify", "end")

    def project(self, *, human_raw=b"", human_source_sha256=None,
                receipts=(), authenticate_receipt=None):
        require(self._state != "new", "capture-not-started")
        human_source_sha256 = (sha256(b"").hexdigest() if human_source_sha256 is None
                               else human_source_sha256)
        raw = b"".join((json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
                       .encode() for event in self._events)
        identity = self.identity
        phases = collect_phase_metrics(raw, PhaseBinding(
            identity.exact_e, identity.execution_id, identity.attempt_identity_sha256,
            identity.clock_instance_id, sha256(raw).hexdigest(), ("build", "verify")))
        joins = collect_execution_joins(
            human_raw, human_source_sha256=human_source_sha256, exact_e=identity.exact_e,
            campaign_id=identity.campaign_id, case_ids=[identity.case_id],
            executions=(ExecutionReference(identity.case_id, identity.execution_id,
                        identity.attempt_identity_sha256, identity.receipt_sha256),),
            receipts=receipts, authenticate_receipt=authenticate_receipt)
        result = dict(schema="factory-controller-phase-capture/1", state=self._state,
                      exact_e=identity.exact_e, execution_id=identity.execution_id,
                      order_sha256=identity.order_sha256,
                      attempt_identity_sha256=identity.attempt_identity_sha256,
                      candidate_commit=self._candidate, transport=self._transport,
                      candidate_status="observed" if self._candidate else "unknown",
                      transport_status="observed" if self._transport else "unknown",
                      phase_journal=raw.decode(), phases=phases, human_joins=joins,
                      physical_send_proven=False, native_cleanup_proven=False,
                      complete_coverage=False, billing_final=False,
                      production_qualification=False)
        result["content_sha256"] = canonical_hash(result)
        return result
