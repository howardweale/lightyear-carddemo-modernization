"""CI-only untrusted preflight argument refusal; no admitted fixture."""
import unittest

from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.configured_receipt_answer_preflight import review_answer_receipt_preflight


class AnswerPreflightRefusalTests(unittest.TestCase):
    def test_asserted_admission_refuses_before_unusable_paths(self):
        with self.assertRaisesRegex(ExecutionContractError, '^configured-human-native-context-required$'):
            review_answer_receipt_preflight(
                {'status': 'passed', 'execution_authorized': True}, object(),
                {'policy_id': 'lightyear:configured-receipt:answer-fragment'},
                object(), object(), object(), object(), object(), object())

    def test_caller_proof_or_service_override_is_not_accepted(self):
        for override in ('review', 'api', 'clock', 'environment', 'callback', 'consumption'):
            with self.subTest(override=override), self.assertRaises(TypeError):
                review_answer_receipt_preflight(
                    *[object() for _ in range(9)], **{override: object()})
