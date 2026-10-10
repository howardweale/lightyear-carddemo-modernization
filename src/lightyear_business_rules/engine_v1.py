"""Pure rule checking and existing judge-key receipts; no execution/authority."""
from collections import Counter
from hashlib import sha256
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest, verify_envelope
from . import EVALUATOR_VERSION
from .language import RuleError, require, check_form, pic_type

KINDS = {"calculation", "decision", "validation", "data-contract", "control-flow", "side-effect"}


def rules_from_mappings(manifests):
    rows = []
    for manifest in manifests:
        for workload in manifest["workloads"]:
            for original in workload["rules"]:
                row = dict(original)
                for name, value in dict(schema="lightyear-business-rule/1", workload=workload["id"], kind="decision", inputs=[], outputs=[], executable=None,
                        provenance="source-observed" if row.get("confidence") == "observed" else "asserted", legacy_behaviour=None, decision_ref=None).items():
                    row.setdefault(name, value)
                rows.append(row)
    rows.sort(key=lambda r: r["id"])
    validate_rules(rows)
    return rows


def validate_rules(rules, node_ids=None):
    require(isinstance(rules, list) and 0 < len(rules) <= 10000, "rule-set-bound")
    require(all(isinstance(r, dict) and isinstance(r.get("id"), str) for r in rules), "rule-shape")
    require(len({r["id"] for r in rules}) == len(rules), "duplicate-rule-id")
    for rule in rules:
        require(rule.get("schema") == "lightyear-business-rule/1" and rule["id"].startswith("rule:"), "rule-schema")
        require(isinstance(rule.get("workload"), str) and rule["workload"].startswith("workload:"), "rule-workload")
        require(isinstance(rule.get("statement"), str) and 0 < len(rule["statement"]) < 300, "rule-statement")
        require(rule.get("kind") in KINDS and rule.get("provenance") in {"source-observed", "asserted", "model-proposed"}, "rule-kind-or-provenance")
        require(rule.get("legacy_behaviour") in {None, "faithful", "defect-candidate"}, "legacy-behaviour")
        for name in ("inputs", "outputs"):
            require(isinstance(rule.get(name), list) and all(isinstance(n, str) for n in rule[name]), "rule-node-list")
            if node_ids is not None:
                require(set(rule[name]) <= set(node_ids), "rule-node-unresolved")
        for anchor in rule.get("derived_from", []):
            require(type(anchor["line_start"]) is int and type(anchor.get("line_end", anchor["line_start"])) is int and 0 < anchor["line_start"] <= anchor.get("line_end", anchor["line_start"]), "source-lines")
        require(isinstance(rule.get("bindings", {}), dict), "rule-bindings")
        for binding in rule.get("bindings", {}).values():
            require(isinstance(binding, dict) and isinstance(binding.get("node"), str), "binding-shape")
            require(binding["node"] in rule["inputs"] + rule["outputs"], "unbound-field")
            if "pic" in binding.get("type", {}):
                pic_type(binding["type"]["pic"])
                if isinstance(node_ids, dict):
                    node = node_ids[binding["node"]]
                    require(pic_type(node["properties"].get("picture", "")) == pic_type(binding["type"]["pic"]), "binding-pic-mismatch")
        require(rule.get("executable") is None or isinstance(rule["executable"], dict), "executable-shape")


def check(rules, records, *, visibility="private"):
    validate_rules(rules)
    require(visibility in {"public-development", "private"}, "records-visibility")
    require(isinstance(records, list) and len(records) <= 100000, "record-set-bound")
    require(all(isinstance(r, dict) and set(r) <= {"key", "input", "output", "meta"} and "key" in r and isinstance(r["key"], str) and len(r["key"]) <= 256 for r in records), "record-shape")
    require(len({r["key"] for r in records}) == len(records), "duplicate-record-key")
    require(len(canonical(records)) <= 128*1024*1024, "records-byte-bound")
    results = []
    for rule in sorted(rules, key=lambda r: r["id"]):
        row = dict(id=rule["id"], status="untested", applicable_count=0, agree_count=0,
                   disagree_count=0, indeterminate_count=0, first_disagreement=None, reasons=[])
        if rule["executable"] is None:
            row["reasons"] = ["no executable form"]
        else:
            for i, record in enumerate(records):
                context = {**record, "previous": records[i-1] if i else {}, "next": records[i+1] if i+1 < len(records) else {},
                           "position": {"first": i == 0, "last": i+1 == len(records), "index": i}}
                try:
                    result = check_form(rule["executable"], context, rule.get("bindings", {}))
                except (RuleError, KeyError, TypeError, ZeroDivisionError) as exc:
                    row["indeterminate_count"] += 1
                    row["reasons"].append(str(exc) if isinstance(exc, RuleError) else "malformed-or-missing-input")
                    continue
                if result is None:
                    continue
                row["applicable_count"] += 1
                row["agree_count" if result else "disagree_count"] += 1
                if result is False and row["first_disagreement"] is None:
                    detail = dict(record_key=record["key"], fields=rule["outputs"])
                    row["first_disagreement"] = detail if visibility == "public-development" else {"sha256": digest(detail)}
            row["status"] = ("contradicted" if row["disagree_count"] else "indeterminate" if row["indeterminate_count"]
                             else "verified" if row["applicable_count"] else "untested")
        row["reasons"] = sorted(set(row["reasons"]))
        results.append(row)
    return dict(schema="lightyear-rule-verdict/1", evaluator_version=EVALUATOR_VERSION, rule_set_sha256=digest(rules), records_sha256=digest(records),
                visibility=visibility, record_count=len(records), rules=results, status_counts=dict(sorted(Counter(r["status"] for r in results).items())),
                model_calls=0, limitation="Statuses describe only these captured records; no mainframe equivalence claim.")


def implementation_hash():
    # Git may materialize CRLF on Windows; line endings do not alter Python semantics.
    return digest({name: sha256((Path(__file__).parent/name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                   for name in ("__init__.py", "engine.py", "language.py")})


def issue(rules, records, signer, *, visibility="private"):
    return signer.sign({**check(rules, records, visibility=visibility), "evaluator_sha256": implementation_hash()})


def replay(receipt, rules, records, public_key):
    require(verify_envelope(receipt, public_key), "invalid-rule-signature")
    expected = {**check(rules, records, visibility=receipt["visibility"]), "evaluator_sha256": implementation_hash()}
    require({k:v for k,v in receipt.items() if k not in {"signature", "content_sha256"}} == expected, "rule-replay-mismatch")
    return dict(status="passed", receipt_sha256=receipt["content_sha256"], rules=len(rules), model_calls=0)
