"""Signed Factory consumer context. Construct only with external trust and backfill."""
from lightyear_control_tower.factory_policy import FactoryDecisions, require
from lightyear_control_tower.decisions import digest


class FactoryAuthority(FactoryDecisions):
    def __init__(self, public_key, trusted_head, backfill_proof, backfill_contract):
        super().__init__(public_key, trusted_head)
        self.verify(backfill_proof, "factory-decision-backfill", backfill_contract, ("accept",))
        self.signed_only = True

    def spend(self, plan, proof, contract, phase=1):
        require(digest({k:v for k,v in plan.items() if k != "content_sha256"}) == plan["content_sha256"], "plan-seal")
        limits = plan["phases"][str(phase)]
        expected = dict(plan_sha256=plan["content_sha256"], client=plan["client"],
            transport=plan.get("transport", plan.get("dispatch")), model=plan["model"],
            calls=limits["model_calls"], input_tokens=limits["input_tokens"], output_tokens=limits["output_tokens"],
            hours=limits["hours"], dollar_cap=limits["api_equivalent_hard_cap_usd"], phase=phase)
        require(contract["details"] == expected, "factory-exact-spend-plan-required")
        self.verify(proof, "model-spend-approval", contract, ("approve",))
        return {"phase1_budget_approved": phase == 1, "phase2_authorized": phase == 2,
                "authority": "signed-factory-decision"}

    def engineering(self, proof, contract, *, commit, seal, window, observer_sha256, class_hashes, caps, now=None):
        details = contract["details"]
        require((details["executable_commit"], details["request_seal"], details["window"]) == (commit, seal, window), "factory-exact-engineering-window-required")
        require((details["observer_sha256"], details["class_hashes"], details["caps"]) == (observer_sha256, class_hashes, caps), "factory-engineering-caps-binding")
        from datetime import datetime, timezone
        at = now or datetime.now(timezone.utc)
        start, end = (datetime.fromisoformat(window[k]) for k in ("start", "end"))
        require(at.tzinfo is not None and start <= at < end, "factory-engineering-window-closed")
        return self.verify(proof, "engineering-run-approval", contract, ("approve",))

    def equivalence(self, proof, contract, mutant_id, claim_scope):
        require(mutant_id in contract["details"]["items"] and contract["details"]["claim_scope"] == claim_scope)
        decision = self.verify(proof, "equivalence-review", contract, ("accept",))
        require(decision["validation"]["items"][mutant_id]["outcome"] == "accept")
        return decision

    def behaviour(self, proof, contract, entry):
        d = contract["details"]
        require(d["entry_id"] == entry["id"] and d["source_sha256"] == entry["source_sha256"], "factory-register-binding")
        return self.verify(proof, "legacy-behaviour-disposition", contract, ("keep", "fix", "investigate"))


def configured_authority(explicit=None):
    """Operator-owned startup setting: absent means migration not activated.

    Once configured, a missing/bad config or unsigned backfill is an error, never
    a fallback. Trust files must be supplied by the operator, outside input packets.
    All model-spend paths (including future B07) must call this before reservation.
    No private key is loaded. The current journal head is supplied out of band.
    """
    import os
    from pathlib import Path
    from lightyear_control_tower.requests import read_json, read_bytes
    location = os.environ.get("LIGHTYEAR_FACTORY_AUTHORITY")
    if not location:
        return explicit
    config = read_json(Path(location))
    require(set(config) == {"schema", "public_key", "trusted_head", "backfill_proof", "backfill_contract"})
    require(config["schema"] == "factory-consumer-trust/1")
    authority = FactoryAuthority(read_bytes(Path(config["public_key"])), config["trusted_head"],
                                 config["backfill_proof"], config["backfill_contract"])
    # A supplied context cannot override the deployment trust setting.
    if explicit is not None:
        require(explicit.public_key == authority.public_key and explicit.head == authority.head,
                "factory-context-override-refused")
    return authority


def proof_contract(proof):
    """Extract an untrusted contract; caller MUST verify it against external trust."""
    event = next((e for e in proof.get("journal", {}).get("events", [])
                  if e.get("content_sha256") == proof.get("decision_sha256")), None)
    require(event is not None, "factory-signed-decision-required")
    return event["payload"]["validation"]["contract"]
