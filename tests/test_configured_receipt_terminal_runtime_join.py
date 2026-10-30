"""CI-only untrusted runtime relationships. No native admission fixtures."""
import copy,os,unittest
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_execution.configured_terminal_runtime_join import match_terminal_runtime


def hashed(v):
    v=dict(v);v['content_sha256']=canonical_hash(v,{'content_sha256'});return v


def records(build=True):
    runtime=dict(schema='factory-model-admission/1',provider_verified=False,
        plan_sha256='a'*64,decision_sha256='b'*64,trusted_journal_head='c'*64,
        work_order_sha256='d'*64,executable_commit='e'*40,
        workspace_read_manifest={'untrusted-example.txt':'f'*64})
    admission=hashed(dict({k:runtime[k] for k in ('plan_sha256','decision_sha256',
        'trusted_journal_head','work_order_sha256')},runtime_binding_sha256=canonical_hash(runtime)))
    identity=hashed(dict(work_order_sha256=runtime['work_order_sha256'],
        admission_receipt_sha256=admission['content_sha256'],
        workspace_inventory_sha256=canonical_hash(runtime['workspace_read_manifest'])))
    receipt=dict(work_order_sha256=runtime['work_order_sha256'])
    if build:receipt['factory_build_receipt']={'current_admission_sha256':canonical_hash(runtime)}
    return hashed(receipt),admission,identity,runtime


class ConfiguredReceiptTerminalRuntimeJoin(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
    def test_original_runtime_relationships_return_no_authority_and_preserve_input(self):
        value=records();before=copy.deepcopy(value)
        self.assertIsNone(match_terminal_runtime(*value));self.assertEqual(value,before)
    def test_early_receipt_without_build_is_not_synthesized(self):
        value=records(False);before=copy.deepcopy(value)
        self.assertIsNone(match_terminal_runtime(*value));self.assertEqual(value,before)
        self.assertNotIn('factory_build_receipt',value[0])
    def test_changed_parent_executable_refuses_original_admission_digest(self):
        receipt,admission,identity,runtime=records();runtime['executable_commit']='f'*40
        with self.assertRaisesRegex(ContractError,'admission-digest'):
            match_terminal_runtime(receipt,admission,identity,runtime)
    def test_build_reference_mismatch_or_missing_refuses(self):
        for build in ({'current_admission_sha256':'0'*64},{},[]):
            receipt,admission,identity,runtime=records();receipt['factory_build_receipt']=build
            with self.subTest(build=build),self.assertRaisesRegex(ContractError,'build-digest'):
                match_terminal_runtime(hashed(receipt),admission,identity,runtime)
    def test_plan_decision_trust_and_order_mismatch_refuse(self):
        for field in ('plan_sha256','decision_sha256','trusted_journal_head','work_order_sha256'):
            receipt,admission,identity,runtime=records();runtime[field]='0'*64
            with self.subTest(field=field),self.assertRaisesRegex(ContractError,'admission-field'):
                match_terminal_runtime(receipt,admission,identity,runtime)
    def test_workspace_substitution_missing_and_empty_refuse(self):
        for manifest in ({'other.txt':'f'*64},{},None):
            receipt,admission,identity,runtime=records();runtime['workspace_read_manifest']=manifest
            with self.subTest(manifest=manifest),self.assertRaisesRegex(ContractError,'workspace'):
                match_terminal_runtime(receipt,admission,identity,runtime)
    def test_identity_admission_and_receipt_order_substitutions_refuse(self):
        for field in ('admission_receipt_sha256','work_order_sha256'):
            receipt,admission,identity,runtime=records();identity[field]='0'*64
            with self.subTest(field=field),self.assertRaisesRegex(ContractError,'identity'):
                match_terminal_runtime(receipt,admission,hashed(identity),runtime)
        receipt,admission,identity,runtime=records();receipt['work_order_sha256']='0'*64
        with self.assertRaisesRegex(ContractError,'identity'):
            match_terminal_runtime(hashed(receipt),admission,identity,runtime)
    def test_boolean_shape_and_missing_record_digest_refuse(self):
        for value in (0,True,None):
            receipt,admission,identity,runtime=records();runtime['provider_verified']=value
            with self.subTest(value=value),self.assertRaisesRegex(ContractError,'shape'):
                match_terminal_runtime(receipt,admission,identity,runtime)
        for index in range(3):
            values=list(records());values[index].pop('content_sha256')
            with self.subTest(index=index),self.assertRaisesRegex(ContractError,'record-digest'):
                match_terminal_runtime(*values)
