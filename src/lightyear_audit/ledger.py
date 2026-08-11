from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .contracts import (
    AUDIT_SCHEMA_VERSION,
    AuditContractError,
    EventDraft,
    canonical_hash,
    parse_timestamp,
    reject_secrets,
)


def _event(draft: EventDraft, sequence: int, previous: str | None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "sequence": sequence,
        "previous_sha256": previous,
        **draft.to_dict(),
    }
    identity = canonical_hash(event)
    event["event_id"] = f"audit:event:{identity[:24]}"
    event["event_sha256"] = canonical_hash(event)
    return event


class AppendOnlyAuditLog:
    """JSONL write-ahead log with sequence, integrity, and optimistic-head checks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        events = [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        errors = validate_events(events)
        if errors:
            raise AuditContractError("Audit log is invalid: " + "; ".join(errors))
        return events

    def append(self, draft: EventDraft, expected_head: str | None = None) -> dict[str, Any]:
        events = self.read()
        current_head = events[-1]["event_sha256"] if events else None
        if expected_head is not None and current_head != expected_head:
            raise AuditContractError("Audit log head changed before append")
        event = _event(draft, len(events) + 1, current_head)
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        descriptor = os.open(self.path, flags, 0o600)
        try:
            line = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
            os.write(descriptor, line)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return event


def build_snapshot(
    drafts: Iterable[EventDraft],
    graph_content_sha256: str,
    checkpoint_at: str,
    signing_key: bytes | None = None,
) -> dict[str, Any]:
    parse_timestamp(checkpoint_at)
    events = []
    previous = None
    previous_time = None
    for sequence, draft in enumerate(drafts, start=1):
        occurred = parse_timestamp(draft.occurred_at)
        if previous_time is not None and occurred < previous_time:
            raise AuditContractError("Audit drafts must be ordered by occurred_at")
        event = _event(draft, sequence, previous)
        events.append(event)
        previous = event["event_sha256"]
        previous_time = occurred
    if not events:
        raise AuditContractError("Audit snapshot requires at least one event")
    checkpoint = {
        "checkpoint_version": "1.0",
        "created_at": checkpoint_at,
        "event_count": len(events),
        "ledger_head_sha256": previous,
        "signature_algorithm": "HMAC-SHA256" if signing_key else "none",
        "signature": None,
    }
    if signing_key:
        checkpoint["signature"] = hmac.new(
            signing_key,
            canonical_hash(checkpoint, {"signature"}).encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
    decisions = [
        json.loads(json.dumps(event["details"]["decision"], sort_keys=True))
        for event in events
        if event["action"] == "policy.decision_recorded" and "decision" in event["details"]
    ]
    exceptions = [
        json.loads(json.dumps(event["details"]["exception"], sort_keys=True))
        for event in events
        if event["action"] == "policy.exception_granted" and "exception" in event["details"]
    ]
    payload: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "snapshot_type": "lightyear-audit-ledger",
        "ledger_id": "lightyear:carddemo:audit",
        "graph_content_sha256": graph_content_sha256,
        "events": events,
        "decisions": decisions,
        "exceptions": exceptions,
        "checkpoint": checkpoint,
        "statistics": {
            "event_count": len(events),
            "actors": dict(sorted(Counter(event["actor"]["role"] for event in events).items())),
            "actions": dict(sorted(Counter(event["action"] for event in events).items())),
            "decisions": dict(sorted(Counter(item["status"] for item in decisions).items())),
            "active_exceptions": len(exceptions),
        },
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_events(events: list[dict[str, Any]]) -> list[str]:
    errors = []
    previous = None
    event_ids: set[str] = set()
    previous_time = None
    for expected, event in enumerate(events, start=1):
        try:
            draft = EventDraft.from_dict(event)
            occurred = parse_timestamp(draft.occurred_at)
            if previous_time is not None and occurred < previous_time:
                errors.append(f"event {expected} occurred_at is out of order")
            previous_time = occurred
        except AuditContractError as error:
            errors.append(f"event {expected} contract error: {error}")
        if event.get("sequence") != expected:
            errors.append(f"event {expected} sequence is invalid")
        if event.get("previous_sha256") != previous:
            errors.append(f"event {expected} ledger chain is broken")
        if event.get("event_sha256") != canonical_hash(event, {"event_sha256"}):
            errors.append(f"event {expected} hash is invalid")
        event_id = event.get("event_id")
        expected_id = "audit:event:" + canonical_hash(
            event, {"event_id", "event_sha256"}
        )[:24]
        if event_id != expected_id:
            errors.append(f"event {expected} id is invalid")
        if event_id in event_ids:
            errors.append(f"event {expected} id is duplicated")
        event_ids.add(event_id)
        previous = event.get("event_sha256")
    return errors


def validate_snapshot(
    payload: dict[str, Any],
    graph_content_sha256: str | None = None,
    signing_key: bytes | None = None,
) -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    if payload.get("schema_version") != AUDIT_SCHEMA_VERSION:
        errors.append("unsupported audit schema_version")
    if graph_content_sha256 and payload.get("graph_content_sha256") != graph_content_sha256:
        errors.append("audit snapshot targets a different graph identity")
    try:
        reject_secrets(payload)
    except AuditContractError as error:
        errors.append(str(error))
    events = payload.get("events", [])
    if not isinstance(events, list):
        errors.append("audit events must be an array")
        events = []
    errors.extend(validate_events(events))
    projected_decisions = [
        event["details"]["decision"]
        for event in events
        if event.get("action") == "policy.decision_recorded"
        and isinstance(event.get("details", {}).get("decision"), dict)
    ]
    projected_exceptions = [
        event["details"]["exception"]
        for event in events
        if event.get("action") == "policy.exception_granted"
        and isinstance(event.get("details", {}).get("exception"), dict)
    ]
    if payload.get("decisions") != projected_decisions:
        errors.append("audit decision projection is stale")
    if payload.get("exceptions") != projected_exceptions:
        errors.append("audit exception projection is stale")
    for decision in projected_decisions:
        if decision.get("content_sha256") != canonical_hash(decision, {"content_sha256"}):
            errors.append(f"policy decision hash is invalid: {decision.get('id', 'unknown')}")
    head = events[-1].get("event_sha256") if events else None
    checkpoint = payload.get("checkpoint", {})
    if checkpoint.get("event_count") != len(events):
        errors.append("audit checkpoint event count is stale")
    if checkpoint.get("ledger_head_sha256") != head:
        errors.append("audit checkpoint ledger head is stale")
    expected_statistics = {
        "event_count": len(events),
        "actors": dict(sorted(Counter(event["actor"]["role"] for event in events).items())),
        "actions": dict(sorted(Counter(event["action"] for event in events).items())),
        "decisions": dict(sorted(Counter(item["status"] for item in projected_decisions).items())),
        "active_exceptions": len(projected_exceptions),
    }
    if payload.get("statistics") != expected_statistics:
        errors.append("audit statistics projection is stale")
    signature = checkpoint.get("signature")
    algorithm = checkpoint.get("signature_algorithm")
    if signature:
        if algorithm != "HMAC-SHA256":
            errors.append("unsupported audit checkpoint signature algorithm")
        elif signing_key is None:
            warnings.append("checkpoint signature present but no verification key was supplied")
        else:
            expected = hmac.new(
                signing_key,
                canonical_hash(checkpoint, {"signature"}).encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                errors.append("audit checkpoint signature is invalid")
    else:
        warnings.append("checkpoint is unsigned; configure LIGHTYEAR_AUDIT_SIGNING_KEY for live ledgers")
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        errors.append("audit snapshot content hash is invalid")
    return errors, warnings


def write_snapshot(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0) if path.suffix == ".gz" else raw)


def load_snapshot(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))
