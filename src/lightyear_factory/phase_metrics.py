"""Public monotonic phase metrics; no runtime clock capture or proof of coverage.

A source hash binds bytes, not authenticity. The integrating owner supplies
authenticated execution/attempt/clock identity and the expected phase inventory.
Durations from different clock instances or attempts are never combined.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .contracts import canonical_hash
from .journal_metrics import (
    MAX_EVENTS, MAX_JOURNAL_BYTES, MetricsError, _constant, _digest,
    _identifier, _integer, _object, _require,
)

FIELDS = frozenset({
    "schema", "sequence", "previous_sha256", "event_sha256", "event_id",
    "exact_e", "execution_id", "attempt_identity_sha256", "clock_instance_id",
    "phase", "boundary", "monotonic_ns",
})


@dataclass(frozen=True)
class PhaseBinding:
    exact_e: str
    execution_id: str
    attempt_identity_sha256: str
    clock_instance_id: str
    source_sha256: str
    phases: tuple

    def validate(self):
        _require(type(self.exact_e) is str and
                 re.fullmatch("[0-9a-f]{40}", self.exact_e) is not None,
                 "phase-metrics-source")
        _require(_identifier(self.execution_id) and _identifier(self.clock_instance_id),
                 "phase-metrics-owner")
        _require(_digest(self.attempt_identity_sha256) and _digest(self.source_sha256),
                 "phase-metrics-digest")
        _require(type(self.phases) is tuple and 0 < len(self.phases) <= 100 and
                 all(_identifier(p) for p in self.phases) and
                 len(set(self.phases)) == len(self.phases), "phase-metrics-inventory")


def collect_phase_metrics(raw, binding):
    """Project exact start/end pairs; partial intervals remain unknown.

    Same-phase intervals must not overlap. Different phases may overlap, so no
    summed cross-phase wall duration is emitted. Repeated intervals accumulate
    only within the same phase and retained original clock instance.
    """
    _require(type(binding) is PhaseBinding, "phase-metrics-binding")
    binding.validate()
    _require(type(raw) is bytes and len(raw) <= MAX_JOURNAL_BYTES and
             sha256(raw).hexdigest() == binding.source_sha256, "phase-metrics-byte-drift")
    _require(not raw or raw.endswith(b"\n"), "phase-metrics-truncated")
    lines = raw.splitlines()
    _require(len(lines) <= MAX_EVENTS and all(lines), "phase-metrics-event-count")
    previous = None
    prior_ns = None
    seen = set()
    active = {}
    completed = {p: [] for p in binding.phases}
    for sequence, line in enumerate(lines, 1):
        try:
            event = json.loads(line, object_pairs_hook=_object, parse_constant=_constant)
        except (UnicodeError, json.JSONDecodeError):
            raise MetricsError("phase-metrics-json") from None
        _require(type(event) is dict and set(event) == FIELDS, "phase-metrics-fields")
        _require(event["schema"] == "factory-monotonic-phase/1" and
                 type(event["sequence"]) is int and event["sequence"] == sequence and
                 event["previous_sha256"] == previous, "phase-metrics-chain")
        _require(_digest(event["event_sha256"]) and
                 canonical_hash(event, {"event_sha256"}) == event["event_sha256"],
                 "phase-metrics-event-digest")
        _require(event["exact_e"] == binding.exact_e and
                 event["execution_id"] == binding.execution_id and
                 event["attempt_identity_sha256"] == binding.attempt_identity_sha256 and
                 event["clock_instance_id"] == binding.clock_instance_id,
                 "phase-metrics-cross-owner")
        identity = event["event_id"]
        phase = event["phase"]
        _require(_identifier(identity) and identity not in seen, "phase-metrics-event-id")
        _require(type(phase) is str and phase in completed, "phase-metrics-unknown-phase")
        tick = _integer(event["monotonic_ns"])
        _require(tick <= 2**63 - 1 and (prior_ns is None or tick >= prior_ns),
                 "phase-metrics-clock-regression")
        boundary = event["boundary"]
        if boundary == "start":
            _require(phase not in active, "phase-metrics-duplicate-start")
            active[phase] = (tick, identity)
        elif boundary == "end":
            _require(phase in active, "phase-metrics-orphan-end")
            start, start_id = active.pop(phase)
            completed[phase].append(dict(start_event_id=start_id, end_event_id=identity,
                                         elapsed_ns=tick-start))
        else:
            raise MetricsError("phase-metrics-boundary")
        seen.add(identity)
        previous = event["event_sha256"]
        prior_ns = tick
    rows = []
    for phase in binding.phases:
        intervals = completed[phase]
        rows.append(dict(
            phase=phase, intervals=intervals,
            observed_completed_ns=sum(row["elapsed_ns"] for row in intervals),
            open_interval=phase in active, observed_interval_count=len(intervals),
            total_phase_ns=None, complete_coverage=False,
            missing_reason=("open-interval" if phase in active else
                            "no-observations" if not intervals else "coverage-not-established")))
    result = dict(
        schema="factory-monotonic-phase-metrics/1", exact_e=binding.exact_e,
        execution_id=binding.execution_id, attempt_identity_sha256=binding.attempt_identity_sha256,
        clock_instance_id=binding.clock_instance_id, source_sha256=binding.source_sha256,
        journal_head_sha256=previous, observed_events=len(seen), phases=rows,
        total_elapsed_ns=None, cross_phase_sum_permitted=False, complete_coverage=False,
        receipt_authentication_established=False, production_qualification=False)
    result["content_sha256"] = canonical_hash(result)
    return result
