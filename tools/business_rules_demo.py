"""Reproducible offline public demo. Temporary TEST authority, never real approval.

Writes new output directories only. No Docker, databases, models or network.
"""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import uuid
from lightyear_control_tower.decisions import utcnow, digest
from lightyear_mainframe.zos_evidence import initialize_key, Signer
from lightyear_business_rules.engine import rules_from_mappings, issue, replay
from lightyear_business_rules.carddemo import captured_records
from lightyear_business_rules.catalogue import catalogue, html, dmn, scenarios, disposition
from lightyear_business_rules.coverage import decisions, coverage
from lightyear_business_rules.mutation import run as mutate
from lightyear_business_rules.tower import write_request
from lightyear_business_rules.tsql import capture_records

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    with path.open("x",encoding="utf-8") as f:
        json.dump(value,f,indent=2);f.write("\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--jdk",type=Path,required=True)
    parser.add_argument("--public-tsql-captures",type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    load=lambda p:json.loads(p.read_text(encoding="utf-8"))
    rules=rules_from_mappings([load(ROOT/"knowledge/mappings/carddemo-intcalc-executable.json")])
    records,binding=captured_records(ROOT/"tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-2026-10-05")
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp)
        initialize_key(temp/"judge.pem")
        signer=Signer(temp/"judge.pem")
        (args.output/"judge-test.public.pem").write_bytes(signer.public)
        receipt=issue(rules,records,signer,visibility="public-development")
        write(args.output/"intcalc-records.json",records)
        write(args.output/"intcalc-capture-binding.json",binding)
        write(args.output/"intcalc-receipt.json",receipt)
        write(args.output/"intcalc-replay.json",replay(receipt,rules,records,signer.public))
        kill=signer.sign(mutate(ROOT,ROOT/"tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-2026-10-05",temp/"mutants",args.jdk,rules,receipt))
        write(args.output/"mutations.json",kill)
        point=decisions((ROOT/"spec/mainframe/public-source/CBACT04C.cbl").read_text(),"CBACT04C","app/cbl/CBACT04C.cbl")
        write(args.output/"coverage.json",coverage(rules,point,receipt))
        # Fixture-only signed decision demonstrates existing Tower authorization.
        from lightyear_control_tower.console import ConsoleService,provision
        data=temp/"data";data.mkdir()
        authority=temp/"authority/authority.json"
        credential=provision(authority,"business-rules-demo","demo-customer","DEMO customer approver",identity_kind="customer").read_text().strip()
        (authority.parent/"judge.public.pem").write_bytes(signer.public)
        write(authority.parent/"qualification-trust.json",dict(scope="business-rules-demo",public_key="judge.public.pem"))
        service=ConsoleService(data,authority)
        try:
            rule=next(r for r in rules if r["id"].endswith("source-final-account"))
            request=write_request(data,service.scope,rules,rule,receipt,signer.public,"demo-customer")
            service.grant_roles("demo-customer",["operator","business-owner"],reason="Temporary acceptance fixture only",workloads=[rule["workload"]])
            token=service.login(credential)["token"]
            item=service.review(token,request["id"])
            event=service.decide(token,dict(item_id=request["id"],bound=item["bound"],outcome="preserve",
                reason="TEST FIXTURE: proves gate only; does not authorize customer or production behaviour",named_owner="DEMO customer approver",
                review_after=(utcnow().date()+timedelta(days=5)).isoformat(),previous_decision_sha256=None,request_id=str(uuid.uuid4())))
            proof=service.proof(token,event["content_sha256"])
            decision=disposition(rules,rule,receipt,proof,service.public_key,proof["journal"]["journal_head_sha256"],service.scope)
            write(args.output/"tower-test-proof.json",proof)
            (args.output/"tower-test.public.pem").write_bytes(service.public_key)
        finally: service.close()
        cat=catalogue(rules,receipt,signer.public,kill_report=kill,decisions={rule["id"]:proof},
                      tower_key=service.public_key,tower_head=proof["journal"]["journal_head_sha256"],tower_scope="business-rules-demo")
        cat["test_authority_only"]=True
        write(args.output/"catalogue.json",cat)
        (args.output/"catalogue.html").write_text(html(cat),encoding="utf-8")
        (args.output/"rules.dmn").write_text(dmn(rules),encoding="utf-8")
        (args.output/"scenarios.feature").write_text(scenarios(rules,records,receipt,signer.public),encoding="utf-8")
        sql_rules=rules_from_mappings([load(ROOT/"knowledge/mappings/public-tsql-rules.json")])
        sql_records,sql_binding=capture_records(args.public_tsql_captures,ROOT,
            "f5bdd5002b137b56f6dd315e4746d9ba336ec14b50f64387811826b3a1cb01f7",
            "7ec005f292917b0bc4bd478b024eacb9a88bbeb1d5d6437bce341ea25ec62dce")
        write(args.output/"tsql-binding.json",sql_binding)
        sql_summary={}
        for variant,rows in sql_records.items():
            signed=issue(sql_rules,rows,signer,visibility="public-development")
            write(args.output/f"tsql-{variant}-records.json",rows)
            write(args.output/f"tsql-{variant}-receipt.json",signed)
            replay(signed,sql_rules,rows,signer.public)
            sql_summary[variant]=signed["status_counts"]
        summary=dict(schema="lightyear-business-rules-demo/1",intcalc=receipt["status_counts"],tsql=sql_summary,
            receipt_sha256=receipt["content_sha256"],ruleset_sha256=digest(rules),model_calls=0,docker_calls=0,
            qualification_credit=False,test_authority_only=True,
            limitations=["INTCALC inputs/outputs are public synthetic rehearsal records.",
              "Tower decision uses a temporary demo customer and is not Howard's production decision.",
              "SQL results authenticate historical public native captures; no new native run."])
        write(args.output/"summary.json",summary)
        print(json.dumps(summary))


if __name__ == "__main__":main()
