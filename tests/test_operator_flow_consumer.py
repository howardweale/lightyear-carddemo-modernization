"""CI-only pure refusal checks; never synthesize a passed native review/context."""
import json,unittest
from tools.ci.operator_flow_consumer import parse_approval,check_public_expectations

class ConsumerApprovalTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(metadata_head='a'*40,executable='b'*40,producer_run_id=12,artifact_id=34,
            plan_sha256='c'*64,decision_sha256='d'*64,journal_head_sha256='e'*64,
            public_key_sha256='f'*64,nonce_sha256='1'*64,archive_sha256='2'*64,
            fixture_only=True,allow_shared_nonce_consumption=True)
    def test_exact_configuration_is_only_parsed(self):
        self.assertEqual(parse_approval(json.dumps(self.row)),self.row)
    def test_absent_or_oversized_configuration_refuses(self):
        for raw in ('',' '*8193):
            with self.assertRaises(ValueError):parse_approval(raw)
    def test_unknown_or_missing_fields_refuse(self):
        for row in (dict(self.row,proof={}),{k:v for k,v in self.row.items() if k!='archive_sha256'}):
            with self.assertRaisesRegex(ValueError,'approval-fields'):parse_approval(json.dumps(row))
    def test_boolean_service_ids_refuse(self):
        for key in ('producer_run_id','artifact_id'):
            with self.assertRaisesRegex(ValueError,'approval-identity'):parse_approval(json.dumps(dict(self.row,**{key:True})))
    def test_same_E_and_M_refuse(self):
        with self.assertRaisesRegex(ValueError,'approval-identity'):parse_approval(json.dumps(dict(self.row,metadata_head=self.row['executable'])))
    def test_exact_explicit_shared_tag_scope_required(self):
        for key in ('fixture_only','allow_shared_nonce_consumption'):
            for value in (False,1,'true'):
                with self.assertRaisesRegex(ValueError,'fixture-tag-scope'):parse_approval(json.dumps(dict(self.row,**{key:value})))
    def test_duplicate_and_nonfinite_fields_refuse(self):
        for raw in ('{"fixture_only":true,"fixture_only":false}','{"producer_run_id":NaN}'):
            with self.assertRaises(ValueError):parse_approval(raw)
    def test_proof_report_cannot_supply_trust_head(self):
        files={'trust.json':json.dumps(dict(scope='factory',public_key='public.pem',journal_head_sha256='0'*64)).encode(),
               'public.pem':b'not a public key','producer.json':b'{}'}
        with self.assertRaisesRegex(ValueError,'independent-key-head'):check_public_expectations(self.row,files)
