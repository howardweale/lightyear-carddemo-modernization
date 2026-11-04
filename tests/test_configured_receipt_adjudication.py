"""CI-only original-object refusals; synthetic evidence grants no enforcement."""
import os,unittest
from lightyear_factory.contracts import ContractError
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.configured_receipt_security import observe_authorization,observe_lease,accept_original_gate_report,receipt_security_summary
from lightyear_execution.configured_receipt_gates import ReceiptGateRunner,run_original_receipt_gates
from lightyear_execution.configured_receipt_final import original_receipt_budget


class ConfiguredReceiptAdjudicationTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_synthetic_scope_cannot_register_authorization(self):
        with self.assertRaisesRegex(ExecutionContractError,'original-context'):
            observe_authorization(object(),{'status':'verified-scope-only'})

    def test_synthetic_lease_cannot_register_secret_evidence(self):
        with self.assertRaisesRegex(ExecutionContractError,'original-context'):
            observe_lease(object(),{},dict(name='FACTORY_TRANSPORT_KEY',persisted=False))

    def test_synthetic_gate_report_cannot_establish_enforcement(self):
        with self.assertRaisesRegex(ExecutionContractError,'original-context'):
            accept_original_gate_report(object(),{'gates':[{'execution':{'enforced':True}}]})

    def test_no_summary_from_passed_mapping(self):
        with self.assertRaisesRegex(ExecutionContractError,'original-context'):
            receipt_security_summary({'status':'passed'})

    def test_gate_runner_requires_native_backend(self):
        with self.assertRaisesRegex(ContractError,'native-container'):
            ReceiptGateRunner('unused',object(),lambda *args:None)

    def test_gate_execution_requires_original_controller_first(self):
        with self.assertRaisesRegex(ContractError,'native-controller'):
            run_original_receipt_gates(object(),object(),object())

    def test_final_budget_cannot_be_substituted_by_passed_receipt(self):
        with self.assertRaisesRegex(ContractError,'native-controller'):
            original_receipt_budget({'status':'passed'},object(),object(),'unused')
