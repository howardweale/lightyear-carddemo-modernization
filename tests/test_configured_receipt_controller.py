"""CI-only native binding refusals; no receipt authority or execution."""
import os,unittest
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_receipt_controller import create_configured_human_router,verify_configured_controller
from lightyear_execution.configured_receipt_lifecycle import finalize_receipt_controller
from lightyear_execution.configured_receipt_terminal import _require_origin
from lightyear_execution.configured_receipt_transport import require_configured_transport
from lightyear_execution.configured_receipt_wire_boundary import require_original_wire_open


class ConfiguredReceiptControllerTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_passed_mapping_cannot_create_native_router(self):
        with self.assertRaisesRegex(ContractError,'native-context'):
            create_configured_human_router({'status':'passed'})

    def test_passed_mapping_cannot_verify_controller(self):
        with self.assertRaisesRegex(ContractError,'native-controller'):
            verify_configured_controller({'status':'passed'},object())

    def test_forged_finalization_refuses_before_signer_or_secret(self):
        with self.assertRaisesRegex(ContractError,'native-controller'):
            finalize_receipt_controller(object(),object(),object(),object(),object(),'unused')

    def test_terminal_reader_does_not_recover_forged_origin(self):
        with self.assertRaisesRegex(ContractError,'original-controller'):_require_origin(object())

    def test_unbound_transport_cannot_reserve_or_open(self):
        with self.assertRaisesRegex(ContractError,'native-controller'):
            require_configured_transport(object(),{})
        with self.assertRaisesRegex(ContractError,'native-provider'):
            require_original_wire_open(object(),object())
