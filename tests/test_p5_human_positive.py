"""CI-only record negatives. Synthetic dictionaries are never signed fixtures."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch
from lightyear_factory.contracts import canonical_hash
from tools.ci.p5_human_positive import main, validate_positive_records


class PositivePublicRecordTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.admission=dict(schema='factory-human-drill-context-admission/1', status='passed',
            work_order_sha256='a'*64, stub_only=True, credentials_issued=False, secrets_leased=False)
        self.seal(self.admission)
        self.receipt=dict(run_id='drill-public', status='passed', attempts=0, changed_paths=[],
            work_order_sha256='a'*64, initial_snapshot_sha256='b'*64, final_snapshot_sha256='b'*64,
            verification=dict(status='passed', gates=[dict(status='passed', output_sha256='c'*64)]),
            execution_security=dict(production_ready=False,
                admission_receipt_sha256=self.admission['content_sha256'], gate_execution_sha256=['d'*64]))
        self.seal(self.receipt)
        self.provenance=dict(schema='factory-human-drill-controller-provenance/1',
            status='complete-public-trace', controller_origin_verified=True, output_plan_complete=True,
            receipt_sha256=self.receipt['content_sha256'], completed_public_calls=1,
            unfinished_public_calls=0, accounted_calls=1, external_model_calls=0, signatures_created=0,
            production_qualified=False, qualifies_for_factory_receipt=False,
            gaps=['full-production-build-receipt-route-not-integrated'])
        self.seal(self.provenance)
        self.dispatch=dict(schema='factory-human-drill-dispatch/1', run_id='drill-public',
            controller_status='passed', controller_raised_refusal=False,
            receipt_sha256=self.receipt['content_sha256'], provenance_sha256=self.provenance['content_sha256'],
            external_model_calls=0, signatures_created=0, production_qualified=False,
            qualifies_for_factory_receipt=False, gaps=['full-production-build-receipt-route-not-integrated'])
        self.seal(self.dispatch)

    def seal(self, value):
        value['content_sha256']=canonical_hash(value, {'content_sha256'})

    def reseal(self):
        self.seal(self.admission)
        self.receipt['execution_security']['admission_receipt_sha256']=self.admission['content_sha256']
        self.seal(self.receipt)
        self.provenance['receipt_sha256']=self.receipt['content_sha256']; self.seal(self.provenance)
        self.dispatch['receipt_sha256']=self.receipt['content_sha256']
        self.dispatch['provenance_sha256']=self.provenance['content_sha256']; self.seal(self.dispatch)

    def check(self):
        return validate_positive_records(self.dispatch,self.provenance,self.receipt,self.admission)

    def test_synthetic_relations_grant_no_authority_or_production_qualification(self):
        result=self.check()
        self.assertTrue(result['retained_relationships_verified'])
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['production_qualified'])
        self.assertFalse(result['qualifies_for_factory_receipt'])

    def test_blocked_controller_cannot_become_positive_by_rehashing(self):
        self.receipt['status']=self.dispatch['controller_status']='blocked'; self.reseal()
        with self.assertRaisesRegex(ValueError,'positive-controller-did-not-pass'): self.check()

    def test_missing_oci_gate_evidence_and_failed_gate_refuse(self):
        original=deepcopy(self.receipt)
        for field in ('gate_evidence','failed_gate','no_gate'):
            self.receipt=deepcopy(original)
            if field=='gate_evidence': self.receipt['execution_security']['gate_execution_sha256']=[]
            elif field=='failed_gate': self.receipt['verification']['gates'][0]['status']='failed'
            else: self.receipt['verification']['gates']=[]
            self.reseal()
            with self.subTest(field=field), self.assertRaises(ValueError): self.check()

    def test_incomplete_or_boolean_call_counts_refuse(self):
        original=deepcopy(self.provenance)
        for field,value in (('completed_public_calls',True),('unfinished_public_calls',1),
                ('accounted_calls',0),('output_plan_complete',False),('controller_origin_verified',False)):
            self.provenance=deepcopy(original); self.provenance[field]=value; self.reseal()
            with self.subTest(field=field), self.assertRaises(ValueError): self.check()

    def test_gap_removal_qualification_upgrade_model_call_or_signature_refuse(self):
        original=deepcopy(self.provenance)
        for field,value in (('gaps',[]),('production_qualified',True),('qualifies_for_factory_receipt',True),
                ('external_model_calls',1),('signatures_created',1)):
            self.provenance=deepcopy(original); self.provenance[field]=value; self.reseal()
            with self.subTest(field=field), self.assertRaises(ValueError): self.check()

    def test_clean_case_rejects_builder_attempt_or_changed_source(self):
        original=deepcopy(self.receipt)
        for field,value in (('attempts',1),('changed_paths',['public.py']),('final_snapshot_sha256','e'*64)):
            self.receipt=deepcopy(original); self.receipt[field]=value; self.reseal()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,'positive-clean-baseline-only'):
                self.check()

    def test_non_ci_execution_stops_before_any_subprocess(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}), patch('subprocess.run') as invoke:
            with self.assertRaisesRegex(ValueError,'positive-ci-only'): main([])
            invoke.assert_not_called()


if __name__=='__main__': unittest.main()
