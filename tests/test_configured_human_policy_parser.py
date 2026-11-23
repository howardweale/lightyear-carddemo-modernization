"""CI-only parser scope tests. Parsing never issues authority or reads secrets."""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from lightyear_execution.contracts import ExecutionContractError, ExecutionPolicy

class ConfiguredHumanPolicyParserTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        root=Path(__file__).resolve().parents[1]
        self.public=json.loads((root/'tests/fixtures/p5_public/human-clean-control/execution-policy.json').read_bytes())
        self.value=deepcopy(self.public)
        self.value['id']='lightyear:configured-human:configured-build-control'
        self.value['secrets']['allowed_names']=['OPENAI_API_KEY']
        self.value['identities']['roles']['provider']={'actions':['secret:lease:OPENAI_API_KEY']}

    def test_new_parser_preserves_format_and_issues_no_admission(self):
        parsed=ExecutionPolicy.from_configured_human_dict(self.value)
        self.assertEqual(parsed.to_dict(),self.value)
        self.assertEqual(parsed.signature_algorithm,'FACTORY-TOWER-PROOF')
        self.assertEqual(parsed.allowed_secret_names,('OPENAI_API_KEY',))
        self.assertFalse(hasattr(parsed,'admission_receipt'))
        self.assertFalse(hasattr(parsed,'lease_secret'))

    def test_existing_public_loader_still_refuses_provider_secret(self):
        ExecutionPolicy.from_dict(self.public)
        with self.assertRaisesRegex(ExecutionContractError,'no secrets'):
            ExecutionPolicy.from_dict(self.value)
        with self.assertRaisesRegex(ExecutionContractError,'exact scope'):
            ExecutionPolicy.from_configured_human_dict(self.public)

    def test_other_case_hmac_and_unbound_key_are_refused(self):
        for field,value in (('id','lightyear:configured-human:other'),):
            changed=deepcopy(self.value);changed[field]=value
            with self.assertRaisesRegex(ExecutionContractError,'exact scope'):
                ExecutionPolicy.from_configured_human_dict(changed)
        changed=deepcopy(self.value);changed['admission']['signature_algorithm']='HMAC-SHA256'
        with self.assertRaisesRegex(ExecutionContractError,'exact scope'):
            ExecutionPolicy.from_configured_human_dict(changed)
        for keys in (['hmac-key'],['0'*64,'1'*64]):
            changed=deepcopy(self.value);changed['admission']['trusted_key_ids']=keys
            with self.assertRaisesRegex(ExecutionContractError,'exact scope'):
                ExecutionPolicy.from_configured_human_dict(changed)

    def test_credential_scope_cannot_expand_or_enter_container(self):
        for names in ([],['ANTHROPIC_API_KEY'],['OPENAI_API_KEY','GEMINI_API_KEY'],['OPENAI_API_KEY','OPENAI_API_KEY']):
            changed=deepcopy(self.value);changed['secrets']['allowed_names']=names
            with self.assertRaisesRegex(ExecutionContractError,'exact scope'):
                ExecutionPolicy.from_configured_human_dict(changed)
        changed=deepcopy(self.value);changed['runtime']['allowed_environment'].append('OPENAI_API_KEY')
        with self.assertRaisesRegex(ExecutionContractError,'exact scope'):
            ExecutionPolicy.from_configured_human_dict(changed)

    def test_roles_cannot_lease_for_another_subject_or_broaden_actions(self):
        for role in self.value['identities']['roles']:
            changed=deepcopy(self.value)
            changed['identities']['roles'][role]['actions'].append('secret:lease:GEMINI_API_KEY')
            with self.subTest(role=role),self.assertRaisesRegex(ExecutionContractError,'exact scope'):
                ExecutionPolicy.from_configured_human_dict(changed)

    def test_existing_container_and_persistence_checks_remain_required(self):
        for field,value in (('network_mode','host'),('read_only_root',False),('no_new_privileges',False)):
            changed=deepcopy(self.value);changed['isolation'][field]=value
            with self.subTest(field=field),self.assertRaises(ExecutionContractError):
                ExecutionPolicy.from_configured_human_dict(changed)
        changed=deepcopy(self.value);changed['secrets']['persist_values']=True
        with self.assertRaisesRegex(ExecutionContractError,'never be persisted'):
            ExecutionPolicy.from_configured_human_dict(changed)
