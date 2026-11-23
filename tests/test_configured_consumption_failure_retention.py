"""CI-only failure ordering with synthetic reservation; never genuine admission."""
from contextlib import ExitStack
import os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from lightyear_execution import configured_receipt_context as module
from lightyear_execution.contracts import ExecutionContractError,canonical_hash
from lightyear_execution.configured_consumption_evidence import consumption_message_bytes

class ConsumptionFailureRetentionTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'source';self.root.mkdir()
        self.out=self.base/'evidence';self.out.mkdir()
        self.record=dict(schema='factory-human-drill-consumption/1',case_id='configured-build-control',
            nonce_sha256='a'*64,plan_sha256='b'*64,decision_sha256='c'*64,
            trusted_journal_head='d'*64,work_order_sha256='e'*64,execution_policy_sha256='f'*64,
            ci={'synthetic':True},consumed_before_execution=True,execution_authorized=False,
            admission_receipt_issued=False)
        self.record['content_sha256']=canonical_hash(self.record)
        self.bound={'review':{'verified_model_admission':{k:self.record[k] for k in
            ('plan_sha256','decision_sha256','trusted_journal_head')},
            'drill_binding':{'nonce_sha256':self.record['nonce_sha256']}}}
        self.result={'record':self.record,'status':'consumed-only'}
        self.args=(SimpleNamespace(root=self.root),SimpleNamespace(content_sha256='e'*64),
                   SimpleNamespace(content_sha256='f'*64),object())
        self.kw=dict(source_root=self.root,input_paths={},read_manifest={},model_config_path='unused',
            public_isolation_path='unused',evidence_path=self.out/'human-admission.json')

    def exercise(self,second,*,fsync_error=False):
        with ExitStack() as stack:
            pre=stack.enter_context(patch.object(module,'_preflight',side_effect=[self.bound,second]))
            reserve=stack.enter_context(patch.object(module,'reserve_configured_receipt_main_plan',return_value=self.result))
            if fsync_error:stack.enter_context(patch.object(module.os,'fsync',side_effect=OSError('synthetic-fsync-failure')))
            with self.assertRaises((ExecutionContractError,OSError)):
                module.admit_configured_receipt_context(*self.args,**self.kw)
            self.assertEqual(reserve.call_count,1)
            self.assertEqual(pre.call_count,1 if fsync_error else 2)
        self.assertFalse((self.out/'human-admission.json').exists())

    def test_expiry_after_return_retains_original_consumption(self):
        self.exercise(ExecutionContractError('synthetic-proof-expired'))
        self.assertEqual((self.out/'human-consumption.json').read_bytes(),consumption_message_bytes(self.record))

    def test_changed_trust_after_return_retains_original_consumption(self):
        self.exercise({'changed':True})
        self.assertEqual((self.out/'human-consumption.json').read_bytes(),consumption_message_bytes(self.record))

    def test_failed_fsync_never_reaches_admission_or_fresh_proof(self):
        self.exercise(ExecutionContractError('must-not-be-reached'),fsync_error=True)

    def test_existing_consumption_evidence_refuses_before_reservation(self):
        retained=self.out/'human-consumption.json';retained.write_bytes(b'original')
        with patch.object(module,'_preflight',return_value=self.bound), patch.object(module,'reserve_configured_receipt_main_plan') as reserve:
            with self.assertRaises(ExecutionContractError):
                module.admit_configured_receipt_context(*self.args,**self.kw)
            reserve.assert_not_called()
        self.assertEqual(retained.read_bytes(),b'original')
        self.assertFalse((self.out/'human-admission.json').exists())
