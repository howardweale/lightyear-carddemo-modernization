"""CI-only policy and refusal tests: no keys, signatures or authority fixtures."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_execution.contracts import ExecutionContractError, ExecutionPolicy
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_execution.admission import sign_work_order, verify_work_order
from lightyear_execution.identity import IdentityAuthority
from lightyear_execution.tower_drill_roles import verify_human_drill_role


class TowerDrillPublicPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.original = json.loads((Path(__file__).resolve().parents[1]/'factory/execution/policy.json').read_text())
        self.public = copy.deepcopy(self.original)
        self.public['admission'].update(signature_algorithm='FACTORY-TOWER-PROOF',trusted_key_ids=['a'*64])
        self.public['secrets']['allowed_names'] = []

    def test_explicit_public_route_preserves_hardened_isolation_and_legacy_roundtrip(self):
        old=ExecutionPolicy.from_dict(self.original); new=ExecutionPolicy.from_dict(self.public)
        self.assertEqual(old.signature_algorithm,'HMAC-SHA256')
        self.assertEqual(new.signature_algorithm,'FACTORY-TOWER-PROOF')
        self.assertEqual(new.to_dict()['isolation'],old.to_dict()['isolation'])
        self.assertEqual(new.to_dict()['runtime'],old.to_dict()['runtime'])
        self.assertEqual(ExecutionPolicy.from_dict(new.to_dict()),new)
        self.assertEqual(ExecutionPolicy.from_dict(old.to_dict()),old)

    def test_public_policy_refuses_secrets_or_unpinned_trust_and_keeps_oci_checks(self):
        for section,key,value in [('secrets','allowed_names',['ANY_CREDENTIAL']),
            ('admission','trusted_key_ids',['unhashed-name']),('admission','trusted_key_ids',[]),
            ('isolation','network_mode','bridge'),('isolation','read_only_root',False)]:
            data=copy.deepcopy(self.public); data[section][key]=value
            with self.subTest(section=section,key=key), self.assertRaises(ExecutionContractError):
                ExecutionPolicy.from_dict(data)

    def test_public_mode_cannot_reach_hmac_identity_issuance(self):
        policy=ExecutionPolicy.from_dict(self.public)
        with patch('lightyear_execution.integration.IdentityAuthority') as authority:
            with self.assertRaisesRegex(ExecutionContractError,'refuses public-proof policy'):
                HardenedExecutionContext(policy,None,{'status':'passed'},None)
            authority.assert_not_called()

    def test_supplied_passed_record_does_not_authorize_human_role(self):
        policy=ExecutionPolicy.from_dict(self.public)
        with self.assertRaisesRegex(ExecutionContractError,'public-trust-policy'):
            verify_human_drill_role(SimpleNamespace(status='passed'),None,policy,'planner','factory:plan')

    def test_all_hmac_entry_points_refuse_public_mode_before_touching_keys(self):
        policy=ExecutionPolicy.from_dict(self.public)
        with self.assertRaisesRegex(ExecutionContractError,'refuses public-proof policy'):
            IdentityAuthority(policy,None)
        with self.assertRaisesRegex(ExecutionContractError,'refuses public-proof policy'):
            verify_work_order({},policy,{},'invalid-unused-time')
        with self.assertRaisesRegex(ExecutionContractError,'refuses public-proof policy'):
            sign_work_order(None,policy,'unused','unused',None,'unused','unused','unused')


if __name__=='__main__': unittest.main()
