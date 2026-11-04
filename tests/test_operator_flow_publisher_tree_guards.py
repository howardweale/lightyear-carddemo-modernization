"""CI-only real Git tree and untrusted main-record checks; no service authority."""
import copy,unittest
import test_operator_flow_tree_guards as fixtures
from tools.ci.operator_flow_consumer import METADATA
from tools.ci.operator_flow_publisher_preflight import _main_identity,_publication_tree

class PublisherTreeGuards(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.OriginalTreeChecks();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.values=dict(executable=self.fixture.executable,metadata_head=self.fixture.candidate())
        self.files={name:self.fixture.metadata[path] for name,path in METADATA.items()}
    def check(self,base=None):
        return _publication_tree(self.fixture.root,self.values,base or self.fixture.base,self.files)
    def test_original_full_tree_and_actual_merge_preserve_false_authority(self):
        result=self.check();self.assertEqual(result['tree'],result['actual_merge_tree'])
        self.assertFalse(result['full_publication_guards_passed']);self.assertFalse(result['publication_authorized'])
        self.assertEqual(self.fixture.oid(),self.values['metadata_head'])
    def test_changed_original_metadata_refuses(self):
        self.files['proof.json']+=b'changed'
        with self.assertRaisesRegex(ValueError,'complete-inventory-mismatch'):self.check()
    def test_extra_metadata_key_refuses(self):
        self.files['extra']=b'x'
        with self.assertRaisesRegex(ValueError,'original-metadata'):self.check()
    def test_main_advance_with_clean_merge_refuses(self):
        f=self.fixture;f.git('checkout','--detach',f.base)
        (f.root/'new-main.txt').write_bytes(b'new');f.commit('advance');main=f.oid()
        f.git('checkout','--detach',self.values['metadata_head'])
        with self.assertRaisesRegex(ValueError,'actual-main-merge-differs'):self.check(main)
    def test_exact_main_record_is_only_identity(self):
        row=dict(ref='refs/heads/main',object=dict(type='commit',sha=self.fixture.base))
        before=copy.deepcopy(row);self.assertEqual(_main_identity(row,self.fixture.base),self.fixture.base)
        self.assertEqual(before,row)
    def test_changed_main_record_refuses(self):
        with self.assertRaisesRegex(ValueError,'current-main-changed'):
            _main_identity(dict(ref='refs/heads/main',object=dict(type='commit',sha='0'*40)),self.fixture.base)
    def test_tag_wrong_ref_or_missing_object_refuses(self):
        for row in ({},dict(ref='refs/heads/other',object=dict(type='commit',sha=self.fixture.base)),
                    dict(ref='refs/heads/main',object=dict(type='tag',sha=self.fixture.base))):
            with self.subTest(row=row),self.assertRaisesRegex(ValueError,'current-main-changed'):
                _main_identity(row,self.fixture.base)
    def test_asserted_boolean_main_expectation_refuses(self):
        with self.assertRaisesRegex(ValueError,'main-expectation'):_main_identity({},True)
