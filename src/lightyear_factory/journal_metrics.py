"""Read-only metrics over public attempt journals; never an admission verifier.

Digests bind exact input bytes, not authenticity. The caller must authenticate
the inventory and original receipts independently. This module cannot authorize
a run, settle billing, resume an attempt or supply P5 qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re

from .contracts import canonical_hash


MAX_JOURNAL_BYTES = 16 * 1024 * 1024
MAX_EVENTS = 20000


class MetricsError(ValueError):
    """Malformed or conflicting evidence must not become a plausible report."""


def _require(condition, reason):
    if not condition:
        raise MetricsError(reason)


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) is not None


def _integer(value):
    _require(type(value) is int and value >= 0, "metrics-nonnegative-integer")
    return value


def _money(value):
    _require(type(value) in (str, int, float), "metrics-money-type")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise MetricsError("metrics-money-value") from None
    _require(number.is_finite() and number >= 0, "metrics-money-range")
    return number


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "metrics-duplicate-json-key")
        result[key] = value
    return result


def _constant(_value):
    raise MetricsError("metrics-nonfinite-json")


@dataclass(frozen=True)
class JournalBinding:
    case_id: str
    exact_e: str
    execution_id: str
    workflow_run_id: int
    workflow_run_attempt: int
    attempt_identity_sha256: str
    source_sha256: str
    journal_head_sha256: str

    def validate(self):
        _require(_identifier(self.case_id) and _identifier(self.execution_id),
                 "metrics-identity")
        _require(isinstance(self.exact_e, str) and
                 re.fullmatch(r"[0-9a-f]{40}", self.exact_e) is not None,
                 "metrics-exact-source")
        _require(all(_digest(value) for value in (
            self.attempt_identity_sha256, self.source_sha256,
            self.journal_head_sha256)), "metrics-digest")
        _require(_integer(self.workflow_run_id) > 0 and
                 _integer(self.workflow_run_attempt) > 0, "metrics-workflow")


def _journal(raw, binding):
    binding.validate()
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_JOURNAL_BYTES,
             "metrics-journal-size")
    _require(sha256(raw).hexdigest() == binding.source_sha256,
             "metrics-source-drift")
    _require(raw.endswith(b"\n"), "metrics-truncated-journal")
    lines = raw.splitlines()
    _require(len(lines) <= MAX_EVENTS and all(lines), "metrics-event-count")
    events = []
    previous = None
    for sequence, line in enumerate(lines, 1):
        try:
            event = json.loads(line, object_pairs_hook=_object,
                               parse_constant=_constant)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise MetricsError("metrics-invalid-json") from None
        _require(isinstance(event, dict) and
                 type(event.get("sequence")) is int and
                 event["sequence"] == sequence and
                 event.get("previous_sha256") == previous,
                 "metrics-chain-sequence")
        _require(_digest(event.get("event_sha256")) and
                 canonical_hash(event, {"event_sha256"}) == event["event_sha256"],
                 "metrics-chain-hash")
        payload = event.get("payload")
        _require(isinstance(payload, dict) and
                 payload.get("attempt_identity_sha256") == binding.attempt_identity_sha256,
                 "metrics-attempt-drift")
        _require(isinstance(event.get("kind"), str), "metrics-event-kind")
        previous = event["event_sha256"]
        events.append(event)
    _require(previous == binding.journal_head_sha256, "metrics-head-drift")
    header = events[0]
    _require(header["kind"] == "model_reservations" and
             type(header["payload"].get("protocol")) is int and
             header["payload"]["protocol"] in (4, 5), "metrics-journal-protocol")
    return events


def _sum_observed(values, money=False):
    known = [value for value in values if value is not None]
    subtotal = sum(known, Decimal(0) if money else 0)
    return dict(observed_subtotal=str(subtotal) if money else subtotal,
                missing_observations=len(values) - len(known),
                complete_for_observed_reservations=len(known) == len(values))


def collect_journal(raw: bytes, binding: JournalBinding):
    """Project hash-bound public fields, without executing or repairing a ledger.

    A reservation is before transport entry. It is NOT evidence of a physical
    send; a missing observer leaves both send completion and usage unknown.
    """
    events = _journal(raw, binding)
    physical, counts, logical = {}, {}, {}
    count_previous = None
    count_sequence = 0
    checkpoint = None
    for event in events[1:]:
        kind, payload = event["kind"], event["payload"]
        if kind == "reserved":
            row = payload.get("reservation")
            _require(isinstance(row, dict), "metrics-logical-shape")
            sequence = _integer(row.get("call_sequence"))
            _require(sequence == len(logical) + 1, "metrics-logical-sequence")
            logical[sequence] = _money(row.get("estimated_cost_usd"))
        elif kind == "sanitized_accounting":
            row = payload.get("accounting")
            _require(isinstance(row, dict), "metrics-accounting-shape")
            calls = _integer(row.get("calls"))
            _require(calls <= len(logical) and
                     (checkpoint is None or calls >= checkpoint["calls"]),
                     "metrics-checkpoint-sequence")
            checkpoint = dict(calls=calls, cost=_money(row.get("estimated_cost_usd")))
        elif kind == "model_transport_reserved":
            row = payload.get("reservation")
            _require(isinstance(row, dict), "metrics-transport-shape")
            sequence = _integer(payload.get("transport_sequence"))
            _require(sequence == len(physical) + 1, "metrics-transport-sequence")
            transport = row.get("transport_kind")
            _require(transport in ("input-token-count", "responses", "anthropic-messages",
                                   "gemini-generate-content"), "metrics-transport-kind")
            _require(_digest(row.get("request_sha256")), "metrics-request-digest")
            physical[event["event_sha256"]] = dict(
                sequence=sequence, request=row["request_sha256"], kind=transport,
                observation=None)
        elif kind == "model_transport_observed":
            ticket, observation = payload.get("reservation_ticket"), payload.get("observation")
            _require(isinstance(ticket, dict) and isinstance(observation, dict),
                     "metrics-observation-shape")
            reserved = physical.get(ticket.get("reservation_event_sha256"))
            _require(reserved is not None and reserved["observation"] is None and
                     ticket == dict(attempt_identity_sha256=binding.attempt_identity_sha256,
                                    transport_sequence=reserved["sequence"],
                                    request_sha256=reserved["request"],
                                    reservation_event_sha256=ticket["reservation_event_sha256"]),
                     "metrics-observation-ticket")
            reserved["observation"] = observation
        elif kind == "count_financial":
            row = payload.get("event")
            _require(isinstance(row, dict), "metrics-count-shape")
            count_sequence += 1
            _require(row.get("attempt_identity_sha256") == binding.attempt_identity_sha256 and
                     type(row.get("event_sequence")) is int and
                     row["event_sequence"] == count_sequence and
                     row.get("previous_count_event_sha256") == count_previous and
                     canonical_hash(row, {"content_sha256"}) == row.get("content_sha256"),
                     "metrics-count-chain")
            count_previous = row["content_sha256"]
            if row.get("kind") == "count_charge_reserved":
                sequence = _integer(row.get("count_sequence"))
                _require(sequence == len(counts) + 1 and _digest(row.get("request_sha256")),
                         "metrics-count-sequence")
                counts[sequence] = dict(
                    ticket=dict(count_sequence=sequence, request_sha256=row["request_sha256"],
                                reservation_event_sha256=row["content_sha256"]),
                    cost=_money(row.get("reserved_cost_usd")), settled=False,
                    unknown=True)
            elif row.get("kind") == "count_charge_observed":
                ticket = row.get("ticket")
                _require(isinstance(ticket, dict) and type(ticket.get("count_sequence")) is int,
                         "metrics-count-ticket")
                reserved = counts.get(ticket["count_sequence"])
                _require(reserved is not None and not reserved["settled"] and
                         ticket == reserved["ticket"], "metrics-count-reused-ticket")
                charge = _money(row.get("conservative_charge_usd"))
                count = row.get("counted_input_tokens")
                if count is None:
                    _require(charge == reserved["cost"], "metrics-unknown-count-release")
                else:
                    _integer(count)
                _require(row.get("billing_final") is False, "metrics-count-final-billing")
                reserved.update(cost=charge, settled=True, unknown=count is None)
            else:
                raise MetricsError("metrics-count-kind")
        else:
            raise MetricsError("metrics-unsupported-event")
    generation = [row for row in physical.values() if row["kind"] != "input-token-count"]
    counting = [row for row in physical.values() if row["kind"] == "input-token-count"]
    tokens = {}
    for field in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens"):
        values = []
        for row in generation:
            usage = (row["observation"] or {}).get("response_usage")
            value = usage.get(field) if isinstance(usage, dict) else None
            values.append(None if value is None else _integer(value))
        tokens[field] = _sum_observed(values)
    estimates = []
    for row in generation:
        observation = row["observation"] or {}
        value = observation.get("estimated_cost_usd")
        estimates.append(_money(value) if observation.get("cost_estimate_available") is True
                         and value is not None else None)
    preflight = [(row["observation"] or {}).get("input_token_count") for row in counting]
    pending_logical = sum((cost for sequence, cost in logical.items()
                           if checkpoint is None or sequence > checkpoint["calls"]), Decimal(0))
    count_exposure = sum((row["cost"] for row in counts.values()), Decimal(0))
    held_count = sum((row["cost"] for row in counts.values() if row["unknown"]), Decimal(0))
    result = dict(
        schema="factory-journal-metrics/1", case_id=binding.case_id,
        exact_e=binding.exact_e, execution_id=binding.execution_id,
        workflow_run_id=binding.workflow_run_id,
        workflow_run_attempt=binding.workflow_run_attempt,
        attempt_identity_sha256=binding.attempt_identity_sha256,
        source_sha256=binding.source_sha256, journal_head_sha256=binding.journal_head_sha256,
        observed_logical_reservations=len(logical),
        observed_generation_transport_reservations=len(generation),
        observed_count_transport_reservations=len(counting),
        observed_transport_results=sum(row["observation"] is not None for row in physical.values()),
        unresolved_transport_reservations=sum(row["observation"] is None for row in physical.values()),
        physical_sends=None, physical_sends_reason="reservation-before-opener-is-not-send-proof",
        tokens=tokens,
        count_endpoint_estimate=_sum_observed(
            [None if value is None else _integer(value) for value in preflight]),
        usd=dict(
            generation_transport_estimates=_sum_observed(estimates, money=True),
            logical_checkpoint_conservative=None if checkpoint is None else str(checkpoint["cost"]),
            pending_logical_reservation=str(pending_logical),
            count_conservative_exposure=str(count_exposure) if events[0]["payload"]["protocol"] == 5 else None,
            unknown_count_hold=str(held_count) if events[0]["payload"]["protocol"] == 5 else None,
            combined_total=None, total_reason="overlapping-components-not-added",
            provider_reported_actual=None, invoice_actual=None, invoice_final=False),
        elapsed_monotonic_seconds=None,
        elapsed_reason="journal-UTC-timestamps-do-not-prove-monotonic-elapsed",
        human_interventions=None, human_reason="complete-human-event-coverage-not-supplied",
        observability="PARTIAL", production_qualification=False,
        authority="report-only; caller must authenticate inventory and source receipts")
    result["content_sha256"] = canonical_hash(result)
    return result


def collect_cases(case_ids, exact_e, sources):
    """Return every expected case, including absent evidence; deduplicate exports.

    sources is an iterable of (JournalBinding, exact_journal_bytes). Different
    snapshots or bindings for one attempt are rejected rather than double-counted.
    """
    _require(isinstance(case_ids, (list, tuple)) and len(case_ids) == 19 and
             all(_identifier(case) for case in case_ids) and len(set(case_ids)) == 19,
             "metrics-nineteen-case-inventory")
    _require(isinstance(exact_e, str) and re.fullmatch(r"[0-9a-f]{40}", exact_e) is not None,
             "metrics-exact-source")
    seen = {}
    groups = {case: [] for case in case_ids}
    for binding, raw in sources:
        _require(type(binding) is JournalBinding and binding.case_id in groups and
                 binding.exact_e == exact_e, "metrics-inventory-binding")
        report = collect_journal(raw, binding)
        prior = seen.get(binding.attempt_identity_sha256)
        if prior is not None:
            _require(prior == report, "metrics-conflicting-attempt-snapshot")
            continue
        seen[binding.attempt_identity_sha256] = report
        groups[binding.case_id].append(report)
    rows = []
    for case in case_ids:
        attempts = sorted(groups[case], key=lambda row: row["attempt_identity_sha256"])
        rows.append(dict(case_id=case, observability="PARTIAL" if attempts else "UNOBSERVED",
                         missing_reason=None if attempts else "no-bound-journal",
                         attempts=attempts))
    result = dict(schema="factory-nineteen-case-metrics/1", exact_e=exact_e, cases=rows,
                  observed_attempts=len(seen), production_qualification=False,
                  human_interventions=None, invoice_actual_usd=None,
                  limitations=["hash-binding-is-not-authentication", "no-native-proof",
                               "no-human-coverage", "no-monotonic-phase-timing",
                               "no-physical-send-proof", "no-invoice-reconciliation"])
    result["content_sha256"] = canonical_hash(result)
    return result


def write_report(path: Path, report):
    """Create a deterministic report without replacing any retained output."""
    _require(isinstance(report, dict) and report.get("content_sha256") ==
             canonical_hash(report, {"content_sha256"}), "metrics-report-digest")
    raw = (json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    with Path(path).open("xb") as handle:
        handle.write(raw)
    return sha256(raw).hexdigest()
