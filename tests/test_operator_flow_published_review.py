"""Untrusted post-publication record joins; no API, signing or admission."""
import copy,os,unittest
from datetime import datetime,timezone
import test_operator_flow_completed_review as fixtures
from tools.ci.operator_flow_completed_review import _published_relationships
from tools.ci.operator_flow_metadata import MESSAGE

class PublishedReview(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.f=fixtures.CompletedReview();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.candidate=self.f.fixture.candidate;self.M=self.candidate['commit'];self.branch='refs/heads/codex/disposable-review'
        self.pr=copy.deepcopy(self.f.pr);self.pr['head'].update(sha=self.M,ref='codex/disposable-review');self.pr['merge_commit_sha']=None
        self.ref=dict(ref=self.branch,object=dict(type='commit',sha=self.M))
        person=dict(name='Codex',email='codex@openai.com',date=datetime.fromtimestamp(self.candidate['commit_epoch'],timezone.utc).isoformat())
        self.commit=dict(sha=self.M,tree=dict(sha=self.candidate['tree']),parents=[dict(sha=self.candidate['parent'])],
            author=dict(person),committer=dict(person),message=MESSAGE)
    def observe(self):
        return _published_relationships(self.f.run,self.f.workflow,self.f.listing,self.pr,self.f.merge,
            self.ref,self.commit,self.f.expected,self.M,self.branch,self.candidate)
    def test_M_readback_retains_original_E_review_without_authority(self):
        result=self.observe();self.assertEqual(result['reviewer'],self.f.observe())
        self.assertEqual(result['published_head'],self.M);self.assertFalse(result['publication_authorized'])
        self.assertFalse(result['qualification_evidence'])
    def test_old_E_PR_head_is_not_postpublication_M(self):
        self.pr['head']['sha']=self.candidate['parent']
        with self.assertRaisesRegex(ValueError,'current-M'):self.observe()
    def test_changed_branch_or_ref_is_refused(self):
        self.ref['ref']='refs/heads/main'
        with self.assertRaises(ValueError):self.observe()
        self.ref['ref']=self.branch;self.pr['head']['ref']='codex/other'
        with self.assertRaisesRegex(ValueError,'current-M'):self.observe()
    def test_M_commit_extra_parent_or_changed_tree_refused(self):
        self.commit['parents'].append(dict(sha='0'*40))
        with self.assertRaises(ValueError):self.observe()
        self.commit['parents']=self.commit['parents'][:1];self.commit['tree']['sha']='0'*40
        with self.assertRaises(ValueError):self.observe()
    def test_historical_review_cannot_claim_it_ran_on_M(self):
        self.f.run['head_sha']=self.M
        with self.assertRaisesRegex(ValueError,'completed-review-run'):self.observe()
    def test_changed_current_base_refused(self):
        self.pr['base']['sha']='0'*40
        with self.assertRaisesRegex(ValueError,'current-M'):self.observe()
    def test_original_E_tested_merge_order_still_required(self):
        self.f.merge['parents'].reverse()
        with self.assertRaisesRegex(ValueError,'tested-merge'):self.observe()
    def test_failed_historical_step_and_asserted_authority_refuse(self):
        self.f.job['steps'][0]['conclusion']='skipped'
        with self.assertRaisesRegex(ValueError,'successful-steps'):self.observe()
        self.f.job['steps'][0]['conclusion']='success';self.candidate['publication_authorized']=True
        with self.assertRaisesRegex(ValueError,'no-authority'):self.observe()
