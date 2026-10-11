import copy,tempfile,unittest
from pathlib import Path
from lightyear_mainframe.zos_evidence import Signer,initialize_key
from lightyear_factory.scenario_policy import PROPOSAL,issue,release,assess

class ScenarioPolicyTests(unittest.TestCase):
    def test_signature_binding_approval_and_actual_fields(self):
        with tempfile.TemporaryDirectory() as d:
            key=Path(d)/'test.pem';initialize_key(key);s=Signer(key)
            v=s.sign(dict(verdict='equivalent'))
            a=dict(instrumented=True,decision_outcomes='4/4',legacy_mutants_killed='50/50',
                   coverage_by_class={'business-logic':{'fraction':'4/4'}},
                   systematic_mutation=dict(counts={'killed-divergent':45,'killed-failure':5,'survived':0,'not-compiled':0,'equivalent (argued, listed)':0},eligible_count=50,excluded_equivalents=0,equivalent_dispositions=[],unresolved_survivors=[],not_compiled=[]),
                   distinct_values_per_output_field={'amount':2},uncovered=[])
            r=issue(v,a,['amount'],s)
            self.assertFalse(release(v,r,s.public)['releasable'])
            p=s.sign(dict(schema='scenario-policy-approval/1',verdict_sha256=v['content_sha256'],assessment_sha256=r['content_sha256'],threshold=PROPOSAL))
            self.assertTrue(release(v,r,s.public,p,s.public)['releasable'])
            changed=copy.deepcopy(r);changed['scenario_adequacy']['decision_outcomes']='3/4'
            with self.assertRaisesRegex(ValueError,'binding'):release(v,changed,s.public,p,s.public)
            self.assertIn('compared-field-inventory-incomplete',assess(a,PROPOSAL,['another']))
            self.assertTrue(assess({**a,'uncovered':['not-solved']},PROPOSAL,['amount']))
            self.assertTrue(assess({**a,'legacy_mutants_killed':'0/0'},PROPOSAL,['amount']))
            self.assertIn('malformed-scenario-evidence',assess({**a,'legacy_mutants_killed':'8/8'},PROPOSAL,['amount']))
            fake=copy.deepcopy(a);fake['systematic_mutation']['counts']['survived']=1
            self.assertIn('malformed-scenario-evidence',assess(fake,PROPOSAL,['amount']))

    def test_engineering_cannot_promote(self):
        with tempfile.TemporaryDirectory() as d:
            key=Path(d)/'test.pem';initialize_key(key);s=Signer(key)
            v=s.sign(dict(verdict='equivalent',run_class='engineering'))
            r=issue(v,{},[],s)
            self.assertFalse(release(v,r,s.public)['releasable'])
