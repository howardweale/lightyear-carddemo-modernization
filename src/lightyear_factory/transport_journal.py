"""Attempt-journal hooks at physical transports; budget decisions stay with callers."""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
from .contracts import canonical_hash
from typing import Any, Callable


class TransportJournalError(RuntimeError):
    """Journal failure must stop transport and must not enter provider retry handling."""


@dataclass(frozen=True)
class _Scope:
    reserve: Callable[[dict[str, Any]], Any]
    observe: Callable[[Any, dict[str, Any]], None]
    invocation: dict[str, Any]
    bounds: dict[str, Any]
    counted: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _Reservation:
    scope: _Scope
    ticket: Any
    kind: str
    input_price: float
    output_price: float
    record: dict[str, Any]


_active: ContextVar[_Scope | None] = ContextVar("factory_transport_journal", default=None)
_received: ContextVar[Any] = ContextVar("factory_transport_received", default=None)


def _emit(callback, *args):
    try:
        return callback(*args)
    except Exception as exc:
        # In particular, an fsync TimeoutError must never look like a network timeout.
        raise TransportJournalError("Attempt accounting journal write failed") from exc


@contextmanager
def transport_journal_scope(reserve, observe, *, invocation, bounds):
    """Carry the caller's existing reservation values without recalculating admission."""
    if _active.get() is not None:
        raise TransportJournalError("Nested transport journal scope")
    token = _active.set(_Scope(reserve, observe, deepcopy(invocation), deepcopy(bounds)))
    try:
        yield
    finally:
        _active.reset(token)


def reserve_transport(provider, role, request, kind, attempt):
    scope = _active.get()
    if scope is None:
        return None
    raw = request.data
    if not isinstance(raw, bytes):
        raise TransportJournalError("Transport request must have exact byte data")
    record = dict(
        invocation=deepcopy(scope.invocation), bounds=deepcopy(scope.bounds),
        provider=provider.provider_id, model=provider.model, role=role,
        transport_kind=kind, provider_attempt=attempt,
        request_sha256=sha256(raw).hexdigest(), request_bytes=len(raw),
        canonical_request_sha256=canonical_hash(json.loads(raw)),
        pricing=dict(input_usd_per_million=provider.input_usd_per_million,
                     output_usd_per_million=provider.output_usd_per_million),
    )
    if kind == "input-token-count":
        scope.counted.clear()
    elif kind == "responses":
        record["input_token_preflight"] = None
        if provider.token_preflight:
            counted = scope.counted
            bound = scope.bounds.get("input_tokens")
            body = json.loads(raw)
            try:
                projection = {key: body[key] for key in ("model", "instructions", "input", "text")}
            except (KeyError, TypeError):
                raise TransportJournalError("Generation input cannot be bound to token count") from None
            if (not counted or type(bound) is not int or bound < 0
                    or any(counted[key] != record[key] for key in ("provider", "model", "role"))
                    or canonical_hash(projection) != counted["canonical_request_sha256"]):
                raise TransportJournalError("Generation requires matching durable token count")
            if counted["input_tokens"] > bound:
                raise TransportJournalError("Counted input exceeds reserved input bound")
            record["input_token_preflight"] = dict(
                input_tokens=counted["input_tokens"],
                count_request_sha256=counted["request_sha256"],
                count_projection_sha256=counted["canonical_request_sha256"])
    # The sink appends the identity-bound reservation and fsyncs before returning
    # its ticket. The opener has not been entered if this callback fails.
    ticket = _emit(scope.reserve, record)
    return _Reservation(scope, ticket, kind,
                        provider.input_usd_per_million, provider.output_usd_per_million,
                        deepcopy(record))


def _reported_usage(kind, payload):
    if isinstance(payload, bytes):
        if len(payload) > 8 * 1024 * 1024:
            return None
        try:
            payload = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return None
    if not isinstance(payload, dict):
        return None
    raw = payload.get("usageMetadata" if kind == "gemini-generate-content" else "usage")
    if not isinstance(raw, dict):
        return None
    # Usage mapping matches the existing adapters, before content validation.
    try:
        if kind == "anthropic-messages":
            values = [raw["input_tokens"], raw.get("cache_read_input_tokens", 0),
                      raw.get("cache_creation_input_tokens", 0), raw["output_tokens"]]
            if not all(type(v) is int and v >= 0 for v in values):
                return None
            return dict(input_tokens=sum(values[:3]), cached_input_tokens=values[1], output_tokens=values[3])
        if kind == "gemini-generate-content":
            values = [raw["promptTokenCount"], raw.get("cachedContentTokenCount", 0),
                      raw["candidatesTokenCount"], raw.get("thoughtsTokenCount", 0)]
            if not all(type(v) is int and v >= 0 for v in values):
                return None
            return dict(input_tokens=values[0], cached_input_tokens=values[1], output_tokens=values[2]+values[3])
    except KeyError:
        return None
    return deepcopy(raw)


def _observation(reservation, payload, failure):
    observed = _reported_usage(reservation.kind, payload)
    cost = None
    if reservation.kind != "input-token-count" and observed is not None:
        values = [observed.get("input_tokens"), observed.get("output_tokens")]
        if all(type(value) is int and value >= 0 for value in values):
            if reservation.input_price > 0 and reservation.output_price > 0:
                cost = round((values[0]*reservation.input_price + values[1]*reservation.output_price)/1_000_000, 8)
    result = dict(outcome="failed" if failure is not None else "returned",
                response_usage=observed, estimated_cost_usd=cost,
                cost_estimate_available=cost is not None,
                failure_type=type(failure).__name__ if failure is not None else None)
    if reservation.kind == "input-token-count":
        # Count evidence is not billed usage. Never give the count endpoint a
        # fabricated zero cost, even when it returned a valid count.
        count = payload.get("input_tokens") if isinstance(payload, dict) else None
        result["input_token_count"] = count if type(count) is int and count >= 0 else None
    return result


def report_transport_payload(payload):
    """Capture usage before an admitted response wrapper validates its snapshot."""
    callback = _received.get()
    if callback is not None:
        callback(payload)


@contextmanager
def observe_transport(reservation):
    payload = None
    def received(value):
        nonlocal payload
        payload = value
    if reservation is None:
        yield received
        return
    token = _received.set(received)
    try:
        yield received
    except BaseException as exc:
        _emit(reservation.scope.observe, reservation.ticket,
              _observation(reservation, payload, exc))
        raise
    else:
        observation = _observation(reservation, payload, None)
        _emit(reservation.scope.observe, reservation.ticket, observation)
        if reservation.kind == "input-token-count" and observation["input_token_count"] is not None:
            # Publish the count to the next send only AFTER the durable observer
            # returns. A failed fsync cannot enable a generation transport.
            reservation.scope.counted.update(
                {key: reservation.record[key] for key in
                 ("provider", "model", "role", "request_sha256", "canonical_request_sha256")},
                input_tokens=observation["input_token_count"])
    finally:
        _received.reset(token)
