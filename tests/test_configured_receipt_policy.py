"""CI-only scope/refusal checks; no positive admission, secrets or sends."""
from copy import deepcopy
import json,os,unittest
from pathlib import Path
from lightyear_execution.contracts import ExecutionContractError,ExecutionPolicy
from lightyear_execution.configured_receipt_policy import parse_configured_receipt_policy,POLICY_ID,TRANSPORT_SECRET
from lightyear_execution.configured_receipt_admission import verify_configured_receipt_plan
from lightyear_execution.configured_receipt_runtime import verify_configured_receipt_runtime
from lightyear_execution.configured_receipt_scopes import verify_configured_receipt_role


class ConfiguredReceiptPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        root=Path(__file__).resolve().parents[1]
        self.value=json.loads((root/'tests/fixtures/p5_public/human-clean-control/execution-policy.json').read_bytes())
        self.value['id']=POLICY_ID
        self.value['secrets']['allowed_names']=['OPENAI_API_KEY',TRANSPORT_SECRET]
        self.value['identities']['roles'].update(provider={'actions':['secret:lease:OPENAI_API_KEY']},
            recorder={'actions':['secret:lease:FACTORY_TRANSPORT_KEY']})

    def test_exact_policy_roundtrip_is_scope_only(self):
        before=deepcopy(self.value);policy=parse_configured_receipt_policy(self.value)
        self.assertEqual(policy.to_dict(),before);self.assertEqual(self.value,before)
        self.assertEqual(policy.allowed_secret_names,('OPENAI_API_KEY',TRANSPORT_SECRET))
        self.assertFalse(hasattr(policy,'lease_secret'))
        self.assertFalse(hasattr(policy,'admission_receipt'))

    def test_old_loaders_still_refuse_receipt_scope(self):
        for parser in (ExecutionPolicy.from_dict,ExecutionPolicy.from_configured_human_dict):
            with self.assertRaises(ExecutionContractError):parser(self.value)

    def test_extra_scope_or_worker_secret_is_refused(self):
        for mutate in (lambda v:v['secrets']['allowed_names'].append('UNAPPROVED'),
                       lambda v:v['runtime']['allowed_environment'].append(TRANSPORT_SECRET),
                       lambda v:v['runtime']['allowed_environment'].append('OPENAI_API_KEY'),
                       lambda v:v['identities']['roles']['builder']['actions'].append('secret:lease:FACTORY_TRANSPORT_KEY')):
            value=deepcopy(self.value);mutate(value)
            with self.assertRaises(ExecutionContractError):parse_configured_receipt_policy(value)

    def test_persistence_hmac_and_isolation_relaxation_are_refused(self):
        for section,key,value in (('secrets','persist_values',True),('admission','signature_algorithm','HMAC-SHA256'),
                                  ('isolation','network_mode','host'),('isolation','read_only_root',False)):
            changed=deepcopy(self.value);changed[section][key]=value
            with self.assertRaises(ExecutionContractError):parse_configured_receipt_policy(changed)

    def test_unknown_fields_and_wrong_case_cannot_be_normalized(self):
        for key,value in (('extra',True),('id','lightyear:configured-receipt:other')):
            changed=deepcopy(self.value);changed[key]=value
            with self.assertRaises(ExecutionContractError):parse_configured_receipt_policy(changed)

    def test_passed_dictionary_cannot_review_receipt_proof(self):
        with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
            verify_configured_receipt_plan({'status':'passed'},object(),parse_configured_receipt_policy(self.value))

    def test_unadmitted_runtime_refuses_before_path_access(self):
        with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
            verify_configured_receipt_runtime(object(),object(),parse_configured_receipt_policy(self.value),
                source_root=object(),input_paths=object(),read_manifest=object())

    def test_policy_only_does_not_grant_recorder_role(self):
        with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
            verify_configured_receipt_role(object(),object(),parse_configured_receipt_policy(self.value),
                'recorder','secret:lease:FACTORY_TRANSPORT_KEY')
