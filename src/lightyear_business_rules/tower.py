"""Prepare a request, never sign an operator decision or grant authority."""
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest, verify_envelope
from lightyear_control_tower.requests import confined, identifier, read_json
from .catalogue import catalogue, bound
from .language import require


def write_request(root, scope, rules, rule, receipt, judge_key, proposer, *, adequacy_report=None):
    require(verify_envelope(receipt, judge_key) and receipt["rule_set_sha256"] == digest(rules), "request-receipt-binding")
    require(rule in rules, "request-rule-not-in-set")
    scope, proposer = identifier(scope), identifier(proposer)
    require(receipt["visibility"] == "public-development", "private-register-needs-authority-owned-adapter")
    require(rule["provenance"] != "model-proposed", "unapproved-rule-proposal")
    summary = next(s for s in receipt["rules"] if s["id"] == rule["id"])
    require(summary["status"] == "contradicted" or rule["legacy_behaviour"] == "defect-candidate", "no-disposition-required")
    bindings = bound(rules, rule, receipt)
    if adequacy_report:
        from lightyear_factory.scenario_policy import verified_assessment
        verified_assessment(receipt,adequacy_report,judge_key)
        bindings['scenario_assessment']=digest(adequacy_report)
    name = "business-rule-"+digest(bindings)[:32]
    root = Path(root).resolve()
    evidence = {}
    artifacts=[("rule_set",rules), ("rule",rule), ("receipt",receipt)]
    if adequacy_report:artifacts.append(('scenario_assessment',adequacy_report))
    for key, value in artifacts:
        relative = f"work/business-rules/{scope}/{name}/{key}.json"
        path = confined(root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as out: out.write(canonical(value))
        evidence[key] = relative
    request = dict(schema="tower-request/1", scope=scope, id=name, kind="business-rule-disposition",
                   bound=bindings, evidence=evidence, workload=rule["workload"], summary="Keep or fix: "+rule["statement"], proposed_by=proposer)
    path = confined(root, f"work/control-tower/requests/{scope}/{name}.json", internal=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out: out.write(canonical(request))
    return request


def inspect(service, item):
    load = lambda key: read_json(confined(service.root, item["evidence"][key]))
    rules, rule, receipt = load("rule_set"), load("rule"), load("receipt")
    adequacy=load('scenario_assessment') if 'scenario_assessment' in item['evidence'] else None
    if adequacy:require(digest(adequacy)==item['bound'].get('scenario_assessment'),'tower-scenario-binding')
    cat = catalogue(rules, receipt, service.qualification_key(),adequacy_report=adequacy)
    require(rule in rules and bound(rules, rule, receipt).items() <= item["bound"].items(), "tower-rule-binding")
    require(any(e["id"] == rule["id"] for e in cat["register"]), "rule-not-in-register")
    return dict(passed=True, rule_id=rule["id"], receipt_sha256=receipt["content_sha256"], operator_review=True)


def read_catalogue(service):
    rows = []
    for item in service.inbox.queue():
        if item.get("kind") != "business-rule-disposition" or item.get("status") == "invalid": continue
        inspect(service, item)
        rules = read_json(confined(service.root,item["evidence"]["rule_set"]))
        receipt = read_json(confined(service.root,item["evidence"]["receipt"]))
        adequacy=read_json(confined(service.root,item['evidence']['scenario_assessment'])) if 'scenario_assessment' in item['evidence'] else None
        rows.append(dict(request_id=item["id"], catalogue=catalogue(rules,receipt,service.qualification_key(),adequacy_report=adequacy)))
    return dict(available=bool(rows), catalogues=rows)
