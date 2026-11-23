"""CI-only refusal paths; no human-proof mocking, secret or nonce use."""
from copy import copy,deepcopy
import os
import pickle
import unittest
from unittest.mock import patch
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.configured_human_context import (
    ConfiguredHumanExecutionContext,admit_configured_human_context)


class ConfiguredHumanContextRefusalTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_receipt_constructor_is_refused(self):
        with self.assertRaisesRegex(ExecutionContractError,'no-receipt-constructor'):
            ConfiguredHumanExecutionContext({'status':'passed'})

    def test_forged_object_cannot_bind_or_authorize(self):
        for method,args in (('bind',('0'*64,'old')),('authorize',('builder','factory:build','old'))):
            context=object.__new__(ConfiguredHumanExecutionContext)
            with self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
                getattr(context,method)(*args)

    def test_forged_context_cannot_read_a_secret(self):
        context=object.__new__(ConfiguredHumanExecutionContext)
        with patch.dict(os.environ,{},clear=True),patch.object(os.environ,'get',
                side_effect=AssertionError('credential environment must not be read')) as reader:
            with self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
                context.lease_secret('provider','OPENAI_API_KEY','old')
            reader.assert_not_called()

    def test_forged_context_cannot_supply_isolation_values(self):
        context=object.__new__(ConfiguredHumanExecutionContext)
        with self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
            context.public_expected_values(object())

    def test_forged_context_cannot_supply_verification_evidence(self):
        context=object.__new__(ConfiguredHumanExecutionContext)
        with self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
            context.record_verification({'gates':[{'execution':{'enforced':True}}]})

    def test_copy_and_pickle_cannot_resume_a_context(self):
        context=object.__new__(ConfiguredHumanExecutionContext)
        for operation in (copy,deepcopy,pickle.dumps):
            with self.subTest(operation=operation.__name__),self.assertRaises(ExecutionContractError):
                operation(context)

    def test_fake_inputs_cannot_reach_atomic_reservation(self):
        with patch('lightyear_execution.tower_drill_reservation._GitHubAPI.request',
                   side_effect=AssertionError('nonce API must not be called')) as api:
            with self.assertRaisesRegex(ExecutionContractError,'native-context'):
                admit_configured_human_context({'status':'passed'},object(),object(),object(),
                    source_root='.',input_paths={},read_manifest={},model_config_path='unused',
                    public_isolation_path='unused',evidence_path='unused')
            api.assert_not_called()

    def test_no_secret_reader_or_resume_receipt_can_be_injected(self):
        for extra in ({'secret_reader':lambda:'fake'},{'resume_receipt':{'status':'passed'}},
                      {'consumption':{'status':'consumed-only'}}):
            with self.assertRaises(TypeError):
                admit_configured_human_context(object(),object(),object(),object(),
                    source_root='.',input_paths={},read_manifest={},model_config_path='unused',
                    public_isolation_path='unused',evidence_path='unused',**extra)

    def test_forged_summary_does_not_claim_qualification(self):
        context=object.__new__(ConfiguredHumanExecutionContext)
        with self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
            context.summary()

    def test_repr_never_dumps_context_state(self):
        context=object.__new__(ConfiguredHumanExecutionContext)
        context.untrusted_extra='synthetic-must-not-appear'
        self.assertEqual(repr(context),'<ConfiguredHumanExecutionContext>')
