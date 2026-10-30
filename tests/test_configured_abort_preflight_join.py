"""CI-only mapping relations, never authentic admission or process proof."""
import os,unittest
from copy import deepcopy
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_execution.configured_abort_preflight_join import match_abort_preflight

class AbortPreflightRelations(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
    def mappings(self):
        ci=dict(repository='example/repo',run_id=7,run_attempt=1,job='fixture',workflow_ref='fixture@'+'a'*40,head_sha='b'*40)
        admission={k:chr(99+i)*64 for i,k in enumerate(('plan_sha256','decision_sha256','trusted_journal_head','work_order_sha256','nonce_sha256','execution_policy_sha256'))}
        admission['ci']=ci
        verified={k:admission[k] for k in ('plan_sha256','decision_sha256','trusted_journal_head','work_order_sha256')}
        verified['executable_commit']=ci['head_sha']
        binding={k:admission[k] for k in ('nonce_sha256','execution_policy_sha256','work_order_sha256')}
        binding.update(case_id='configured-build-control',ci={k:ci[k] for k in ('repository','job','run_attempt','workflow_ref')})
        review=dict(schema='factory-human-drill-plan-review/1',status='verified-plan-only',execution_authorized=False,admission_receipt_issued=False,nonce_consumed=False,verified_model_admission=verified,drill_binding=binding)
        review['content_sha256']=canonical_hash(review)
        return admission,review,{k:ci[k] for k in ('repository','run_id','run_attempt','job')}
    def test_matching_mappings_return_no_authority(self):
        args=self.mappings();before=deepcopy(args)
        self.assertIsNone(match_abort_preflight(*args));self.assertEqual(args,before)
        self.assertNotIn('status',args[0])
    def test_different_original_proof_order_nonce_or_policy_refused(self):
        for key in ('plan_sha256','decision_sha256','trusted_journal_head','work_order_sha256','nonce_sha256','execution_policy_sha256'):
            a,r,c=self.mappings();self.assertNotEqual(a[key],'0'*64);a[key]='0'*64
            with self.subTest(key=key),self.assertRaises(ContractError):match_abort_preflight(a,r,c)
    def test_other_case_refused(self):
        a,r,c=self.mappings();r['drill_binding']['case_id']='other';r['content_sha256']=canonical_hash(r,{'content_sha256'})
        with self.assertRaises(ContractError):match_abort_preflight(a,r,c)
    def test_other_live_run_job_or_repository_refused(self):
        for key,value in (('run_id',8),('job','other'),('repository','other/repo'),('run_attempt',2)):
            a,r,c=self.mappings();c[key]=value
            with self.subTest(key=key),self.assertRaises(ContractError):match_abort_preflight(a,r,c)
    def test_other_metadata_head_or_workflow_refused(self):
        for key in ('head_sha','workflow_ref'):
            a,r,c=self.mappings();a['ci'][key]='changed'
            with self.subTest(key=key),self.assertRaises(ContractError):match_abort_preflight(a,r,c)
    def test_boolean_attempt_or_run_is_not_integer_identity(self):
        for side in ('admission','live'):
            for key in ('run_id','run_attempt'):
                a,r,c=self.mappings();(a['ci'] if side=='admission' else c)[key]=True
                with self.subTest(side=side,key=key),self.assertRaises(ContractError):match_abort_preflight(a,r,c)
    def test_modified_or_execution_approved_review_refused(self):
        a,r,c=self.mappings();r['status']='changed'
        with self.assertRaises(ContractError):match_abort_preflight(a,r,c)
        a,r,c=self.mappings();r['execution_authorized']=True;r['content_sha256']=canonical_hash(r,{'content_sha256'})
        with self.assertRaises(ContractError):match_abort_preflight(a,r,c)
    def test_missing_or_extra_live_fields_refused(self):
        for change in ('missing','extra'):
            a,r,c=self.mappings()
            if change=='missing':del c['job']
            else:c['approved']=True
            with self.subTest(change=change),self.assertRaises(ContractError):match_abort_preflight(a,r,c)
