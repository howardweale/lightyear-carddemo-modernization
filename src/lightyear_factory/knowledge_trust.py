"""Shared Tower verification for optional factory knowledge features.

Trust configuration is host owned. Proofs never supply their own trust key or
fresh head. Historical replay uses the head/time recorded at event admission.
"""

from datetime import datetime, timezone
from lightyear_control_tower.decisions import digest
from lightyear_control_tower.verification import verify_decision


def approve(proof, trust, kind, bindings, outcomes, *, now=None):
    if not trust.get("trusted_head") or not trust.get("scope"):
        raise ValueError("fresh Tower head and scope required")
    event = next(
        (
            e
            for e in proof["journal"]["events"]
            if e["content_sha256"] == proof["decision_sha256"]
        ),
        None,
    )
    if event is None:
        raise ValueError("knowledge decision missing from journal")
    bound = event["payload"]["bound"]
    if {k: v for k, v in bound.items() if k != "request"} != bindings:
        raise ValueError("knowledge decision bindings differ")
    decision = verify_decision(
        proof,
        trust["tower_key"].encode(),
        kind,
        bound,
        expected_head=trust["trusted_head"],
        scope=trust["scope"],
        outcomes=outcomes,
        now=now or datetime.now(timezone.utc),
    )
    from lightyear_control_tower.kinds import default_registry

    if any(
        not isinstance(decision.get(k), str) or not decision[k].strip()
        for k in default_registry().get(kind).required_fields
    ):
        raise ValueError("required operator decision fields missing")
    return decision


def sealed(value):
    return value.get("evaluation_class") == "sealed-holdout"


def hashed(value):
    return {**value, "content_sha256": digest(value)}
