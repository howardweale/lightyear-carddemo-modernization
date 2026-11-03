"""Public human-event metrics: corrections append; missing coverage stays unknown.

The emitter returns one JSONL record for a separately owned durable sink. It
never signs, writes a live journal or attests that all human activity was logged.
"""
from datetime import datetime
from hashlib import sha256
import json
import re

from .contracts import canonical_hash
from .journal_metrics import (
    MAX_EVENTS, MAX_JOURNAL_BYTES, MetricsError, _constant, _digest,
    _identifier, _integer, _object, _require,
)

ACTIONS = frozenset({
    "preparation", "policy-approval", "exact-hash-approval", "sign-export",
    "environment-approval", "manual-transfer", "dispatch", "stop", "repair",
    "retry-authorization-or-refusal", "custody-touch-session", "invoice-reconciliation",
})
FIELDS = frozenset({
    "event_id", "actor_id", "occurred_at", "campaign_id", "exact_e", "case_ids",
    "execution_ids", "action", "evidence_sha256s", "supersedes_event_id",
})
CHAIN_FIELDS = frozenset({
    "schema", "sequence", "previous_event_sha256", "content_sha256",
})


def _identifiers(values, *, empty=False):
    return (isinstance(values, list) and (empty or bool(values)) and
            all(_identifier(value) for value in values) and
            len(set(values)) == len(values))


def _validate(event):
    _require(isinstance(event, dict) and set(event) == FIELDS | CHAIN_FIELDS,
             "human-metrics-field-set")
    _require(event["schema"] == "factory-human-event/1", "human-metrics-schema")
    sequence = _integer(event["sequence"])
    _require(sequence > 0 and
             (event["previous_event_sha256"] is None if sequence == 1
              else _digest(event["previous_event_sha256"])), "human-metrics-chain-shape")
    _require(all(_identifier(event[name]) for name in ("event_id", "actor_id", "campaign_id")),
             "human-metrics-identity")
    _require(isinstance(event["exact_e"], str) and
             re.fullmatch(r"[0-9a-f]{40}", event["exact_e"]) is not None,
             "human-metrics-source")
    _require(_identifiers(event["case_ids"]) and
             _identifiers(event["execution_ids"], empty=True), "human-metrics-scope")
    _require(isinstance(event["action"], str) and event["action"] in ACTIONS,
             "human-metrics-action")
    evidence = event["evidence_sha256s"]
    _require(isinstance(evidence, list) and evidence and
             all(_digest(value) for value in evidence) and len(set(evidence)) == len(evidence),
             "human-metrics-evidence")
    _require(event["supersedes_event_id"] is None or _identifier(event["supersedes_event_id"]),
             "human-metrics-correction")
    timestamp = event["occurred_at"]
    _require(isinstance(timestamp, str) and "T" in timestamp, "human-metrics-time")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise MetricsError("human-metrics-time") from None
    _require(parsed.utcoffset() is not None, "human-metrics-time-offset")
    _require(_digest(event["content_sha256"]) and
             canonical_hash(event, {"content_sha256"}) == event["content_sha256"],
             "human-metrics-event-digest")


def encode_human_event(fields, *, sequence, previous_event_sha256):
    """Return one public record; caller owns append/fsync and authentication.

    Only structured IDs, action labels, timestamps and public evidence digests
    are accepted. Free-text notes, PINs, private keys and identity files have no
    field in this schema. Corrections use a new ID and supersede the latest ID.
    """
    _require(isinstance(fields, dict) and set(fields) == FIELDS,
             "human-metrics-field-set")
    event = dict(fields, schema="factory-human-event/1", sequence=sequence,
                 previous_event_sha256=previous_event_sha256)
    try:
        event["content_sha256"] = canonical_hash(event)
    except (TypeError, ValueError):
        raise MetricsError("human-metrics-nonjson-field") from None
    _validate(event)
    return (json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def collect_human_events(raw, *, source_sha256, exact_e, campaign_id, case_ids):
    """Project a complete exported stream, without certifying activity coverage.

    Corrections retain the old records but replace their contribution. A shared
    action contributes once globally and is referenced on each affected case.
    A zero observed count never means zero actual interventions.
    """
    _require(_identifiers(case_ids) and len(case_ids) == 19, "human-metrics-inventory")
    _require(_identifier(campaign_id) and isinstance(exact_e, str) and
             re.fullmatch(r"[0-9a-f]{40}", exact_e) is not None, "human-metrics-binding")
    _require(type(raw) is bytes and len(raw) <= MAX_JOURNAL_BYTES and
             _digest(source_sha256) and sha256(raw).hexdigest() == source_sha256,
             "human-metrics-source-drift")
    _require(not raw or raw.endswith(b"\n"), "human-metrics-truncated-stream")
    lines = raw.splitlines()
    _require(len(lines) <= MAX_EVENTS and all(lines), "human-metrics-event-count")
    previous = None
    seen, active, roots = {}, {}, {}
    for sequence, line in enumerate(lines, 1):
        try:
            event = json.loads(line, object_pairs_hook=_object, parse_constant=_constant)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise MetricsError("human-metrics-invalid-json") from None
        _validate(event)
        _require(event["sequence"] == sequence and event["previous_event_sha256"] == previous,
                 "human-metrics-chain")
        _require(event["exact_e"] == exact_e and event["campaign_id"] == campaign_id and
                 set(event["case_ids"]) <= set(case_ids), "human-metrics-cross-scope")
        identity = event["event_id"]
        _require(identity not in seen, "human-metrics-duplicate-id")
        supersedes = event["supersedes_event_id"]
        if supersedes is None:
            root = identity
        else:
            _require(supersedes in seen, "human-metrics-unknown-correction")
            root = roots[supersedes]
            _require(active[root]["event_id"] == supersedes, "human-metrics-correction-fork")
        roots[identity] = root
        active[root] = event
        seen[identity] = event
        previous = event["content_sha256"]
    effective = []
    for root, event in sorted(active.items()):
        effective.append(dict(root_event_id=root, event_id=event["event_id"],
                              actor_id=event["actor_id"], action=event["action"],
                              occurred_at=event["occurred_at"], case_ids=event["case_ids"],
                              execution_ids=event["execution_ids"],
                              evidence_sha256s=event["evidence_sha256s"],
                              event_sha256=event["content_sha256"]))
    rows = []
    for case in case_ids:
        ids = [event["event_id"] for event in effective if case in event["case_ids"]]
        rows.append(dict(case_id=case, observed_event_ids=ids, observed_event_count=len(ids),
                         actual_intervention_count=None, coverage_attested=False))
    result = dict(schema="factory-human-metrics/1", exact_e=exact_e, campaign_id=campaign_id,
                  source_sha256=source_sha256, journal_head_sha256=previous,
                  recorded_rows=len(seen), correction_rows=len(seen)-len(active),
                  observed_event_count=len(active), effective_events=effective, cases=rows,
                  actual_intervention_count=None, coverage_attested=False,
                  missing_reason="complete-human-coverage-and-receipt-authentication-not-established",
                  production_qualification=False)
    result["content_sha256"] = canonical_hash(result)
    return result
