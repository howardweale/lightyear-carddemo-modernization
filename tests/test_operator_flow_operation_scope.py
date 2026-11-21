"""CI-only untrusted scope and real intent refusal cases; no authority."""
import copy,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.ci.operator_flow_publication_intent import operation_scope,reserve_intent

class OperationScope(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.root=Path(os.environ['RUNNER_TEMP']).resolve()/'disposable-scope-nonexistent'
        self.values=dict(executable='1'*40,metadata_head='2'*40,producer_run_id=101,artifact_id=102,
            archive_sha256='3'*64,plan_sha256='4'*64,decision_sha256='5'*64,journal_head_sha256='6'*64,
            public_key_sha256='7'*64,nonce_sha256='8'*64,commit_epoch=103)
        self.args=dict(intent_root=self.root/'intent',executable_root=self.root/'E',metadata_root=self.root/'M',
            trust_path=self.root/'public-trust',empty_hooks=self.root/'hooks',values=self.values,
            reviewer_run_id=104,reviewer_job_id=105,pr_number=106,base='9'*40,tested_merge='a'*40,
            branch_ref='refs/heads/codex/disposable-scope',expected_request_sha256='b'*64,
            expected_main_protection_sha256='c'*64,expected_main_rules_sha256='d'*64,
            expected_java_fence_sha256='e'*64,expected_posttran_inventory_sha256='f'*64)
    def test_dictionary_order_does_not_change_exact_scope(self):
        other=copy.deepcopy(self.args);other['values']=dict(reversed(list(self.values.items())))
        self.assertEqual(operation_scope(**self.args),operation_scope(**other))
    def test_every_original_public_scalar_changes_scope(self):
        expected=operation_scope(**self.args)
        for key,value in self.values.items():
            other=copy.deepcopy(self.args);other['values'][key]=value+1 if type(value) is int else '0'*len(value)
            with self.subTest(key=key):self.assertNotEqual(expected,operation_scope(**other))
    def test_every_other_argument_changes_scope(self):
        expected=operation_scope(**self.args)
        for key,value in self.args.items():
            if key=='values':continue
            if isinstance(value,Path):changed=value.parent/(value.name+'-other')
            elif type(value) is int:changed=value+1
            elif key=='branch_ref':changed='refs/heads/codex/disposable-other'
            else:changed='0'*len(value)
            with self.subTest(key=key):self.assertNotEqual(expected,operation_scope(**dict(self.args,**{key:changed})))
    def test_integer_fields_reject_boolean_coercion_and_out_of_range(self):
        for key in ('producer_run_id','artifact_id','commit_epoch','reviewer_run_id','reviewer_job_id','pr_number'):
            for bad in (True,False,0,-1,10**20,'104',104.0):
                other=copy.deepcopy(self.args)
                if key in self.values:other['values'][key]=bad
                else:other[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):operation_scope(**other)
    def test_all_digest_fields_reject_wrong_types_lengths_and_case(self):
        fields=[('values',k) for k,v in self.values.items() if type(v) is str]
        fields += [('args',k) for k in self.args if k in ('base','tested_merge') or k.startswith('expected_')]
        for location,key in fields:
            for bad in (True,None,'','A'*64,'0'*39,'0'*65):
                other=copy.deepcopy(self.args)
                (other['values'] if location=='values' else other)[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):operation_scope(**other)
    def test_original_scalar_keys_are_exact_and_mapping_subclasses_refuse(self):
        class Mapping(dict):pass
        for values in (None,Mapping(self.values),dict(self.values,approval=True),{k:v for k,v in self.values.items() if k!='nonce_sha256'}):
            with self.subTest(values_type=type(values).__name__),self.assertRaises(ValueError):
                operation_scope(**dict(self.args,values=values))
    def test_relative_or_arbitrary_path_objects_refuse(self):
        for key in ('intent_root','executable_root','metadata_root','trust_path','empty_hooks'):
            for bad in ('relative',Path('relative'),None,True,object()):
                with self.subTest(key=key),self.assertRaises(ValueError):operation_scope(**dict(self.args,**{key:bad}))
    def test_protected_wildcard_or_injected_ref_refuses(self):
        for bad in ('refs/heads/main','refs/tags/x','refs/heads/codex/*','refs/heads/codex/x\ny',True,None):
            with self.subTest(bad=bad),self.assertRaises(ValueError):operation_scope(**dict(self.args,branch_ref=bad))
    def test_scope_is_immutable_does_not_read_files_or_create_authority(self):
        with patch('builtins.open',side_effect=AssertionError('unexpected I/O')):
            scope=operation_scope(**self.args)
        def immutable(x):
            self.assertIn(type(x),(tuple,str,int))
            if type(x) is tuple:
                for child in x:immutable(child)
        immutable(scope)
        old=scope;self.values['plan_sha256']='0'*64
        self.assertNotEqual(old,operation_scope(**self.args))
        self.assertNotIn('publication_authorized',repr(scope))
    def test_same_intent_cannot_resume_and_another_directory_changes_scope(self):
        with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as tmp:
            root=Path(tmp).resolve();first=root/'one';second=root/'two';first.mkdir();second.mkdir()
            args=dict(self.args,intent_root=first);expected=operation_scope(**args)
            binding=dict(executable=self.values['executable'],metadata_head=self.values['metadata_head'],
                request_sha256=self.args['expected_request_sha256'],branch_ref=self.args['branch_ref'])
            reserve_intent(first,**binding);marker=first/'operator-publication-intent.txt';before=marker.read_bytes()
            with self.assertRaises(FileExistsError):reserve_intent(first,**binding)
            self.assertEqual(marker.read_bytes(),before)
            self.assertNotEqual(expected,operation_scope(**dict(args,intent_root=second)))
            self.assertEqual(list(second.iterdir()),[])
