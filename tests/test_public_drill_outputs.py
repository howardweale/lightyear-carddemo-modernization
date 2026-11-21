"""CI-only public comparison/refusal tests; no human proof or key fabricated."""
import copy
import os
import unittest

from lightyear_execution.contracts import ExecutionContractError,canonical_hash
from lightyear_execution.public_drill_outputs import (
    match_public_outputs,review_public_drill_outputs,validate_public_output_plan)


class PublicDrillOutputTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        response={'public_control':True}
        row=dict(sequence=1,role='planner',invocation_sha256='a'*64,schema_sha256='b'*64,
                 response_content=response,response_sha256=canonical_hash({'content':response}))
        self.script=dict(schema='factory-public-drill-outputs/1',case_id='synthetic-case',
            work_order_sha256='c'*64,provider='p5-scripted',model='p5-stub-2026-10-27',steps=[row])
        self.seal(self.script)

    def seal(self,value):value['content_sha256']=canonical_hash(value,{'content_sha256'})

    def test_matching_public_content_is_never_execution_or_origin_authority(self):
        result=match_public_outputs(self.script,copy.deepcopy(self.script['steps']))
        self.assertEqual(result['status'],'matched-expected-content')
        self.assertFalse(result['controller_origin_verified'])
        self.assertFalse(result['execution_authorized']);self.assertFalse(result['qualifies_for_factory_receipt'])

    def test_changed_content_invocation_schema_role_sequence_and_missing_extra_refuse(self):
        for key,value in dict(response_content={'public_control':False},invocation_sha256='d'*64,
                              schema_sha256='d'*64,role='builder',sequence=2).items():
            observed=copy.deepcopy(self.script['steps']);observed[0][key]=value
            with self.subTest(key=key),self.assertRaises(ExecutionContractError):match_public_outputs(self.script,observed)
        for observed in ([],self.script['steps']*2):
            with self.assertRaises(ExecutionContractError):match_public_outputs(self.script,observed)

    def test_bool_and_float_are_not_equal_to_integer_or_boolean_output(self):
        for key,value in [('sequence',True),('sequence',1.0),('response_content',{'public_control':1})]:
            observed=copy.deepcopy(self.script['steps']);observed[0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ExecutionContractError):
                match_public_outputs(self.script,observed)

    def test_self_rehashed_plan_with_wrong_order_or_response_hash_refuses(self):
        changed=copy.deepcopy(self.script);changed['work_order_sha256']='d'*64;self.seal(changed)
        with self.assertRaises(ExecutionContractError):validate_public_output_plan(changed,'c'*64,'synthetic-case')
        changed=copy.deepcopy(self.script);changed['steps'][0]['response_sha256']='d'*64;self.seal(changed)
        with self.assertRaises(ExecutionContractError):validate_public_output_plan(changed,'c'*64,'synthetic-case')

    def test_caller_dictionary_cannot_substitute_for_genuine_proof(self):
        with self.assertRaisesRegex(ExecutionContractError,'genuine-admission'):
            review_public_drill_outputs({'verified':True},None,None,'tests/fixtures/p5_public/unused.json')

    def test_non_stub_model_and_unknown_fields_refuse(self):
        for field,value in [('model','gpt-5.4-2026-03-05'),('provider','openai-responses'),('unreviewed',True)]:
            changed=copy.deepcopy(self.script);changed[field]=value;self.seal(changed)
            with self.assertRaises(ExecutionContractError):validate_public_output_plan(changed,'c'*64,'synthetic-case')


if __name__=='__main__':unittest.main()
