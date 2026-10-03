"""Authenticated authorship and evidence subjects, independent of inbox labels."""

from .decisions import digest
from .verification import check


def proposal_actor(item, events):
    bound = item["bound"]
    event = next(
        (
            e
            for e in events
            if e["kind"] == "tower_proposal"
            and e["content_sha256"] == bound.get("proposal")
        ),
        None,
    )
    check(event is not None, "authenticated-proposal-required")
    p = event["payload"]
    check(p.get("scope") == item["scope"], "proposal-scope-mismatch")
    if item["kind"].startswith("rule-"):
        check(p.get("proposal_type") == "rule-proposal", "proposal-kind-mismatch")
        check(
            p.get("bound", {}).get("rule") == bound.get("rule"),
            "proposal-rule-mismatch",
        )
        check(digest(p.get("rule")) == bound.get("rule"), "proposal-rule-mismatch")
    else:
        check(
            p.get("proposal_type") == "classification-draft", "proposal-kind-mismatch"
        )
        check(
            all(
                p.get("bound", {}).get(k) == bound.get(k)
                for k in ("classification", "item_ids")
            ),
            "proposal-classification-mismatch",
        )
    return event["actor"]["id"]
