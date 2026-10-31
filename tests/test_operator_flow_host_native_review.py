"""Native trust refusal through the used proof/runtime sequence; no keys/API."""
import json,os,tempfile,unittest
from pathlib import Path
from lightyear_factory.contracts import ContractError
from tools.ci.operator_flow_publisher_preflight import _native_current_review,PREFIX

class HostNativeReview(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']);self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.root=self.base/'M';self.root.mkdir()
        source=Path(__file__).resolve().parents[1]/'tests/fixtures/p5_public/human-clean-control'
        target=self.root/'tests/fixtures/p5_public/human-clean-control';target.mkdir(parents=True)
        (target/'work-order.json').write_bytes((source/'work-order.json').read_bytes())
        policy=self.root/PREFIX/'execution-policy.json';policy.parent.mkdir(parents=True)
        policy.write_bytes((source/'execution-policy.json').read_bytes())
        self.public=self.base/'public';self.public.mkdir()
        (self.public/'public.pem').write_bytes(b'INERT NON-KEY PUBLIC TEST BYTES')
        self.trust=self.public/'trust.json'
    def run_review(self):return _native_current_review(self.root,self.trust,{})
    def test_missing_external_trust_refuses_before_native_plan(self):
        with self.assertRaisesRegex(ContractError,'factory-model-external-trust-required'):self.run_review()
    def test_checkout_cannot_supply_its_own_trust(self):
        self.trust=self.root/'trust.json';self.trust.write_bytes(b'{}')
        with self.assertRaisesRegex(ContractError,'factory-model-external-trust-required'):self.run_review()
    def test_nonfactory_trust_scope_refuses(self):
        self.trust.write_text(json.dumps(dict(scope='disposable-is-not-real-trust',public_key='public.pem',journal_head_sha256='a'*64)))
        with self.assertRaisesRegex(ContractError,'factory-model-trust-scope'):self.run_review()
    def test_missing_current_journal_head_refuses(self):
        self.trust.write_text(json.dumps(dict(scope='factory',public_key='public.pem')))
        with self.assertRaisesRegex(ContractError,'factory-model-trust-changed'):self.run_review()
