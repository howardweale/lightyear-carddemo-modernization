"""CI-only public configuration refusals; no proof or secret use."""
import os,unittest
from hashlib import sha256
import json
from tools.ci.p5_configured_receipt_trust_inputs import validate_public_configuration
from tools.ci.p5_configured_receipt_inputs import prepare

class ConfiguredReceiptInputTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.head='a'*40;self.plan={'schema':'factory-build-plan/1'}
        self.plan['content_sha256']=sha256(json.dumps(self.plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.env=dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/main',
            GITHUB_SHA=self.head,GITHUB_WORKFLOW_SHA=self.head,GITHUB_RUN_ATTEMPT='1',
            GITHUB_REPOSITORY='howardweale/lightyear-carddemo-modernization',
            P5_CONFIGURED_RECEIPT_APPROVED_HEAD=self.head,P5_CONFIGURED_RECEIPT_APPROVED_PLAN=self.plan['content_sha256'],
            P5_CONFIGURED_RECEIPT_JOURNAL_HEAD='b'*64)
    def test_synthetic_public_configuration_is_only_trust_configuration(self):
        result=validate_public_configuration(self.env,self.head,self.plan)
        self.assertEqual(set(result),{'scope','public_key','journal_head_sha256'})
    def test_pull_request_cannot_prepare_main_trust(self):
        self.env['GITHUB_EVENT_NAME']='pull_request'
        with self.assertRaisesRegex(ValueError,'ci-scope'):validate_public_configuration(self.env,self.head,self.plan)
    def test_changed_workflow_revision_refused(self):
        self.env['GITHUB_WORKFLOW_SHA']='c'*40
        with self.assertRaisesRegex(ValueError,'ci-scope'):validate_public_configuration(self.env,self.head,self.plan)
    def test_old_provider_only_approval_names_do_not_supply_main_authority(self):
        self.env['P5_CONFIGURED_HUMAN_APPROVED_HEAD']=self.env.pop('P5_CONFIGURED_RECEIPT_APPROVED_HEAD')
        with self.assertRaisesRegex(ValueError,'approved-head'):validate_public_configuration(self.env,self.head,self.plan)
    def test_second_attempt_refused(self):
        self.env['GITHUB_RUN_ATTEMPT']='2'
        with self.assertRaisesRegex(ValueError,'ci-scope'):validate_public_configuration(self.env,self.head,self.plan)
