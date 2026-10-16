"""Real test-Tower signatures, with no production keys or workload execution."""
import copy
import hashlib
import json
import unittest

from tests import test_decision_console_factory as fixtures
from lightyear_control_tower.factory_policy import FactoryDecisions, validate_contract, write_request
from lightyear_control_tower.threshold_conditions import DECISIONS, REPOSITORY, condition_hashes, CONDITIONS


class ThresholdConditionTests(unittest.TestCase):
    setUp = fixtures.FactoryTests.setUp
    contract = fixtures.FactoryTests.contract
    decide = fixtures.FactoryTests.decide
    def test_malformed_proof_details_return_the_refusal_code(self):
        from lightyear_control_tower.threshold_conditions import validate_conditions
        for value in (None, [], {}, {"details": "invalid"}):
            with self.assertRaisesRegex(ValueError, "threshold-conditions-unmet"):
                validate_conditions(value)

    def test_policy_inventory_matches_preserved_decision(self):
        from lightyear_control_tower.threshold_conditions import DECISIONS_SHA256, CONDITIONS
        raw = (REPOSITORY/DECISIONS).read_bytes()
        self.assertEqual(DECISIONS_SHA256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(list(CONDITIONS), json.loads(raw)["scenario_threshold_2"]["conditions"])

    def threshold(self):
        c = self.contract("scenario-threshold-approval")
        review=self.contract('equivalence-review')
        proof,_,_=self.decide(review)
        values=[
            ('docs/factory/b1.json',dict(schema='factory-legacy-twin/1',phase='B1-equivalence-followup',job='POSTTRAN',current_head='b'*40,
                counts={'equivalent (argued, individual review pending)':2},population=2,target_cases=400,target_valid_comparisons=400,target_evidence_gap_ids=[],fresh_sites=483,expected_sites=483)),
            ('docs/factory/reviews.json',dict(schema='threshold-equivalence-reviews/1',program='POSTTRAN',evidence_head='b'*40,
                required_ids=['mutant-1','mutant-2'],claim_scope='twin',proofs=[proof])),
            ('docs/factory/campaign.json',dict(schema='release-evidence-index/2',head='b'*40,conclusion='success',run_id=1,sources=[dict(head='b'*40,run_id=1)])),
            ('docs/factory/keep-or-fix-register.json',dict(schema='factory-keep-or-fix-register/1',defects=[dict(id='registered')]))]
        c['details'].update(effective_condition='unconditional',evidence_head='b'*40,conditions=[])
        for condition,(path,value) in zip(CONDITIONS,values):
            raw=json.dumps(value).encode(); (self.root/path).write_bytes(raw)
            evidence=dict(path=path,sha256=hashlib.sha256(raw).hexdigest(),commit='b'*40)
            c['sources'].append(evidence)
            c['details']['conditions'].append(dict(condition_sha256=hashlib.sha256(condition.encode()).hexdigest(),state='met',evidence=copy.deepcopy(evidence)))
        return c

    def test_unmet_or_omitted_condition_refused_before_signing(self):
        for mode in ("unmet", "missing", "empty", "duplicate", "legacy"):
            c = self.threshold()
            rows = c["details"]["conditions"]
            if mode == "unmet": rows[0].update(state="not-met", evidence=None)
            if mode == "missing": rows.pop()
            if mode == "empty": rows.clear()
            if mode == "duplicate": rows[-1] = copy.deepcopy(rows[0])
            if mode == "legacy": del c["details"]["conditions"]
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "threshold-conditions-unmet"):
                write_request(self.root, c)

    def test_changed_hash_and_forged_source_refused(self):
        for mode in ("hash", "source", "bytes", "commit"):
            c = self.threshold()
            if mode == "hash": c["details"]["conditions"][0]["evidence"]["sha256"] = "f"*64
            if mode == "source":
                c["sources"][1]["sha256"] = "f"*64
                c["details"]["conditions"][0]["evidence"]["sha256"] = "f"*64
            if mode == "bytes": (self.root / 'docs/factory/b1.json').write_text("changed")
            if mode == "commit": c["details"]["conditions"][0]["evidence"]["commit"] = "f"*40
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "threshold-conditions-unmet"):
                validate_contract(c, self.root)

    def test_fully_met_fixture_signs_and_changed_evidence_cannot_be_consumed(self):
        c = self.threshold()
        proof, _, _ = self.decide(c)
        reader = FactoryDecisions(self.service.public_key, proof["journal"]["journal_head_sha256"], evidence_root=self.root)
        reader.verify(proof, c["kind"], c, ("approve",))
        (self.root / 'docs/factory/b1.json').write_text("changed after signing")
        with self.assertRaisesRegex(ValueError, "threshold-conditions-unmet"):
            reader.verify(proof, c["kind"], c, ("approve",))

    def test_wrong_evidence_kind_even_with_matching_hash(self):
        for position in range(4):
            c=self.threshold(); evidence=c['details']['conditions'][position]['evidence']
            raw=b'{"schema":"unrelated/1","success":true}'
            (self.root/evidence['path']).write_bytes(raw)
            evidence['sha256']=hashlib.sha256(raw).hexdigest()
            next(s for s in c['sources'] if s['path']==evidence['path'])['sha256']=evidence['sha256']
            with self.subTest(position=position), self.assertRaisesRegex(ValueError,'threshold-condition-evidence-type'):
                validate_contract(c,self.root)

    def test_foreign_review_cannot_be_used_to_sign_threshold(self):
        c=self.threshold(); evidence=c['details']['conditions'][1]['evidence']
        packet=json.loads((self.root/evidence['path']).read_bytes())
        event=next(e for e in packet['proofs'][0]['journal']['events'] if e['content_sha256']==packet['proofs'][0]['decision_sha256'])
        event['payload']['reason']='forged acceptance'
        raw=json.dumps(packet).encode(); (self.root/evidence['path']).write_bytes(raw)
        evidence['sha256']=hashlib.sha256(raw).hexdigest()
        next(s for s in c['sources'] if s['path']==evidence['path'])['sha256']=evidence['sha256']
        with self.assertRaisesRegex(ValueError,'threshold-condition-evidence-type'): self.decide(c)

    def test_regenerated_request_is_not_signable_and_history_is_preserved(self):
        for date in ("2026-10-14", "2026-10-15"):
            c = json.loads((REPOSITORY / f"docs/factory/scenario-threshold-effective-request-{date}.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "threshold-conditions-unmet"):
                validate_contract(c)
