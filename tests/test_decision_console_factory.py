import copy
import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from lightyear_control_tower.console import ConsoleService, provision
from lightyear_control_tower.decisions import canonical, DecisionUnauthorized
from lightyear_control_tower.factory_policy import (FIELDS, FactoryDecisions, write_request,
    validate_contract)
from lightyear_control_tower.kinds import default_registry, factory_registry
from lightyear_control_tower.verification import DecisionVerificationError


class FactoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.root.mkdir()
        self.authority = Path(self.temp.name) / "authority/authority.json"
        credential = provision(self.authority, "factory", "howard", "Howard").read_text().strip()
        self.service = ConsoleService(self.root, self.authority)
        self.addCleanup(self.service.close)
        self.service.grant_roles("howard", ["operator", "qualification-approver", "business-owner", "campaign-authorizer"],
            reason="Test fixture only", workloads=["factory:POSTTRAN", "factory:factory"])
        self.token = self.service.login(credential)["token"]
        self.source = self.root / "docs/factory/public.json"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(canonical({"decided_on":"2026-10-11","public": True}))

    def contract(self, kind):
        d = {key: "value" for key in FIELDS[kind]}
        for key in d:
            if key.endswith("_sha256"):
                d[key] = "a" * 64
        d.update({k:v for k,v in dict(items=["mutant-1", "mutant-2"],
            class_proof_sha256=None, reviewer_type="human", claim_scope="twin", dependencies=[],
            dependent_arguments=["mutant-1"], lines=[109], line=189,
            calls=3,input_tokens=750000,output_tokens=192000,hours=2,dollar_cap=36,phase=1,
            executable_commit="b"*40,request_seal="c"*64,class_hashes={"A":"d"*64},caps={"seconds":60},
            window={"start":"2026-10-13T16:00:00+00:00","end":"2026-10-13T19:00:00+00:00"},
            records=[{"path":"docs/factory/public.json","original_date":"2026-10-11","record":{"decided_on":"2026-10-11","public":True}}], compiler_refusals="listed-excluded-not-blockers",
            activation="signed-factory-decisions-only",historical_only=True).items() if k in d})
        return dict(schema="factory-contract/1",kind=kind,program="POSTTRAN",
            sources=[dict(path="docs/factory/public.json",sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),commit="b"*40)],details=d)

    def decide(self, contract, outcome=None):
        request = write_request(self.root, contract)
        item = self.service.review(self.token, request["id"])
        payload = dict(item_id=item["id"],bound=item["bound"],
            outcome=outcome or factory_registry().get(contract["kind"]).outcomes[0],reason="Reviewed public fixture",
            previous_decision_sha256=(item["latest_decision"] or {}).get("content_sha256"),request_id=str(uuid.uuid4()))
        if "items" in contract["details"]:
            payload["factory_items"] = {i:dict(outcome="accept",reason="Source argument checked") for i in contract["details"]["items"]}
        if outcome == "fix":
            payload["acknowledged_dependencies"] = contract["details"]["dependent_arguments"]
        event = self.service.decide(self.token, payload)
        proof = self.service.proof(self.token, event["content_sha256"])
        return proof, item, payload

    def test_every_kind_roundtrip_role_tamper_stale_and_scope(self):
        for kind in factory_registry().names():
            with self.subTest(kind=kind):
                contract = self.contract(kind)
                proof, item, payload = self.decide(contract)
                reader = FactoryDecisions(self.service.public_key, proof["journal"]["journal_head_sha256"])
                decision = reader.verify(proof, kind, contract, factory_registry().get(kind).outcomes)
                self.assertEqual("Reviewed public fixture", decision["reason"])
                damaged = copy.deepcopy(proof); damaged["journal"]["events"][-1]["payload"]["reason"] = "tampered"
                with self.assertRaises(ValueError): reader.verify(damaged, kind, contract, factory_registry().get(kind).outcomes)
                with self.assertRaises(ValueError): FactoryDecisions(self.service.public_key,"f"*64).verify(proof,kind,contract, factory_registry().get(kind).outcomes)
                foreign = copy.deepcopy(proof); foreign["journal"]["scope"] = "ms94-b06"
                with self.assertRaises(ValueError): reader.verify(foreign,kind,contract, factory_registry().get(kind).outcomes)
                credential = self.service.add_identity("reader-"+kind, "Read only")
                self.service.grant_roles("reader-"+kind,["operator"],reason="No approving role")
                token = self.service.login(credential)["token"]
                with self.assertRaises(DecisionUnauthorized): self.service.decide(token,payload)

    def test_default_and_intake_registries_unchanged(self):
        from lightyear_control_tower.carddemo_policy import registry
        self.assertEqual(4,len(registry().names()))
        self.assertFalse(set(factory_registry().names()) & set(default_registry().names()))

    def test_hash_and_scope_boundaries(self):
        contract=self.contract("model-spend-approval")
        request=write_request(self.root,contract)
        self.assertEqual(request,write_request(self.root,contract))
        self.source.write_text("changed")
        with self.assertRaises(ValueError): self.service.inbox.item(request["id"])
        contract["sources"][0]["path"]="../private/key.json"
        with self.assertRaises(ValueError):validate_contract(contract)

    def test_per_item_review_required(self):
        contract=self.contract("equivalence-review")
        request=write_request(self.root,contract);item=self.service.review(self.token,request["id"])
        with self.assertRaises(ValueError):
            self.service.decide(self.token,dict(item_id=item["id"],bound=item["bound"],outcome="accept",reason="No item decisions",request_id=str(uuid.uuid4())))

    def test_fix_invalidates_earlier_equivalence(self):
        contract=self.contract("equivalence-review");contract["details"]["dependencies"]=["value"]
        proof,_,_=self.decide(contract)
        self.decide(self.contract("legacy-behaviour-disposition"),"fix")
        proof=self.service.proof(self.token,proof["decision_sha256"])
        with self.assertRaisesRegex(ValueError,"invalidated"):
            FactoryDecisions(self.service.public_key,proof["journal"]["journal_head_sha256"]).verify(proof,"equivalence-review",contract,("accept",))

    def test_wrong_plan_and_unsigned_refused(self):
        contract=self.contract("model-spend-approval");proof,_,_=self.decide(contract)
        reader=FactoryDecisions(self.service.public_key,proof["journal"]["journal_head_sha256"])
        changed=copy.deepcopy(contract);changed["details"]["plan_sha256"]="f"*64
        with self.assertRaises(ValueError):reader.verify(proof,"model-spend-approval",changed,("approve",))
        with self.assertRaises(ValueError):reader.verify({"human_answer":"Approve Phase 1 budget"},"model-spend-approval",contract,("approve",))

    def test_configured_activation_refuses_literal_and_bad_config(self):
        from unittest.mock import patch
        from lightyear_factory.posttran_preflight import verify_approval
        from lightyear_factory.tower_authority import configured_authority
        b = self.contract("factory-decision-backfill")
        proof,_,_ = self.decide(b)
        public = Path(self.temp.name)/"public.pem"
        public.write_bytes(self.service.public_key)
        config = Path(self.temp.name)/"consumer.json"
        config.write_bytes(canonical(dict(schema="factory-consumer-trust/1",public_key=str(public),
            trusted_head=proof["journal"]["journal_head_sha256"],backfill_proof=proof,backfill_contract=b)))
        with patch.dict("os.environ", {"LIGHTYEAR_FACTORY_AUTHORITY":str(config)}):
            self.assertTrue(configured_authority().signed_only)
            with self.assertRaisesRegex(ValueError,"signed-decision"):
                verify_approval({}, {"human_answer":"Approve Phase 1 budget"})
            config.write_text("{}")
            with self.assertRaises(ValueError): configured_authority()

    def test_backfill_record_bytes_cannot_be_changed(self):
        b = self.contract("factory-decision-backfill")
        b["details"]["records"][0]["record"]["public"] = False
        with self.assertRaisesRegex(ValueError,"original-record"):
            write_request(self.root,b)

    def test_committed_backfill_complete_and_unchanged(self):
        from lightyear_control_tower.factory_import import historical_contract
        repository=Path(__file__).resolve().parents[1]
        b=json.loads((repository/"docs/factory/tower-backfill-request-2026-10-12.json").read_bytes())
        import subprocess
        head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repository,text=True).strip()
        current=historical_contract(repository,head)
        for source in current["sources"]: source["commit"]=b["sources"][0]["commit"]
        self.assertEqual(b,current)

    def test_engineering_consumer_checks_all_limits(self):
        from lightyear_factory.tower_authority import FactoryAuthority
        b=self.contract("factory-decision-backfill");bp,_,_=self.decide(b)
        c=self.contract("engineering-run-approval");p,_,_=self.decide(c)
        bp=self.service.proof(self.token,bp["decision_sha256"])
        authority=FactoryAuthority(self.service.public_key,p["journal"]["journal_head_sha256"],bp,b)
        d=c["details"]
        args=dict(commit=d["executable_commit"],seal=d["request_seal"],window=d["window"],
                  observer_sha256=d["observer_sha256"],class_hashes=d["class_hashes"],caps=d["caps"])
        authority.engineering(p,c,**args)
        with self.assertRaisesRegex(ValueError,"caps-binding"):
            authority.engineering(p,c,**{**args,"caps":{"seconds":61}})


if __name__ == "__main__":
    unittest.main()
