"""Bound, deterministic validation; no shell commands or workload execution.

Additional lane replay/rule validators must be registered by trusted application
code. A request cannot supply executable Python, a command, or a validator.
"""

import hashlib
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from carddemo_oracle.compare import validate_normalization_ledger, NORMALIZATION_RULES
from .decisions import DecisionConflict, digest, verify_envelope
from .requests import confined, read_json, identifier
from .verification import verify_decision


def evidence(root, item, name):
    path = confined(root, item["evidence"][name])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != item["bound"][name]:
        raise DecisionConflict("Evidence changed, review again")
    return read_json(path)


from .rule_types import typed_rule


def still_caught(rule, fixture):
    """Exercise the registered normalization on a positive pair and planted fault.

    These are explicit public test values, never native holdout captures. Unknown
    operations fail closed. No rule text is interpreted as code.
    """
    typed_rule(rule)
    if fixture.get("schema") != "tower-still-caught/1" or fixture.get(
        "rule_sha256"
    ) != digest(rule):
        raise ValueError("Still-caught fixture does not bind this rule")

    def normalize(value):
        op = rule["operation"]
        if op == "fixed-width-right-padding":
            if not isinstance(value, str):
                raise ValueError("Text fixture required")
            return value.rstrip()
        if op == "decimal-canonical-text":
            number = Decimal(str(value))
            if not number.is_finite():
                raise ValueError("Finite decimal required")
            return number
        if op == "copybook-filler":
            if not isinstance(value, dict):
                raise ValueError("Record fixture required")
            return {k: v for k, v in value.items() if k != "filler"}
        raise ValueError("Unregistered rule")

    try:
        a, b = fixture["positive"]
        x, y = fixture["planted_fault"]
        passed = (
            normalize(a) == normalize(b) and normalize(x) != normalize(y) and x != y
        )
    except (KeyError, ValueError, TypeError, InvalidOperation):
        passed = False
    return {
        "schema": "tower-still-caught-result/1",
        "passed": passed,
        "rule_sha256": digest(rule),
        "fixture_sha256": digest(fixture),
        "validator": "registered-normalizations/1",
    }


def qualification_replay(record, replay, key):
    """Verify the portable LAS fixture protocol until the LAS adapter is supplied.

    The qualification's signed outcome is not recomputed or promoted. Replay
    requires each signed control receipt and its exact expected outcome.
    """
    if record.get("schema") != "lane-qualification/1" or not verify_envelope(
        record, key
    ):
        raise DecisionConflict("Qualification signature invalid")
    if record.get("fixture_only") is not True:
        raise DecisionConflict(
            "Install the LAS native replay adapter before accepting production qualifications"
        )
    if (
        replay.get("schema") != "lane-replay/1"
        or replay.get("qualification_sha256") != record["content_sha256"]
    ):
        raise DecisionConflict("Replay binding invalid")
    receipts = replay.get("receipts", [])
    controls = record.get("controls", [])
    if not controls or len(receipts) != len(controls):
        raise DecisionConflict("Replay incomplete")
    ids = set()
    for control, receipt in zip(controls, receipts):
        if (
            control["id"] in ids
            or not verify_envelope(receipt, key)
            or receipt.get("id") != control["id"]
            or receipt.get("content_sha256") != control["receipt_sha256"]
            or receipt.get("outcome") != control["expected_outcome"]
        ):
            raise DecisionConflict("Replay control failed")
        ids.add(control["id"])
    return {
        "passed": True,
        "controls_replayed": len(controls),
        "qualification_sha256": record["content_sha256"],
        "replay_protocol": "signed-control-receipts/1",
        "native_execution_repeated": False,
    }


class WorkflowValidation:
    def __init__(self, service):
        self.service = service
        for kind in (
            "rule-technical-review",
            "rule-approval",
            "rule-retirement",
            "qualification-acceptance",
        ):
            service.validators[kind] = self.validate

    def inspect(self, item, events):
        s = self.service
        kind = item["kind"]
        result = {}
        if kind == "rule-technical-review":
            rule = evidence(s.root, item, "rule")
            typed_rule(rule)
            test = evidence(s.root, item, "still_caught")
            result["still_caught"] = still_caught(rule, test)
            # The bound ledger itself is validated, not a caller's claimed result.
            result["ledger"] = validate_normalization_ledger(
                confined(s.root, item["evidence"]["ledger_validation"])
            )
            result["passed"] = (
                result["still_caught"]["passed"]
                and result["ledger"]["status"] == "passed"
            )
        elif kind == "rule-approval":
            rule = typed_rule(evidence(s.root, item, "rule"))
            proof = evidence(s.root, item, "technical_review")
            p = verify_decision(
                proof,
                s.public_key,
                "rule-technical-review",
                proof["journal"]["events"][
                    next(
                        i
                        for i, e in enumerate(proof["journal"]["events"])
                        if e["content_sha256"] == proof["decision_sha256"]
                    )
                ]["payload"]["bound"],
                scope=s.scope,
                outcomes=("approved",),
            )
            current = next(
                (
                    e
                    for e in reversed(events)
                    if e["kind"] == "tower_decision"
                    and e["payload"]["kind"] == "rule-technical-review"
                    and e["payload"]["item_id"] == p["item_id"]
                ),
                None,
            )
            if (
                not current
                or current["content_sha256"] != proof["decision_sha256"]
                or p["bound"]["rule"] != item["bound"]["rule"]
            ):
                raise DecisionConflict(
                    "Technical review changed or applies to another rule"
                )
            if p["actor"]["id"] == rule["proposed_by"]:
                raise DecisionConflict("Independent technical review required")
            result = {"passed": True, "technical_reviewer": p["actor"]["id"]}
        elif kind == "rule-retirement":
            typed_rule(evidence(s.root, item, "rule"))
            result = {"passed": True}
        elif kind == "qualification-acceptance":
            # Trusted issuer is locally configured, never read from the request.
            cfg = read_json(s.root / "control-tower/qualification-trust.json")
            if cfg.get("scope") != s.scope:
                raise DecisionConflict("Wrong qualification trust scope")
            key = confined(s.root, cfg["public_key"]).read_bytes()
            result = qualification_replay(
                evidence(s.root, item, "qualification"),
                evidence(s.root, item, "replay"),
                key,
            )
        return result

    def validate(self, item, payload, events, session):
        if payload["outcome"] in {"rejected"}:
            return
        if item["kind"].startswith("rule-"):
            rule = typed_rule(evidence(self.service.root, item, "rule"))
            if rule["proposed_by"] == session["actor"]["id"]:
                raise DecisionConflict(
                    "The rule proposer cannot approve their own rule"
                )
            if item["kind"] != "rule-technical-review" and rule["workload"] != item.get(
                "workload"
            ):
                raise DecisionConflict("Rule workload mismatch")
        result = self.inspect(item, events)
        if not result.get("passed"):
            raise DecisionConflict("Required validation failed")
        if item["kind"] == "rule-approval":
            result["business_owner_is_technical_reviewer"] = (
                result["technical_reviewer"] == session["actor"]["id"]
            )
        return result


def rule_register(service, token, *, now=None):
    """Derived signed projection only. Expired reviews warn; retirement removes.

    Does not publish, edit the judge, or make an existing divergent verdict pass.
    """
    service._read_access(token)
    today = now or date.today()
    with service.transaction() as db:
        events = service.events(db)
        rules = {}
        for e in events:
            if e["kind"] != "tower_decision":
                continue
            p = e["payload"]
            kind = p["kind"]
            if kind not in {"rule-approval", "rule-retirement"}:
                continue
            h = p["bound"]["rule"]
            if kind == "rule-approval" and p["outcome"] == "approved":
                item = service.inbox.item(p["item_id"])
                if item["bound"] != p["bound"]:
                    raise DecisionConflict(
                        "Approved rule evidence unavailable or changed"
                    )
                rule = typed_rule(evidence(service.root, item, "rule"))
                rules[h] = {
                    "rule": rule,
                    "owner": p["named_owner"],
                    "review_after": p["review_after"],
                    "approval_sha256": e["content_sha256"],
                    "technical_review_sha256": p["bound"]["technical_review"],
                }
            elif kind == "rule-approval":
                rules.pop(h, None)
            elif p["outcome"] == "retired":
                rules.pop(h, None)
            elif p["outcome"] == "renewed" and h in rules:
                rules[h].update(
                    owner=p["named_owner"],
                    review_after=p["review_after"],
                    renewal_sha256=e["content_sha256"],
                )
        for r in rules.values():
            r["review_due"] = date.fromisoformat(r["review_after"]) <= today
        return service.sign(
            {
                "schema": "rule-register/1",
                "scope": service.scope,
                "version": sum(
                    e["kind"] == "tower_decision"
                    and e["payload"]["kind"].startswith("rule-")
                    for e in events
                ),
                "major_version": 1,
                "rules": [rules[h] for h in sorted(rules)],
                "verdicts_changed": False,
            }
        )
