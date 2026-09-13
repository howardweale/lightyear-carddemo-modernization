"""Read-only consumption of separately provisioned Control Tower human authority."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3

from lightyear_control_tower.decisions import ZERO, digest, verify_envelope
from .cloudbank_extensions import ENTRY_ID, WORKLOAD, decision_ledger
from .policy import _unique_object

TRUST = Path("work/control-tower/cloudbank-trust.json")
DATABASE = Path("work/control-tower/cloudbank-decisions.sqlite3")


def trust_config(root: Path) -> dict | None:
    path = root / TRUST
    if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
        raise ValueError("Symbolic decision authority path")
    if not path.exists():
        return None
    if path.stat().st_size > 32768:
        raise ValueError("Decision trust configuration exceeds bounds")
    value = json.loads(path.read_text(), object_pairs_hook=_unique_object)
    if set(value) != {"schema_version", "workload_id", "public_key_pem", "operators"} or value["schema_version"] != "1.0" or value["workload_id"] != WORKLOAD:
        raise ValueError("Unsupported CloudBank decision trust")
    if not isinstance(value["public_key_pem"], str) or not isinstance(value["operators"], list) or not 1 <= len(value["operators"]) <= 32:
        raise ValueError("Invalid CloudBank authority")
    ids = []
    for operator in value["operators"]:
        if set(operator) != {"id", "name", "roles"} or not all(isinstance(operator[k], str) and operator[k] for k in ("id", "name")) or operator["roles"] != ["normalization-approver"]:
            raise ValueError("Invalid trusted human operator")
        ids.append(operator["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate trusted operator")
    return value


def read_events(db) -> list[dict]:
    rows = db.execute("SELECT envelope FROM events ORDER BY sequence LIMIT 257").fetchall()
    if len(rows) > 256 or sum(len(row[0]) for row in rows) > 262144:
        raise ValueError("Decision journal exceeds bounds")
    return [json.loads(row[0], object_pairs_hook=_unique_object) for row in rows]


def validate_approval(root: Path, trust: dict, events: list[dict], at: datetime) -> dict:
    """Verify the full chain, authenticated review, exact terms, latest decision and expiry."""
    if at.tzinfo is None:
        raise ValueError("Application time must include timezone")
    # Review dates are UTC dates; a different offset cannot extend an approval.
    at = at.astimezone(timezone.utc)
    ledger = decision_ledger(root)
    rule = ledger["rules"][0]
    binding = {"entry_id": ENTRY_ID, "entry_sha256": digest(rule),
               "ledger_sha256": digest(ledger), "workload_id": WORKLOAD}
    key = trust["public_key_pem"].encode()
    operators = {o["id"]: o for o in trust["operators"]}
    previous, last_time, latest = ZERO, None, None
    sessions, reviews, requests = {}, {}, set()
    for sequence, event in enumerate(events, 1):
        if not isinstance(event, dict) or not isinstance(event.get("actor"), dict) or not isinstance(event.get("payload"), dict):
            raise ValueError("Malformed human decision event")
        if event.get("sequence") != sequence or event.get("previous_sha256") != previous or event.get("record_type") != "control-tower-decision-event" or event.get("schema_version") != "1.0" or not verify_envelope(event, key):
            raise ValueError("Untrusted or discontinuous human decision journal")
        when = datetime.fromisoformat(event["occurred_at"])
        if when.tzinfo is None or when > at or (last_time and when < last_time):
            raise ValueError("Invalid human decision time")
        when = when.astimezone(timezone.utc)
        previous, last_time = event["content_sha256"], when
        kind, payload, actor, sid = event["kind"], event["payload"], event["actor"], event["session_id"]
        if kind not in {"session_started", "session_ended", "normalization_viewed", "normalization_decided"}:
            raise ValueError("Unsupported decision journal event")
        operator = operators.get(actor.get("id"))
        if not operator or actor != {"id": operator["id"], "name": operator["name"], "kind": "operator"}:
            raise ValueError("Decision actor is not a trusted human operator")
        if kind == "session_started":
            expires = datetime.fromisoformat(payload["expires_at"])
            if sid in sessions or not isinstance(sid, str) or not sid or expires.tzinfo is None or not 0 < (expires - when).total_seconds() <= 3600 or payload.get("authentication") != "individual-local-credential":
                raise ValueError("Invalid authenticated human session")
            sessions[sid] = (actor, expires)
            continue
        if sid not in sessions or sessions[sid][0] != actor or when >= sessions[sid][1]:
            raise ValueError("Decision lacks a current authenticated operator session")
        if kind == "session_ended":
            del sessions[sid]
        elif kind == "normalization_viewed":
            reviews[sid] = payload
        else:
            if {k: payload.get(k) for k in binding} != binding or reviews.get(sid) != binding:
                raise ValueError("Decision lacks exact reviewed entry, ledger and scope binding")
            if payload.get("previous_decision_sha256") != (latest or {}).get("content_sha256"):
                raise ValueError("Decision supersession chain changed")
            if payload.get("channel") != "control-tower" or payload.get("authentication") != "individual-local-credential" or not all(isinstance(payload.get(k), str) and payload[k].strip() for k in ("owner", "reason", "request_id", "request_sha256")):
                raise ValueError("Missing human intent provenance")
            if payload["request_id"] in requests or payload.get("outcome") not in {"approved", "rejected"}:
                raise ValueError("Invalid or repeated human decision")
            requests.add(payload["request_id"])
            if payload["outcome"] == "approved" and not when.date() < date.fromisoformat(payload["review_after"]) <= date.fromisoformat(rule["review_after"]):
                raise ValueError("Invalid governed review expiry")
            latest = event
    if not latest or latest["payload"]["outcome"] != "approved":
        raise ValueError("Current signed human approval is missing or revoked")
    if at.date() >= date.fromisoformat(latest["payload"]["review_after"]):
        raise ValueError("Human approval expired at application time")
    return {**binding, "decision": latest, "journal_head_sha256": previous,
            "events": events, "checked_at": at.isoformat()}


def verify_application_history(root: Path, approval: dict) -> None:
    """A signed prefix cannot conceal a decision already present at application time."""
    path = root / DATABASE
    if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
        raise ValueError("Symbolic decision journal path")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        current = read_events(db)
    finally:
        db.close()
    retained = approval["events"]
    checked = datetime.fromisoformat(approval["checked_at"])
    if current[:len(retained)] != retained or any(datetime.fromisoformat(e["occurred_at"]) <= checked for e in current[len(retained):]):
        raise ValueError("Application omitted or changed authoritative human decision history")


@contextmanager
def approval_guard(root: Path):
    """Keep the decision writer excluded through the engine's application commit.

    The transaction reserves the existing database but never writes decision data.
    It closes the revoke/check/apply race with the Control Tower's own transaction.
    """
    trust = trust_config(root)
    if not trust:
        raise ValueError("CloudBank human decision authority is not provisioned")
    path = root / DATABASE
    if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
        raise ValueError("Symbolic decision journal path")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=2)
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("PRAGMA query_only=ON")
        at = datetime.now(timezone.utc)
        yield validate_approval(root, trust, read_events(db), at)
    finally:
        db.rollback()
        db.close()


def current_approval(root: Path) -> dict:
    """A genuinely read-only live check for Tower projection and admission display."""
    try:
        trust = trust_config(root)
        if not trust:
            raise ValueError("CloudBank human decision authority is not provisioned")
        path = root / DATABASE
        if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
            raise ValueError("Symbolic decision journal path")
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            approval = validate_approval(root, trust, read_events(db), datetime.now(timezone.utc))
        finally:
            db.close()
        return {"status": "approved", "decision_sha256": approval["decision"]["content_sha256"]}
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, ImportError) as exc:
        return {"status": "blocked", "reason": str(exc)}
