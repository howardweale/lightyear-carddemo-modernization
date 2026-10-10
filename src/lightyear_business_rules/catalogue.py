"""Receipt-backed exports. No private record values or unapproved proposals."""
from html import escape
import json
import xml.etree.ElementTree as ET
from lightyear_control_tower.decisions import digest, verify_envelope
from lightyear_control_tower.verification import verify_decision
from .language import require


def bound(rules, rule, receipt):
    return dict(rule_set=digest(rules), rule=digest(rule), receipt=digest(receipt))


def disposition(rules, rule, receipt, proof, tower_key, head, scope, *, now=None):
    require(bool(head) and bool(scope), "fresh-tower-head-and-scope-required")
    expected = bound(rules, rule, receipt)
    event = next(e for e in proof["journal"]["events"] if e["content_sha256"] == proof["decision_sha256"])
    actual = event["payload"]["bound"]
    require(set(actual) == set(expected) | {"request"} and all(actual[k] == v for k,v in expected.items()), "disposition-bindings")
    decision = verify_decision(proof, tower_key, "business-rule-disposition", actual,
                               expected_head=head, scope=scope, now=now)
    outcome = decision["outcome"]
    corrected = "intended" if rule["id"] == "rule:intcalc:source-final-account" else "corrected"
    return dict(decision_sha256=proof["decision_sha256"], outcome=outcome,
                candidate_mode={"preserve": "source-faithful", "fix": corrected, "investigate": "blocked"}[outcome])


def catalogue(rules, receipt, judge_key, *, kill_report=None, decisions=None, tower_key=None, tower_head=None, tower_scope=None):
    require(verify_envelope(receipt, judge_key) and receipt["rule_set_sha256"] == digest(rules), "catalogue-receipt-binding")
    require(receipt.get("schema") in {"lightyear-rule-verdict/1", "lightyear-rule-verdict/2"}, "catalogue-receipt-schema")
    status = {r["id"]: r for r in receipt["rules"]}
    require(set(status) == {r["id"] for r in rules}, "catalogue-rule-set")
    kill_report = kill_report or receipt.get("mutation_assessment")
    if kill_report:
        require(verify_envelope(kill_report, judge_key), "mutation-signature")
        require(kill_report["rule_set_sha256"] == digest(rules) and kill_report["receipt_sha256"] == receipt.get("original_receipt", receipt)["content_sha256"], "mutation-binding")
    kills = {r["id"]: r for r in (kill_report or {}).get("rules", [])}
    entries = []
    for rule in rules:
        # Proposals are quarantined until a separate verified promotion into a
        # reviewed mapping. A status alone never approves their source provenance.
        if rule["provenance"] == "model-proposed":
            continue
        s = dict(status[rule["id"]])
        from .strength import assess, display
        mutation = kills.get(rule["id"]) if (kill_report or {}).get("schema") == "lightyear-rule-mutations/2" else None
        strength, reason = assess(s["status"], s.get("output_diversity", {}), mutation)
        s.update(evidence_strength=strength, evidence_strength_reason=reason,
                 display_status=display(s["status"], strength))
        decision = None
        if (decisions or {}).get(rule["id"]):
            decision = disposition(rules, rule, receipt, decisions[rule["id"]], tower_key, tower_head, tower_scope)
        entries.append(dict(id=rule["id"], statement=rule["statement"], source=rule["derived_from"],
            **{k:v for k,v in s.items() if k != "id"}, legacy_behaviour=rule["legacy_behaviour"],
            receipt_sha256=receipt["content_sha256"], mutation=kills.get(rule["id"]),
            decision=decision))
    return dict(schema="lightyear-rule-catalogue/1", brand="Lightyear", rule_set_sha256=digest(rules),
                receipt_sha256=receipt["content_sha256"], entries=entries,
                register=[e for e in entries if e["status"] == "contradicted" or e["legacy_behaviour"] == "defect-candidate"],
                verified_total=sum(e["status"] == "verified" and e["evidence_strength"] == "discriminating" for e in entries),
                verified_weak_total=sum(e["status"] == "verified" and e["evidence_strength"] == "weak" for e in entries),
                verified_not_assessed_total=sum(e["status"] == "verified" and e["evidence_strength"] == "not-assessed" for e in entries),
                limitation=receipt["limitation"])


def html(payload):
    rows = []
    if payload.get("test_authority_only"):
        payload = {**payload, "limitation": "TEST AUTHORITY ONLY: no production/customer decision. " + payload["limitation"]}
    for e in payload["entries"]:
        rows.append("<tr>" + "".join("<td>"+escape(str(e[k]))+"</td>" for k in ("id", "statement", "display_status", "applicable_count", "disagree_count", "receipt_sha256")) + "</tr>")
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Lightyear | Verified business rules</title><style>body{font:16px system-ui;margin:2em;color:#17334c}table{border-collapse:collapse}td,th{padding:.5em;border:1px solid #ccd;overflow-wrap:anywhere}th{text-align:left}</style><h1>Lightyear | Business rules</h1><p>'+escape(payload["limitation"])+"</p><table><thead><tr><th>Rule</th><th>Statement</th><th>Status</th><th>Applicable</th><th>Disagree</th><th>Receipt SHA-256</th></tr></thead><tbody>"+"".join(rows)+"</tbody></table><h2>Keep or fix</h2><pre>"+escape(json.dumps(payload["register"], indent=2))+"</pre></html>"


def _feel(node):
    if "literal" in node:
        return json.dumps(node["literal"])
    if "number" in node:
        from .language import number
        number(node["number"])
        return str(node["number"])
    if "field" in node:
        from .language import field
        import re
        require(bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", node["field"])), "dmn-field")
        return node["field"].replace(".", "_").replace("-", "_")
    operators = {"eq": "=", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">=", "add": "+", "sub": "-", "mul": "*", "div": "/", "and": "and", "or": "or"}
    op, args = node.get("op"), node.get("args", [])
    if op == "not" and len(args) == 1:
        return "not("+_feel(args[0])+")"
    require(op in operators and len(args) == 2, "dmn-unsupported-expression")
    return "("+_feel(args[0])+" "+operators[op]+" "+_feel(args[1])+")"


def dmn(rules):
    """DMN 1.4 FIRST tables. Boolean inputs explicitly retain applicability."""
    ns = "https://www.omg.org/spec/DMN/20211108/MODEL/"
    ET.register_namespace("", ns)
    el = lambda name: "{"+ns+"}"+name
    root = ET.Element(el("definitions"), id="lightyear_rules", name="Lightyear rules", namespace="urn:lightyear:rules")
    for index, rule in enumerate(rules):
        form = rule.get("executable") or {}
        if rule["provenance"] == "model-proposed" or form.get("form") != "decision_table": continue
        def fields(value):
            if isinstance(value, dict):
                for k,v in value.items():
                    if k == "field": yield v
                    else: yield from fields(v)
            elif isinstance(value, list):
                for v in value: yield from fields(v)
        paths = sorted(set(fields(form)))
        names = [p.replace(".", "_").replace("-", "_") for p in paths]
        require(len(set(names)) == len(names), "dmn-field-name-collision")
        for i, (path, name) in enumerate(zip(paths, names)):
            data = ET.SubElement(root, el("inputData"), id=f"data_{index}_{i}", name=name)
            type_spec = rule.get("bindings", {}).get(path, {}).get("type", {})
            type_ref = "number" if "pic" in type_spec and "9" in type_spec["pic"] else "Any"
            ET.SubElement(data, el("variable"), name=name, typeRef=type_ref)
        decision = ET.SubElement(root, el("decision"), id=f"decision_{index}", name=rule["id"])
        for i in range(len(paths)):
            req = ET.SubElement(decision, el("informationRequirement"))
            ET.SubElement(req, el("requiredInput"), href=f"#data_{index}_{i}")
        table = ET.SubElement(decision, el("decisionTable"), id=f"table_{index}", hitPolicy="FIRST")
        conditions = [form["when"]] + [r["when"] for r in form["rows"][:-1]]
        for i, condition in enumerate(conditions):
            inp = ET.SubElement(table, el("input"), id=f"input_{index}_{i}")
            exp = ET.SubElement(inp, el("inputExpression"), typeRef="boolean")
            ET.SubElement(exp, el("text")).text = _feel(condition)
        ET.SubElement(table, el("output"), name=form["output"].replace(".", "_"))
        for i, row in enumerate(form["rows"]):
            entry = ET.SubElement(table, el("rule"), id=f"row_{index}_{i}")
            for j in range(len(conditions)):
                ET.SubElement(ET.SubElement(entry, el("inputEntry")), el("text")).text = "true" if j == 0 or j == i+1 else "-"
            ET.SubElement(ET.SubElement(entry, el("outputEntry")), el("text")).text = _feel(row.get("then", row.get("else")))
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def scenarios(rules, records, receipt, key):
    from .engine import replay
    replay(receipt, rules, records, key)
    require(receipt["visibility"] == "public-development", "private-scenarios-refused")
    return "\n\n".join("Scenario: "+r["key"]+"\n  Given public captured inputs "+json.dumps(r["input"], sort_keys=True)+
        "\n  When the recorded implementation runs\n  Then its recorded output is "+json.dumps(r["output"], sort_keys=True) for r in records)
