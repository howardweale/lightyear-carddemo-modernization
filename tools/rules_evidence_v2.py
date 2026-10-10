"""New signed TEST-authority public runs. No production signing or authority."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from lightyear_mainframe.zos_evidence import initialize_key, Signer
from lightyear_business_rules.engine import rules_from_mappings, issue, issue_assessment, replay
from lightyear_business_rules.carddemo import captured_records
from lightyear_business_rules.catalogue import catalogue, html
from lightyear_business_rules.scoped_mutation import run
ROOT=Path(__file__).resolve().parents[1]

def main(output,jdk):
    output.mkdir(parents=True,exist_ok=False)
    load=lambda p:json.loads(p.read_text(encoding="utf-8"))
    rules=rules_from_mappings([load(ROOT/"knowledge/mappings/carddemo-intcalc-executable.json")])
    summary={}
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);initialize_key(tmp/"test.pem");signer=Signer(tmp/"test.pem")
        (output/"judge-test.public.pem").write_bytes(signer.public)
        for label,fixture in [("old",ROOT/"tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-2026-10-05"),
                              ("new",ROOT/"tests/mainframe/fixtures/intcalc-discriminating-v1")]:
            records,binding=captured_records(fixture)
            original=issue(rules,records,signer,visibility="public-development")
            mutations=signer.sign(run(ROOT,fixture,tmp/label,jdk,rules,original))
            receipt=issue_assessment(original,mutations,signer)
            replay_result=replay(receipt,rules,records,signer.public)
            cat=catalogue(rules,receipt,signer.public)
            for name,value in [("records",records),("binding",binding),("receipt",receipt),("mutations",mutations),("replay",replay_result),("catalogue",cat)]:
                (output/f"{label}-{name}.json").write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")
            (output/f"{label}-catalogue.html").write_text(html(cat),encoding="utf-8")
            summary[label]={k:cat[k] for k in ("verified_total","verified_weak_total","verified_not_assessed_total")}
            summary[label]["rules"]=[dict(id=e["id"],status=e["status"],evidence_strength=e["evidence_strength"],
                killed_divergent=e["mutation"]["killed_divergent"],killed_failure=e["mutation"]["killed_failure"]) for e in cat["entries"]]
    summary.update(schema="public-rule-evidence-v2/1",test_authority_only=True,legacy_execution=False,docker_calls=0,model_calls=0)
    (output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    inventory={p.name:sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}
    (output/"inventory.json").write_text(json.dumps(inventory,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary))
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);p.add_argument("--jdk",type=Path,required=True)
    a=p.parse_args();main(a.output,a.jdk)
