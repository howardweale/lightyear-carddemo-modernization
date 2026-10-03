"""Offline, fail-closed verification shared by future engine consumers."""

from datetime import datetime, timezone, date
from .decisions import ZERO, verify_envelope
from .kinds import default_registry


class DecisionVerificationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def check(condition, code):
    if not condition:
        raise DecisionVerificationError(code)


def subject(kind, bound):
    if kind == "normalization" and "rule" in bound:
        return (("rule", bound["rule"]),)
    keys = {
        "campaign-authorization": ("campaign", "plan", "declaration"),
        "qualification-acceptance": ("qualification",),
        "rule-technical-review": ("rule",),
        "rule-approval": ("rule",),
        "rule-retirement": ("rule",),
        "classification-acceptance": ("classification", "item_ids"),
        "evidence-release": ("archive",),
    }.get(kind, default_registry().get(kind).hashes)
    return tuple((k, bound.get(k)) for k in keys)


def verify_journal(export, key, *, scope=None, expected_head=None):
    check(verify_envelope(export, key), "invalid-export-signature")
    check(
        export.get("record_type")
        in {"control-tower-session-export", "tower-journal-export/1"},
        "invalid-export-type",
    )
    if scope is not None:
        check(export.get("scope") == scope, "scope-mismatch")
    previous = ZERO
    for seq, event in enumerate(export.get("events", []), 1):
        check(
            isinstance(event, dict) and verify_envelope(event, key),
            "invalid-event-signature",
        )
        check(
            event.get("sequence") == seq and event.get("previous_sha256") == previous,
            "broken-journal-chain",
        )
        previous = event["content_sha256"]
    check(export.get("journal_head_sha256") == previous, "journal-head-mismatch")
    if expected_head is not None:
        check(previous == expected_head, "stale-journal-head")
    return export["events"]


def verify_decision(
    record,
    trusted_public_key,
    kind,
    bound,
    *,
    expected_head=None,
    scope=None,
    outcomes=None,
    now=None,
):
    """Verify a proof against its signed head; consumers pin a fresh head out of band.

    A signature cannot establish that an old export is the newest export. Online
    consumers MUST supply the current trusted journal head; offline replay proves
    validity at the head supplied in the archive, not present-day authorization.
    """
    try:
        check(record.get("schema") == "tower-decision-proof/1", "invalid-proof")
        export = record["journal"]
        events = verify_journal(
            export, trusted_public_key, scope=scope, expected_head=expected_head
        )
        event = next(
            (e for e in events if e["content_sha256"] == record["decision_sha256"]),
            None,
        )
        check(
            event is not None and event["kind"] == "tower_decision",
            "decision-not-in-journal",
        )
        p = event["payload"]
        check(
            p.get("schema") == "tower-decision/1"
            and p.get("kind") == kind
            and p.get("kind_version") == 1,
            "kind-mismatch",
        )
        check(p.get("scope") == export.get("scope"), "scope-mismatch")
        check(p.get("bound") == bound, "bound-hash-mismatch")
        policy = default_registry().get(kind)
        if p.get("scope") == "carddemo-zos":
            from .carddemo_policy import registry, HOWARD, agent_proposal, POLICY

            policy = registry().get(kind)
            check(p.get("disclosure_policy") == POLICY, "disclosure-policy-required")
            if kind != "evidence-release":
                check(p["actor"]["id"] == HOWARD, "howard-decision-required")
            if kind == "normalization":
                proposal = agent_proposal(p, events[: event["sequence"] - 1])
                check(
                    p.get("validation", {}).get("agent_proposal_sha256") == proposal,
                    "agent-proposal-binding-mismatch",
                )
        check(set(policy.hashes) <= set(bound), "incomplete-bound-hashes")
        check(p.get("outcome") in (outcomes or policy.outcomes), "outcome-refused")
        check(
            p.get("channel") == "control-tower"
            and p.get("actor") == event["actor"]
            and p.get("session_id") == event["session_id"],
            "identity-mismatch",
        )
        check(
            p["actor"].get("kind") not in {"agent", "service"}
            and bool(set(p.get("roles_held", [])) & set(policy.roles)),
            "role-refused",
        )
        if policy.independence == "required":
            from .proposals import proposal_actor

            author = proposal_actor(p, events[: event["sequence"] - 1])
            check(
                author != p["actor"]["id"] and p.get("proposed_by") == author,
                "independence-required",
            )
            check(
                p.get("independence")
                == (
                    "operator-review"
                    if kind == "classification-acceptance"
                    else "independent"
                )
                and not p.get("decider_is_proposer"),
                "independence-required",
            )
        if kind == "classification-acceptance":
            ids = p.get("classification_item_ids", [])
            decisions = p.get("item_decisions", {})
            check(
                bool(ids)
                and len(set(ids)) == len(ids)
                and set(decisions) == set(ids)
                and all(v in {"accept", "reject"} for v in decisions.values()),
                "classification-items-required",
            )
            check(
                p["outcome"] != "accept"
                or all(v == "accept" for v in decisions.values()),
                "classification-overall-mismatch",
            )
        later = [
            e
            for e in events[event["sequence"] :]
            if e["kind"] == "tower_decision"
            and e["payload"].get("scope") == p["scope"]
            and e["payload"].get("kind") == kind
            and subject(kind, e["payload"].get("bound", {})) == subject(kind, bound)
            and e["payload"].get("decision_slot") == p.get("decision_slot")
        ]
        check(not later, "decision-superseded")
        if p.get("review_after"):
            today = (now or datetime.now(timezone.utc)).date()
            check(date.fromisoformat(p["review_after"]) > today, "decision-expired")
        return p
    except DecisionVerificationError:
        raise
    except (KeyError, ValueError, TypeError, AttributeError):
        raise DecisionVerificationError("malformed-decision") from None
