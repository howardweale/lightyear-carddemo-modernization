"""Public human-event/execution-receipt joins, without coverage or billing claims.

The integrating caller authenticates each exact receipt with its existing
verifier and trusted inventory. Hash equality alone is never authentication.
This projection does not sign, append, dispatch, retry, or confer authority.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from .contracts import canonical_hash
from .human_metrics import collect_human_events
from .journal_metrics import (
    MAX_EVENTS, MAX_JOURNAL_BYTES, MetricsError, _constant, _digest,
    _identifier, _object, _require,
)


@dataclass(frozen=True)
class ExecutionReference:
    """Expected public join, supplied independently of receipt/event contents."""

    case_id: str
    execution_id: str
    attempt_identity_sha256: str
    receipt_sha256: str | None

    def validate(self):
        _require(_identifier(self.case_id) and _identifier(self.execution_id),
                 "execution-join-identity")
        _require(_digest(self.attempt_identity_sha256), "execution-join-attempt")
        _require(self.receipt_sha256 is None or _digest(self.receipt_sha256),
                 "execution-join-receipt-digest")


RECEIPT_FIELDS = frozenset({
    "schema", "exact_e", "campaign_id", "case_id", "execution_id",
    "attempt_identity_sha256",
})


def _receipt(raw, ref, *, exact_e, campaign_id, authenticate_receipt):
    """Validate a public adapter receipt; production receipt adapters are separate.

    authenticate_receipt(raw, ref) must use the caller's existing verifier and
    trusted authority context, and return the singleton True on success.
    Receipt bytes and the frozen expected reference are passed unchanged.
    """
    try:
        row = json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise MetricsError("execution-join-receipt-json") from None
    _require(type(row) is dict and set(row) == RECEIPT_FIELDS,
             "execution-join-receipt-fields")
    expected = dict(
        schema="factory-metrics-execution-receipt/1", exact_e=exact_e,
        campaign_id=campaign_id, case_id=ref.case_id, execution_id=ref.execution_id,
        attempt_identity_sha256=ref.attempt_identity_sha256)
    _require(row == expected, "execution-join-cross-binding")
    _require(callable(authenticate_receipt), "execution-join-authenticator-required")
    try:
        authenticated = authenticate_receipt(raw, ref)
    except Exception as exc:
        raise MetricsError("execution-join-authentication-failed") from exc
    _require(authenticated is True, "execution-join-authentication-refused")


def collect_execution_joins(raw, *, human_source_sha256, exact_e, campaign_id,
                            case_ids, executions, receipts, authenticate_receipt):
    """Join active (post-correction) human events to exact authenticated receipts.

    Missing receipts, absent evidence links and ambiguous attempts stay unknown.
    Each shared human event contributes once globally; per-execution references
    are not additional interventions. An empty export is never zero actual work.
    Receipt schema here is a public adapter contract, not production integration.
    The caller must independently retain/authenticate the journal source digest
    and inventory. Receipt hashes occur in events, never the reverse: this
    avoids a circular journal/receipt hash dependency.
    """
    humans = collect_human_events(
        raw, source_sha256=human_source_sha256, exact_e=exact_e,
        campaign_id=campaign_id, case_ids=case_ids)
    _require(type(executions) is tuple and len(executions) <= MAX_EVENTS,
             "execution-join-inventory")
    inventory = {}
    expected_digests = {}
    by_execution = {}
    for ref in executions:
        _require(type(ref) is ExecutionReference, "execution-join-reference")
        ref.validate()
        _require(ref.case_id in case_ids, "execution-join-unknown-case")
        key = (ref.case_id, ref.execution_id, ref.attempt_identity_sha256)
        _require(key not in inventory, "execution-join-duplicate-attempt")
        inventory[key] = ref
        by_execution.setdefault(ref.execution_id, []).append(ref)
        if ref.receipt_sha256 is not None:
            _require(ref.receipt_sha256 not in expected_digests,
                     "execution-join-reused-receipt")
            expected_digests[ref.receipt_sha256] = ref
    _require(type(receipts) is tuple and len(receipts) <= MAX_EVENTS,
             "execution-join-receipts")
    _require(all(type(item) is bytes and 0 < len(item) <= MAX_JOURNAL_BYTES
                 for item in receipts), "execution-join-receipt-size")
    _require(sum(len(item) for item in receipts) <= MAX_JOURNAL_BYTES,
             "execution-join-receipt-total-size")
    authenticated = set()
    for item in receipts:
        digest = sha256(item).hexdigest()
        _require(digest not in authenticated, "execution-join-duplicate-receipt")
        _require(digest in expected_digests, "execution-join-unexpected-receipt")
        ref = expected_digests[digest]
        _receipt(item, ref, exact_e=exact_e, campaign_id=campaign_id,
                 authenticate_receipt=authenticate_receipt)
        authenticated.add(digest)

    events = []
    linked_by_attempt = {key: [] for key in inventory}
    joined_event_ids = []
    for event in humans["effective_events"]:
        joins = []
        covered_cases = set()
        for execution_id in sorted(event["execution_ids"]):
            candidates = [ref for ref in by_execution.get(execution_id, ())
                          if ref.case_id in event["case_ids"]]
            linked = [ref for ref in candidates
                      if ref.receipt_sha256 in authenticated and
                      ref.receipt_sha256 in event["evidence_sha256s"]]
            # A single event may span different cases, but may not select two
            # attempts of the same execution/case as though they were one.
            for case_id in sorted({ref.case_id for ref in candidates}):
                scoped = [ref for ref in linked if ref.case_id == case_id]
                if len(scoped) == 1:
                    ref = scoped[0]
                    key = (ref.case_id, ref.execution_id, ref.attempt_identity_sha256)
                    linked_by_attempt[key].append(event["event_id"])
                    joins.append(dict(
                        case_id=case_id, execution_id=execution_id,
                        attempt_identity_sha256=ref.attempt_identity_sha256,
                        receipt_sha256=ref.receipt_sha256, status="joined",
                        missing_reason=None))
                    covered_cases.add(case_id)
                else:
                    joins.append(dict(
                        case_id=case_id, execution_id=execution_id,
                        attempt_identity_sha256=None, receipt_sha256=None,
                        status="unknown", missing_reason=(
                            "ambiguous-attempt" if scoped else
                            "authenticated-receipt-or-evidence-link-missing")))
            if not candidates:
                joins.append(dict(
                    case_id=None, execution_id=execution_id,
                    attempt_identity_sha256=None, receipt_sha256=None,
                    status="unknown", missing_reason="execution-not-in-case-inventory"))
        missing_cases = sorted(set(event["case_ids"]) - covered_cases)
        complete = bool(joins) and not missing_cases and all(
            item["status"] == "joined" for item in joins)
        if complete:
            joined_event_ids.append(event["event_id"])
        events.append(dict(
            root_event_id=event["root_event_id"], event_id=event["event_id"],
            event_sha256=event["event_sha256"], joins=joins,
            missing_case_ids=missing_cases, all_declared_links_joined=complete,
            missing_reason=(None if complete else
                            "no-execution-reference" if not joins else
                            "incomplete-or-ambiguous-join")))

    rows = []
    for key, ref in sorted(inventory.items()):
        ids = linked_by_attempt[key]
        rows.append(dict(
            case_id=ref.case_id, execution_id=ref.execution_id,
            attempt_identity_sha256=ref.attempt_identity_sha256,
            receipt_sha256=ref.receipt_sha256,
            receipt_verified_by_caller=ref.receipt_sha256 in authenticated,
            observed_linked_event_ids=ids, observed_linked_event_count=len(ids),
            actual_intervention_count=None, coverage_attested=False))
    result = dict(
        schema="factory-metrics-execution-joins/1", exact_e=exact_e,
        campaign_id=campaign_id, human_source_sha256=human_source_sha256,
        human_projection_sha256=humans["content_sha256"],
        observed_event_count=humans["observed_event_count"],
        fully_joined_event_ids=joined_event_ids,
        observed_fully_joined_event_count=len(joined_event_ids),
        events=events, executions=rows, actual_intervention_count=None,
        complete_coverage=False, production_qualification=False,
        physical_send_proven=False, billing_final=False,
        missing_reason="complete-human-coverage-not-established")
    result["content_sha256"] = canonical_hash(result)
    return result
