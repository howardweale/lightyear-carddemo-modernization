"""CI-only refusal checks; no proof, public-key fixture or source mutation."""
import os
import unittest
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.configured_receipt_answer_models import review_answer_receipt_models
from lightyear_execution.configured_receipt_answer_scopes import verify_answer_receipt_role
from lightyear_execution.configured_receipt_answer_materials import (
    review_answer_receipt_public_materials, _committed_public_bytes)

class AnswerMaterialRefusalTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def test_model_review_refuses_asserted_proof_before_any_path_or_input_access(self):
        with self.assertRaisesRegex(ExecutionContractError, 'real-verifier'):
            review_answer_receipt_models({'status': 'passed'}, object(), object(), object(),
                input_paths=object(), read_manifest=object())

    def test_role_review_refuses_asserted_proof_before_policy_role_access(self):
        with self.assertRaisesRegex(ExecutionContractError, 'real-verifier'):
            verify_answer_receipt_role({'status': 'passed'}, object(), object(), 'planner', 'plan')

    def test_public_material_review_refuses_asserted_proof_before_manifest_access(self):
        with self.assertRaisesRegex(ExecutionContractError, 'real-verifier'):
            review_answer_receipt_public_materials({'status': 'passed'}, object(), object(), object())

    def test_cross_case_and_arbitrary_public_paths_refuse_before_file_or_git_access(self):
        for path in ('docs/factory/p5-human-clean-control/configured-build-control/receipt-allowed-signers.txt',
                     'docs/factory/p5-human-clean-control/configured-build-control/receipt-encryption-key-id.txt',
                     '../receipt-allowed-signers.txt', '/private/key', 'other.txt'):
            with self.subTest(path=path), self.assertRaisesRegex(ExecutionContractError, 'public-path'):
                _committed_public_bytes(object(), path)
