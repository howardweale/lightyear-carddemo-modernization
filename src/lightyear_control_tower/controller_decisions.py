"""Admission for NEW headless controllers only; never imported by frozen MS94.

The engine supplies a fresh journal export/head through its trusted local handoff.
This module records/dispatches nothing and cannot bypass host execution approvals.
"""

from .verification import verify_decision, verify_journal, check
from .decisions import canonical
import hashlib


def pause_evidence(event):
    """Exact evidence-file bytes to bind a resume request to a signed pause."""
    return canonical(event) + b"\n"


class TowerControllerV2:
    def __init__(self, public_key, scope, campaign_hash, authorization_bound):
        self.key = public_key
        self.scope = scope
        self.campaign = campaign_hash
        self.bound = authorization_bound

    def before_slot(self, proof, *, fresh_head):
        check(proof is not None, "authorization-required")
        auth = verify_decision(
            proof,
            self.key,
            "campaign-authorization",
            self.bound,
            scope=self.scope,
            expected_head=fresh_head,
            outcomes=("authorized",),
        )
        events = verify_journal(
            proof["journal"], self.key, scope=self.scope, expected_head=fresh_head
        )
        relevant = [
            e
            for e in events
            if e["kind"] == "tower_decision"
            and e["payload"]["kind"] == "measurement-validity"
            and e["payload"]["bound"].get("campaign") == self.campaign
        ]
        # Stop/void are terminal across items, not silently superseded by a continue.
        for e in relevant:
            check(
                e["payload"]["outcome"] not in {"stop", "void"},
                "campaign-" + e["payload"]["outcome"],
            )
        if relevant:
            p = relevant[-1]["payload"]
            verify_decision(
                {
                    "schema": "tower-decision-proof/1",
                    "decision_sha256": relevant[-1]["content_sha256"],
                    "journal": proof["journal"],
                },
                self.key,
                "measurement-validity",
                p["bound"],
                scope=self.scope,
                expected_head=fresh_head,
            )
            if p["outcome"] == "pause":
                resumes = [
                    e
                    for e in events
                    if e["kind"] == "tower_decision"
                    and e["payload"]["kind"] == "resume"
                    and e["payload"]["bound"].get("campaign") == self.campaign
                    and e["payload"]["bound"].get("pause")
                    == hashlib.sha256(pause_evidence(relevant[-1])).hexdigest()
                ]
                check(bool(resumes), "campaign-paused")
                r = resumes[-1]
                verify_decision(
                    {
                        "schema": "tower-decision-proof/1",
                        "decision_sha256": r["content_sha256"],
                        "journal": proof["journal"],
                    },
                    self.key,
                    "resume",
                    r["payload"]["bound"],
                    scope=self.scope,
                    expected_head=fresh_head,
                    outcomes=("resume",),
                )
        return {"status": "admitted", "authorization": auth, "controller_version": 2}

    def run(self, slots, *, handoff, execute_slot):
        """Engine-side boundary: fresh handoff before *every* slot, including first."""
        results = []
        for slot in slots:
            proof, head = handoff()
            self.before_slot(proof, fresh_head=head)
            results.append(execute_slot(slot))
        return results
