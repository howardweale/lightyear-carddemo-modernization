import copy
import json
from pathlib import Path
import tempfile
import unittest
from lightyear_business_rules.engine import check, issue, replay, issue_assessment, rules_from_mappings
from lightyear_business_rules.carddemo import captured_records
from lightyear_business_rules.strength import assess
from lightyear_business_rules.operators import CardDemoAdapter, anchored_variants
from lightyear_business_rules.catalogue import catalogue, html
from lightyear_business_rules.language import RuleError
from lightyear_mainframe.zos_evidence import Signer, initialize_key
ROOT=Path(__file__).resolve().parents[1]

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rules=rules_from_mappings([json.loads((ROOT/"knowledge/mappings/carddemo-intcalc-executable.json").read_text())])
        self.records,_=captured_records(ROOT/"tests/mainframe/fixtures/intcalc-discriminating-v1")
    def test_diversity_is_applicability_scoped(self):
        result=check(self.rules,self.records)
        rows={r["id"].split(":")[-1]:r for r in result["rules"]}
        self.assertGreater(rows["monthly-interest"]["output_diversity"]["output.amount"],2)
        self.assertEqual(1,rows["zero-rate"]["output_diversity"]["output.amount"])
        self.assertEqual("weak",rows["zero-rate"]["evidence_strength"])
    def test_strength_requires_divergence_not_crash(self):
        self.assertEqual("weak",assess("verified",{"output.x":2},{"killed_failure":1})[0])
        self.assertEqual("discriminating",assess("verified",{"output.x":2},{"killed_divergent":1})[0])
        self.assertEqual("not-assessed",assess("verified",{})[0])
        self.assertEqual("weak",assess("verified",{"output.x":1},{"killed_divergent":1})[0])
    def test_rule_anchors_never_borrow_monthly_mutants(self):
        source=(ROOT/"candidate-java/src/main/java/ai/lightyear/carddemo/service/InterestCalculationService.java").read_text()
        for rule in self.rules:
            variants=list(anchored_variants(source,rule,CardDemoAdapter()))
            self.assertTrue(all(v["rule_id"] == rule["id"] for v in variants))
            if rule["id"].endswith("account-update"):
                self.assertEqual([],variants)
            if not rule["id"].endswith("monthly-interest"):
                self.assertFalse(any(v["name"].startswith("scale-") for v in variants))
        with self.assertRaises(RuleError):
            list(anchored_variants("changed",next(r for r in self.rules if r["id"].endswith("monthly-interest")),CardDemoAdapter()))
    def test_signed_assessment_binds_receipt_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            key=Path(tmp)/"test.pem";initialize_key(key);signer=Signer(key)
            receipt=issue(self.rules,self.records,signer,visibility="public-development")
            report=signer.sign(dict(schema="lightyear-rule-mutations/2",rule_set_sha256=receipt["rule_set_sha256"],receipt_sha256=receipt["content_sha256"],
                rules=[dict(id=r["id"],killed_divergent=0,killed_failure=0) for r in self.rules]))
            assessed=issue_assessment(receipt,report,signer)
            self.assertEqual("passed",replay(assessed,self.rules,self.records,signer.public)["status"])
            self.assertEqual(0,catalogue(self.rules,assessed,signer.public)["verified_total"])
            self.assertIn("verified (weak evidence)",html(catalogue(self.rules,assessed,signer.public)))
            bad=copy.deepcopy(assessed);bad["rules"][0]["evidence_strength"]="discriminating"
            with self.assertRaises(RuleError):replay(bad,self.rules,self.records,signer.public)
    def test_historical_public_evidence_still_replays(self):
        from tools.replay_business_rules_demo import verify
        self.assertEqual("passed",verify()["status"])
