"""CI-only unadmitted refusals and byte parsing; no mock passed authority."""
import base64,os,unittest
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.configured_receipt_context import ConfiguredReceiptExecutionContext,_decode_transport_key,admit_configured_receipt_context
from lightyear_execution.configured_receipt_main import reserve_configured_receipt_main_plan,review_configured_receipt_main_identity
from lightyear_execution.configured_receipt_materials import validate_public_material_bytes,review_receipt_public_materials


class ConfiguredReceiptContextTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_no_receipt_constructor_or_unadmitted_secret_lease(self):
        with self.assertRaises(ExecutionContractError):ConfiguredReceiptExecutionContext({'status':'passed'})
        context=object.__new__(ConfiguredReceiptExecutionContext)
        with self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
            context.lease_secret('provider','OPENAI_API_KEY',None)

    def test_unadmitted_transport_owner_refuses_before_material_read(self):
        context=object.__new__(ConfiguredReceiptExecutionContext)
        with self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
            context.lease_transport_key(object(),object(),object(),object(),'unused')

    def test_main_entries_refuse_passed_dict_before_api_or_nonce(self):
        for entry in (reserve_configured_receipt_main_plan,review_configured_receipt_main_identity):
            with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
                entry({'status':'passed'},object(),object())

    def test_public_material_review_requires_original_proof_first(self):
        with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
            review_receipt_public_materials(object(),object(),object(),object())

    def test_canonical_synthetic_transport_bytes_only(self):
        raw=bytes(range(32));encoded=base64.b64encode(raw).decode('ascii')
        self.assertEqual(_decode_transport_key(encoded),raw)
        for value in ('',encoded+'\n',encoded[:-1],base64.b64encode(b'x'*31).decode('ascii'),object()):
            with self.assertRaisesRegex(ExecutionContractError,'material-invalid'):
                _decode_transport_key(value)

    def test_public_material_shape_does_not_grant_authority(self):
        trust=b'factory@lightyear.invalid ssh-ed25519 AAAA\n'
        self.assertEqual(validate_public_material_bytes(trust,b'public-key-id-1\n'),'public-key-id-1')
        for signers,key_id in ((trust+trust,b'id\n'),(trust,b'id\nother\n'),(trust,b'../key\n'),(b'PRIVATE KEY',b'id\n')):
            with self.assertRaises(ExecutionContractError):validate_public_material_bytes(signers,key_id)

    def test_main_context_refuses_unadmitted_backend_before_paths(self):
        with self.assertRaisesRegex(ExecutionContractError,'native-context'):
            admit_configured_receipt_context(object(),object(),object(),object(),source_root=object(),
                input_paths=object(),read_manifest=object(),model_config_path=object(),public_isolation_path=object(),evidence_path=object())
