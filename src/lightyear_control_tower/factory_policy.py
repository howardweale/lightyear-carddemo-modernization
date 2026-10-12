"""Closed public Factory contracts and verification; never dispatches or signs."""
from hashlib import sha256
import re
from .decisions import canonical, digest, text_field
from .kinds import factory_registry
from .requests import RequestInbox, confined, read_bytes, read_json, identifier, SHA

SCOPE = "factory"
DISCLOSURE = "public-development"
FIELDS = {
    "scenario-threshold-approval": {"policy_sha256", "version", "effective_condition", "compiler_refusals"},
    "io-exception-acceptance": {"source_sha256", "outcome_id", "outcome", "line", "argument_sha256"},
    "equivalence-review": {"packet_sha256", "items", "class_proof_sha256", "reviewer_type", "claim_scope", "dependencies"},
    "legacy-behaviour-disposition": {"entry_id", "source_sha256", "lines", "observed_behaviour_sha256", "dependent_arguments"},
    "twin-human-review": {"sheet_sha256", "source_sha256", "items"},
    "model-spend-approval": {"plan_sha256", "client", "transport", "model", "calls", "input_tokens", "output_tokens", "hours", "dollar_cap", "phase"},
    "engineering-run-approval": {"executable_commit", "request_seal", "observer_sha256", "class_hashes", "window", "caps"},
    "factory-decision-backfill": {"records", "activation", "historical_only"},
}
COMMON = {"schema", "kind", "program", "sources", "details"}


def require(condition, code="factory-contract-refused"):
    if not condition:
        raise ValueError(code)


def validate_contract(value):
    require(isinstance(value, dict) and set(value) == COMMON)
    require(value["schema"] == "factory-contract/1" and value["kind"] in FIELDS)
    require(value["program"] in {"INTCALC", "POSTTRAN", "B06", "B07", "factory"})
    details = value["details"]
    require(isinstance(details, dict) and set(details) == FIELDS[value["kind"]])
    sources = value["sources"]
    require(isinstance(sources, list) and 0 < len(sources) <= 1000)
    paths = []
    for source in sources:
        require(isinstance(source, dict) and set(source) == {"path", "sha256", "commit"})
        require(isinstance(source["path"], str) and re.fullmatch(r"docs/factory/[A-Za-z0-9_./-]+", source["path"]) and not any(p in {"", ".", ".."} for p in source["path"].split("/")))
        require(isinstance(source["sha256"], str) and SHA.fullmatch(source["sha256"]))
        require(isinstance(source["commit"], str) and len(source["commit"]) == 40
                and all(c in "0123456789abcdef" for c in source["commit"]))
        paths.append(source["path"])
    require(len(set(paths)) == len(paths))
    for key, field in details.items():
        if key.endswith("_sha256") and field is not None:
            require(isinstance(field, str) and SHA.fullmatch(field))
    kind = value["kind"]
    if kind in {"equivalence-review", "twin-human-review"}:
        require(isinstance(details["items"], list) and 0 < len(details["items"]) <= 1000)
        require(len(set(details["items"])) == len(details["items"]))
        for item in details["items"]:
            text_field(item, "Review item", 300)
    if kind == "scenario-threshold-approval":
        text_field(details["version"], "Policy version", 100)
        text_field(details["effective_condition"], "Effective condition")
        require(details["compiler_refusals"] == "listed-excluded-not-blockers")
    if kind == "io-exception-acceptance":
        require(type(details["line"]) is int and details["line"] > 0)
        text_field(details["outcome_id"], "Outcome ID", 300)
        text_field(details["outcome"], "Outcome", 100)
    if kind == "equivalence-review":
        require(details["reviewer_type"] in {"human", "AI-assisted"})
        require(details["claim_scope"] in {"twin", "zos-facing"})
        require(isinstance(details["dependencies"], list))
    if kind == "legacy-behaviour-disposition":
        require(isinstance(details["dependent_arguments"], list))
        require(bool(details["lines"]) and all(type(n) is int and n > 0 for n in details["lines"]))
    if kind == "model-spend-approval":
        for name in ("calls", "input_tokens", "output_tokens", "phase"):
            require(type(details[name]) is int and details[name] > 0)
        for name in ("hours", "dollar_cap"):
            require(type(details[name]) in (int, float) and 0 < details[name] < 1000000)
        for name in ("client", "transport", "model"):
            require(bool(details[name]))
    if kind == "engineering-run-approval":
        from datetime import datetime
        commit = details["executable_commit"]
        require(isinstance(commit, str) and len(commit) == 40 and all(c in "0123456789abcdef" for c in commit))
        require(set(details["window"]) == {"start", "end"})
        start, end = [datetime.fromisoformat(details["window"][k]) for k in ("start", "end")]
        require(start.tzinfo is not None and end.tzinfo is not None and start < end)
        require(isinstance(details["request_seal"], str) and SHA.fullmatch(details["request_seal"]))
        require(isinstance(details["caps"], dict) and 0 < len(details["caps"]) <= 30)
        require(all(re.fullmatch(r"[a-z_]+", k) and type(v) is int and v > 0 for k,v in details["caps"].items()))
        require(isinstance(details["class_hashes"], dict) and 0 < len(details["class_hashes"]) <= 100)
        require(all(re.fullmatch(r"[A-Za-z0-9_.$]+", k) and isinstance(v,str) and SHA.fullmatch(v) for k,v in details["class_hashes"].items()))
    if kind == "factory-decision-backfill":
        require(details["historical_only"] is True and details["activation"] == "signed-factory-decisions-only")
        require(isinstance(details["records"], list) and bool(details["records"]))
    for name in ("dependencies", "dependent_arguments"):
        if name in details:
            require(len(details[name]) <= 1000 and all(isinstance(x,str) for x in details[name]))
            require(len(set(details[name])) == len(details[name]))
            for item in details[name]:
                text_field(item, "Dependency", 300)
    # Finite, bounded JSON is enforced by read_json and canonical serialization.
    require(len(canonical(value)) <= 8 * 1024 * 1024)
    return value


def load_contract(root, item):
    require(item["scope"] == SCOPE)
    require(set(item["evidence"]) == {"contract"})
    path = item["evidence"]["contract"]
    require(path.startswith("docs/factory/tower-requests/"))
    raw = read_bytes(confined(root, path))
    require(sha256(raw).hexdigest() == item["bound"]["contract"], "factory-contract-hash")
    value = validate_contract(read_json(confined(root, path)))
    require(value["kind"] == item["kind"])
    require(raw == canonical(value), "factory-contract-canonical")
    for source in value["sources"]:
        require(sha256(read_bytes(confined(root, source["path"]))).hexdigest() == source["sha256"], "factory-source-hash")
    if value["kind"] == "factory-decision-backfill":
        records = value["details"]["records"]
        require(len(records) == len(value["sources"]), "backfill-inventory")
        for row, source in zip(records, value["sources"]):
            require(set(row) == {"path", "original_date", "record"} and row["path"] == source["path"], "backfill-record-binding")
            original = read_json(confined(root, source["path"]))
            require(row["record"] == original and row["original_date"] == original.get("decided_at", original.get("decided_on")), "backfill-original-record-required")
    return value


class FactoryInbox(RequestInbox):
    def item(self, request_id):
        item = super().item(request_id)
        require(set(item["bound"]) == {"contract", "request"})
        value = load_contract(self.root, item)
        require(item.get("workload") == "factory:" + value["program"])
        return item


def write_request(root, contract, *, proposer="factory-engine"):
    """Only prepares unsigned requests. Sources must already be imported public bytes."""
    from .status_export import atomic_new
    value = validate_contract(contract)
    raw = canonical(value)
    fingerprint = sha256(raw).hexdigest()
    relative = "docs/factory/tower-requests/" + fingerprint + ".json"
    destination = confined(root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        require(read_bytes(destination) == raw)
    else:
        atomic_new(destination, value)
    name = "factory-" + fingerprint
    request = dict(schema="tower-request/1", scope=SCOPE, id=name, kind=value["kind"],
        bound={"contract": fingerprint}, evidence={"contract": relative},
        summary=value["kind"] + ": " + value["program"] + "; operator review, not independent attestation",
        proposed_by=identifier(proposer), workload="factory:" + value["program"])
    folder = confined(root, "work/control-tower/requests/factory", internal=True)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + ".json")
    if path.exists():
        require(read_json(path) == request)
    else:
        atomic_new(path, request)
    FactoryInbox(root, SCOPE, factory_registry()).item(name)
    return request


def validate_decision(root, item, payload, events, session):
    contract = load_contract(root, item)
    kind, details = contract["kind"], contract["details"]
    result = dict(schema="factory-validation/1", contract=contract, disclosure=DISCLOSURE,
        operator_review=True, execution_authorized=False)
    if kind in {"equivalence-review", "twin-human-review"}:
        decisions = payload.get("factory_items")
        require(isinstance(decisions, dict) and set(decisions) == set(details["items"]), "factory-all-items-required")
        for row in decisions.values():
            require(set(row) == {"outcome", "reason"} and row["outcome"] in {"accept", "reject", "investigate"})
            text_field(row["reason"], "Item reason")
        require(payload["outcome"] != "accept" or all(r["outcome"] == "accept" for r in decisions.values()))
        result["items"] = decisions
    if kind == "legacy-behaviour-disposition" and payload["outcome"] == "fix":
        require(payload.get("acknowledged_dependencies") == details["dependent_arguments"], "acknowledge-invalidated-arguments")
        result["invalidated_arguments"] = details["dependent_arguments"]
    if kind == "factory-decision-backfill":
        require({"qualification-approver", "campaign-authorizer", "business-owner"} <= set(session["roles"]), "backfill-all-roles-required")
    return result


def verify_validation(decision):
    validation = decision.get("validation", {})
    require(validation.get("schema") == "factory-validation/1" and validation.get("disclosure") == DISCLOSURE)
    contract = validate_contract(validation["contract"])
    require(contract["kind"] == decision["kind"])
    require(sha256(canonical(contract)).hexdigest() == decision["bound"]["contract"])
    if decision["kind"] in {"equivalence-review", "twin-human-review"}:
        items = validation.get("items", {})
        require(set(items) == set(contract["details"]["items"]))
        require(all(set(r) == {"outcome", "reason"} and r["outcome"] in {"accept", "reject", "investigate"}
                    and isinstance(r["reason"], str) and r["reason"].strip() for r in items.values()))
        require(decision["outcome"] != "accept" or all(r["outcome"] == "accept" for r in items.values()))
    if decision["kind"] == "legacy-behaviour-disposition" and decision["outcome"] == "fix":
        require(validation.get("invalidated_arguments") == contract["details"]["dependent_arguments"])
    if decision["kind"] == "factory-decision-backfill":
        require({"qualification-approver", "campaign-authorizer", "business-owner"} <= set(decision["roles_held"]))
    return contract


class FactoryDecisions:
    """Consumers get trust externally; never trust a key/head embedded in evidence."""
    def __init__(self, public_key, trusted_head):
        require(public_key is not None and isinstance(trusted_head, str) and SHA.fullmatch(trusted_head), "factory-trusted-head-required")
        self.public_key, self.head = public_key, trusted_head

    def verify(self, proof, kind, contract, outcomes):
        from .verification import verify_decision, verify_journal
        require(contract["kind"] == kind)
        bound = proof.get("journal", {}).get("events", [])
        event = next((e for e in bound if e.get("content_sha256") == proof.get("decision_sha256")), None)
        require(event is not None, "factory-signed-decision-required")
        expected = dict(event["payload"]["bound"])
        expected["contract"] = sha256(canonical(validate_contract(contract))).hexdigest()
        decision = verify_decision(proof, self.public_key, kind, expected, scope=SCOPE,
            expected_head=self.head, outcomes=outcomes)
        require(decision["validation"]["contract"] == contract)
        if kind == "equivalence-review":
            events = verify_journal(proof["journal"], self.public_key, scope=SCOPE, expected_head=self.head)
            for other in events:
                p = other.get("payload", {})
                if other.get("kind") == "tower_decision" and p.get("kind") == "legacy-behaviour-disposition" and p.get("outcome") == "fix":
                    previous = verify_validation(p)
                    if previous["details"]["entry_id"] in contract["details"]["dependencies"] and other["sequence"] > event["sequence"]:
                        raise ValueError("factory-equivalence-invalidated")
        return decision
