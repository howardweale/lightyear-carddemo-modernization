"""Replay the published PUBLIC, test-authority-only acceptance fixture offline."""
from datetime import datetime
import json
from pathlib import Path
from hashlib import sha256
from lightyear_business_rules.engine import rules_from_mappings, replay
from lightyear_business_rules.catalogue import catalogue, disposition
from lightyear_control_tower.decisions import verify_envelope

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    evidence = root / "docs/business-rules/evidence"
    read = lambda p: json.loads(p.read_text(encoding="utf-8"))
    inventory = read(evidence / "inventory.json")
    for name, expected in inventory.items():
        assert Path(name).name == name
        assert sha256((evidence/name).read_bytes()).hexdigest() == expected, name
    key = (evidence/"judge-test.public.pem").read_bytes()
    rules = rules_from_mappings([read(root/"knowledge/mappings/carddemo-intcalc-executable.json")])
    receipt = read(evidence/"intcalc-receipt.json")
    replay(receipt, rules, read(evidence/"intcalc-records.json"), key)
    mutations = read(evidence/"mutations.json")
    assert verify_envelope(mutations, key)
    cat = catalogue(rules, receipt, key, kill_report=mutations)
    assert cat["verified_total"] == 0
    assert cat["verified_not_assessed_total"] == 8
    assert all(r["generated"] > 0 for r in mutations["rules"])
    monthly = next(r for r in mutations["rules"] if r["id"].endswith("monthly-interest"))
    assert next(m for m in monthly["mutants"] if m["name"] == "one-cent-smoke")["killed"]
    proof = read(evidence/"tower-test-proof.json")
    event = next(e for e in proof["journal"]["events"] if e["content_sha256"] == proof["decision_sha256"])
    rule = next(r for r in rules if r["id"].endswith("source-final-account"))
    # Historical fixture verification, NOT fresh production authorization.
    disposition(rules, rule, receipt, proof, (evidence/"tower-test.public.pem").read_bytes(),
                proof["journal"]["journal_head_sha256"], "business-rules-demo",
                now=datetime.fromisoformat(event["occurred_at"]))
    sql = rules_from_mappings([read(root/"knowledge/mappings/public-tsql-rules.json")])
    for variant, status in (("source", "verified"), ("correct", "verified"), ("wrong", "contradicted")):
        signed = read(evidence/f"tsql-{variant}-receipt.json")
        replay(signed, sql, read(evidence/f"tsql-{variant}-records.json"), key)
        assert signed["status_counts"] == {status: 5}
    return dict(status="passed", receipts=4, mutation_signature=True, historical_test_tower=True,
                production_authorization=False, docker_calls=0, model_calls=0)


if __name__ == "__main__":
    print(json.dumps(verify()))
