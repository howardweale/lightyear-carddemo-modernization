"""Offline rule, signature, graph and operator-authority acceptance tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from datetime import timedelta
from fractions import Fraction
from lightyear_business_rules.language import assign, evaluate, pic_type, RuleError
from lightyear_business_rules.engine import check, issue, replay, rules_from_mappings, validate_rules
from lightyear_business_rules.carddemo import captured_records
from lightyear_business_rules.coverage import decisions, coverage
from lightyear_business_rules.catalogue import catalogue, html, dmn, scenarios, disposition
from lightyear_business_rules.mutation import mutants, killed
from lightyear_business_rules.projection import enrich
from lightyear_mainframe.zos_evidence import Signer, initialize_key
from lightyear_control_tower.decisions import canonical, utcnow, DecisionUnauthorized

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    rules = rules_from_mappings([json.loads((ROOT/"knowledge/mappings/carddemo-intcalc.json").read_text())])
    records, _ = captured_records(ROOT/"tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-2026-10-05")
    return rules, records


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.rules, self.records = fixture()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        initialize_key(self.root/"judge.pem")
        self.signer = Signer(self.root/"judge.pem")

    def test_pic_assignment_and_intermediate_precision(self):
        self.assertEqual(dict(kind="decimal",precision=11,scale=2,signed=True),pic_type("S9(09)V99"))
        self.assertEqual(Fraction(-123,100),assign("-1.239",{"pic":"S9(3)V99"}))
        self.assertEqual(Fraction(-124,100),assign("-1.235",{"pic":"S9(3)V99"},"rounded"))
        self.assertEqual("AB  ",assign("AB",{"pic":"X(4)"}))
        for value,pic in [("-1","9(3)"),("1000","9(3)"),("long","X(2)")]:
            with self.assertRaises(RuleError): assign(value,{"pic":pic})
        with self.assertRaises(RuleError): pic_type("ZZ9.99")
        expression={"op":"mul","args":[{"assign":{"number":"1.239"},"type":{"pic":"S9(3)V99"},"rounding":"truncate"},{"number":"10"}]}
        self.assertEqual(Fraction(123,10),evaluate(expression,{}))

    def test_statuses_applicability_private_redaction_and_determinism(self):
        first=check(self.rules,self.records)
        self.assertEqual(canonical(first),canonical(check(self.rules,self.records)))
        self.assertEqual({"verified":8,"untested":2},first["status_counts"])
        records=copy.deepcopy(self.records)
        records[0]["key"]="SECRET-CUSTOMER"
        records[0]["output"]["amount"]="991.23"
        result=check(self.rules,records)
        self.assertNotIn("SECRET-CUSTOMER",json.dumps(result))
        self.assertNotIn("991.23",json.dumps(result))
        self.assertGreater(result["status_counts"]["contradicted"],0)
        del records[0]["input"]["rate"]
        self.assertGreater(check(self.rules,records)["status_counts"]["indeterminate"],0)
        rules=copy.deepcopy(self.rules[:1]);rules[0]["executable"]=None
        self.assertEqual(["no executable form"],check(rules,records)["rules"][0]["reasons"])
        self.assertEqual({"untested":10},check(self.rules,[])["status_counts"])

    def test_first_match_and_else_required(self):
        rule=copy.deepcopy(next(r for r in self.rules if r["id"].endswith("nonzero-rate-emission")))
        rule["executable"]["rows"]=[{"when":{"literal":True},"then":{"literal":False}},{"when":{"literal":True},"then":{"literal":True}},{"else":{"literal":True}}]
        self.assertEqual("contradicted",check([rule],self.records)["rules"][0]["status"])
        rule["executable"]["rows"].pop()
        self.assertEqual("indeterminate",check([rule],self.records)["rules"][0]["status"])

    def test_missing_fields_unsupported_and_bounds_fail_closed(self):
        for expr in ({"python":"print(1)"},{"op":"div","args":[{"number":"1"},{"number":"0"}]},{"number":10**100}):
            with self.assertRaises(RuleError): evaluate(expr,{})
        node={"literal":True}
        for _ in range(40): node={"op":"not","args":[node]}
        with self.assertRaises(RuleError): evaluate(node,{})
        with self.assertRaises(RuleError): validate_rules(self.rules,set())

    def test_signature_replay_tamper_and_exports(self):
        receipt=issue(self.rules,self.records,self.signer,visibility="public-development")
        self.assertEqual("passed",replay(receipt,self.rules,self.records,self.signer.public)["status"])
        changed=copy.deepcopy(receipt);changed["rules"][0]["status"]="contradicted"
        with self.assertRaises(RuleError): replay(changed,self.rules,self.records,self.signer.public)
        records=copy.deepcopy(self.records);records[0]["output"]["amount"]="0.01"
        with self.assertRaises(RuleError): replay(receipt,self.rules,records,self.signer.public)
        cat=catalogue(self.rules,receipt,self.signer.public)
        self.assertTrue(any(e["id"].endswith("source-final-account") for e in cat["register"]))
        self.assertIn("Lightyear",html(cat))
        import xml.etree.ElementTree as ET
        root=ET.fromstring(dmn(self.rules))
        self.assertTrue(root.tag.endswith("definitions"))
        self.assertIn("Given",scenarios(self.rules,self.records,receipt,self.signer.public))
        private=issue(self.rules,self.records,self.signer)
        with self.assertRaises(RuleError): scenarios(self.rules,self.records,private,self.signer.public)

    def test_decision_extraction_ignores_comments_literals_preserves_spans(self):
        source="\n".join(["       PROCEDURE DIVISION.","       MAIN.","           IF A = B", "           EVALUATE A", "             WHEN 1", "           PERFORM", "             VARYING I FROM 1 BY 1 UNTIL I > 9", "           SEARCH TABLE-A", "           AT END", "           INVALID KEY", "      * IF THIS IS A COMMENT", "           DISPLAY 'IF SEARCH'", "           END-IF."])
        points=decisions(source,"P","p.cbl")
        self.assertEqual(["IF","EVALUATE","WHEN","PERFORM VARYING","SEARCH","AT END","INVALID KEY"],[p["construct"] for p in points])
        self.assertEqual((6,7),(points[3]["line_start"],points[3]["line_end"]))
        rule=copy.deepcopy(self.rules[:1]);rule[0]["derived_from"]=[dict(path="p.cbl",line_start=3,line_end=3)]
        result=coverage(rule,points,{"rules":[{"id":rule[0]["id"],"status":"untested"}]})
        self.assertEqual(1,result["programs"]["P"]["explained_count"])
        self.assertEqual(6,len(result["programs"]["P"]["unexplained"]))

    def test_mutation_distinct_and_requires_named_field(self):
        source=(ROOT/"candidate-java/src/main/java/ai/lightyear/carddemo/service/InterestCalculationService.java").read_text()
        variants=list(mutants(source))
        self.assertEqual(7,len({text for _,text in variants}))
        self.assertFalse(killed(dict(status="divergent",fields=["OTHER"]),["TRAN-AMT"]))
        self.assertFalse(killed(dict(status="execution-failure",fields=["TRAN-AMT"]),["TRAN-AMT"]))
        self.assertTrue(killed(dict(status="divergent",fields=["TRAN-AMT"]),["TRAN-AMT"]))

    def test_graph_extension_resolves_inputs_and_preserves_snapshot(self):
        from lightyear_knowledge_graph.model import KnowledgeGraph, load_graph
        from lightyear_knowledge_graph.ontology import business_rules_ontology, ontology_identity
        from lightyear_knowledge_graph.builder import _apply_manifest
        from lightyear_knowledge_graph.validation import validate_graph
        snapshot=load_graph(ROOT/"knowledge/graph.snapshot.json.gz")
        ontology=business_rules_ontology()
        graph=KnowledgeGraph("business-rules-demo",snapshot["sources"],ontology_identity(ontology))
        graph.nodes={n["id"]:copy.deepcopy(n) for n in snapshot["nodes"]}
        graph.edges={e["id"]:copy.deepcopy(e) for e in snapshot["edges"]}
        _apply_manifest(graph,ROOT/"knowledge/mappings/carddemo-intcalc.json")
        _apply_manifest(graph,ROOT/"knowledge/mappings/public-tsql-rules.json")
        self.assertEqual([],validate_graph(graph.to_dict(),ontology))
        validate_rules(self.rules,graph.nodes)
        self.assertEqual("untested",graph.nodes["rule:intcalc:monthly-interest"]["properties"]["status"])

    def test_sequence_neighbors_and_order_are_evidence(self):
        rule=copy.deepcopy(self.rules[0])
        rule["executable"]={"form":"sequence_predicate","when":{"op":"not","args":[{"field":"position.first"}]},
            "condition":{"op":"ne","args":[{"field":"previous.input.account"},{"field":"input.account"}]}}
        rows=self.records[:2]
        self.assertEqual("verified",check([rule],rows)["rules"][0]["status"])
        changed=copy.deepcopy(rows);changed[1]["input"]["account"]=changed[0]["input"]["account"]
        self.assertEqual("contradicted",check([rule],changed)["rules"][0]["status"])

    def test_cli_private_check_replay_and_no_overwrite(self):
        from lightyear_judge.cli import main
        records=self.root/"records.json";records.write_text(json.dumps(self.records))
        key=self.root/"public.pem";key.write_bytes(self.signer.public)
        receipt=self.root/"receipt.json"
        common=["--mapping",str(ROOT/"knowledge/mappings/carddemo-intcalc.json"),"--records",str(records)]
        main(["rule-check",*common,"--judge-key",str(self.root/"judge.pem"),"--output",str(receipt)])
        main(["rule-replay",*common,"--public-key",str(key),"--receipt",str(receipt),"--output",str(self.root/"replay.json")])
        self.assertEqual("private",json.loads(receipt.read_bytes())["visibility"])
        with self.assertRaises(FileExistsError):
            main(["rule-check",*common,"--judge-key",str(self.root/"judge.pem"),"--output",str(receipt)])

    def test_catalogue_rejects_unsigned_decision_and_bad_rule_binding(self):
        receipt=issue(self.rules,self.records,self.signer)
        with self.assertRaises(RuleError):
            catalogue(self.rules,receipt,self.signer.public,decisions={self.rules[0]["id"]:{"outcome":"fix"}})
        changed=copy.deepcopy(self.rules);changed[0]["statement"]="Different source statement"
        with self.assertRaises(RuleError): catalogue(changed,receipt,self.signer.public)
        mutation=dict(schema="lightyear-rule-mutations/1",rule_set_sha256=receipt["rule_set_sha256"],
                      receipt_sha256=receipt["content_sha256"],rules=[])
        with self.assertRaises(RuleError): catalogue(self.rules,receipt,self.signer.public,kill_report=mutation)
        catalogue(self.rules,receipt,self.signer.public,kill_report=self.signer.sign(mutation))

    def test_five_sql_rules_and_metadata_generation(self):
        from lightyear_business_rules.tsql import mapping
        saved=json.loads((ROOT/"knowledge/mappings/public-tsql-rules.json").read_text())
        self.assertEqual(saved,mapping(ROOT))
        rules=rules_from_mappings([saved])
        self.assertEqual(5,len(rules))
        self.assertEqual({"untested":5},check(rules,[])["status_counts"])

    def test_public_only_projection_proposals_quarantined(self):
        receipt=issue(self.rules,self.records,self.signer,visibility="public-development")
        node={"id":"rule:intcalc:monthly-interest","properties":{"statement":"Monthly interest"}}
        result=enrich(node,self.rules,receipt,self.records,self.signer.public,public_lane=True,approved_source="1200")
        self.assertEqual("verified",result["properties"]["rule_status"])
        self.assertNotIn("rule_executable_json",result["properties"]) # zero literal also needs approved source
        with self.assertRaises(RuleError): enrich(node,self.rules,receipt,self.records,self.signer.public,public_lane=False,approved_source="1200 0")
        rules=copy.deepcopy(self.rules);rules[0]["provenance"]="model-proposed"
        cat=catalogue(rules,issue(rules,self.records,self.signer),self.signer.public)
        self.assertNotIn(rules[0]["id"],[e["id"] for e in cat["entries"]])

    def test_named_customer_tower_signed_decision_and_mode(self):
        from lightyear_control_tower.console import ConsoleService, provision
        from lightyear_business_rules.tower import write_request
        from lightyear_control_tower.server import ConsoleAPI
        data=self.root/"data";data.mkdir()
        authority=self.root/"authority/authority.json"
        credential=provision(authority,"business-demo","customer-owner","Named Customer",identity_kind="customer").read_text().strip()
        (authority.parent/"judge.public.pem").write_bytes(self.signer.public)
        (authority.parent/"qualification-trust.json").write_text(json.dumps(dict(scope="business-demo",public_key="judge.public.pem")))
        service=ConsoleService(data,authority)
        self.addCleanup(service.close)
        receipt=issue(self.rules,self.records,self.signer,visibility="public-development")
        rule=next(r for r in self.rules if r["id"].endswith("source-final-account"))
        request=write_request(data,"business-demo",self.rules,rule,receipt,self.signer.public,"customer-owner")
        service.grant_roles("customer-owner",["operator"],reason="Isolated test fixture only")
        token=service.login(credential)["token"]
        item=service.review(token,request["id"])
        payload=dict(item_id=request["id"],bound=item["bound"],outcome="preserve",reason="Public demo only",named_owner="Named Customer",
                     review_after=(utcnow().date()+timedelta(days=2)).isoformat(),previous_decision_sha256=None,request_id=str(uuid.uuid4()))
        with self.assertRaises(DecisionUnauthorized): service.decide(token,payload)
        service.grant_roles("customer-owner",["operator","business-owner"],reason="Isolated test fixture only",workloads=[rule["workload"]])
        token=service.login(credential)["token"]
        service.review(token,request["id"])
        signed=service.decide(token,payload)
        proof=service.proof(token,signed["content_sha256"])
        mode=disposition(self.rules,rule,receipt,proof,service.public_key,proof["journal"]["journal_head_sha256"],"business-demo")
        self.assertEqual("source-faithful",mode["candidate_mode"])
        from lightyear_judge.cli import main
        for name, value in (("records",self.records),("receipt",receipt),("proof",proof)):
            (self.root/(name+".json")).write_text(json.dumps(value),encoding="utf-8")
        (self.root/"judge.public.pem").write_bytes(self.signer.public)
        (self.root/"tower.public.pem").write_bytes(service.public_key)
        main(["rule-mode","--mapping",str(ROOT/"knowledge/mappings/carddemo-intcalc.json"),
              "--records",str(self.root/"records.json"),"--receipt",str(self.root/"receipt.json"),
              "--public-key",str(self.root/"judge.public.pem"),"--proof",str(self.root/"proof.json"),
              "--tower-public-key",str(self.root/"tower.public.pem"),"--tower-head",proof["journal"]["journal_head_sha256"],
              "--tower-scope","business-demo","--rule-id",rule["id"],"--output",str(self.root/"mode.json")])
        self.assertEqual("source-faithful",json.loads((self.root/"mode.json").read_bytes())["candidate_mode"])
        self.assertTrue(ConsoleAPI(service).read("business-rules",token,{})["available"])
        changed=copy.deepcopy(rule);changed["statement"]="Changed"
        with self.assertRaises(RuleError): disposition(self.rules,changed,receipt,proof,service.public_key,proof["journal"]["journal_head_sha256"],"business-demo")


if __name__ == "__main__": unittest.main()
