"""CI-only bridge refusals. No mocked successful admission or provider send."""
import os
import unittest
from unittest.mock import patch
from lightyear_factory.contracts import ContractError
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.configured_human_context import ConfiguredHumanExecutionContext
from lightyear_execution.configured_human_controller import (
    create_configured_human_router,verify_configured_controller,bind_configured_controller)


class ConfiguredControllerRefusalTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_receipt_mapping_cannot_construct_router(self):
        with patch('lightyear_factory.model_config.configured_models') as build:
            with self.assertRaisesRegex(ContractError,'native-context'):
                create_configured_human_router({'status':'passed'})
            build.assert_not_called()

    def test_forged_context_cannot_reach_provider_construction(self):
        context=object.__new__(ConfiguredHumanExecutionContext)
        with patch('lightyear_factory.model_config.configured_models') as build:
            with self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
                create_configured_human_router(context)
            build.assert_not_called()

    def test_subclass_cannot_replace_genuine_context(self):
        class Replacement(ConfiguredHumanExecutionContext):pass
        with self.assertRaisesRegex(ContractError,'native-context'):
            create_configured_human_router(object.__new__(Replacement))

    def test_fake_controller_cannot_return_runtime_admission(self):
        with self.assertRaisesRegex(ContractError,'native-controller'):
            verify_configured_controller(object(),object())

    def test_original_controller_with_forged_context_is_refused(self):
        from lightyear_factory.orchestrator import FactoryOrchestrator
        controller=object.__new__(FactoryOrchestrator)
        controller.execution_context=object.__new__(ConfiguredHumanExecutionContext)
        with self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
            verify_configured_controller(controller,object())

    def test_receipt_or_journal_cannot_establish_controller(self):
        with self.assertRaisesRegex(ContractError,'native-controller'):
            bind_configured_controller({'admission_receipt':{'status':'passed'}},
                                      object(),object(),'unused')

    def test_no_provider_or_secret_callback_argument(self):
        for value in ({'provider':object()},{'opener':lambda:None},
                      {'secret_store':object()},{'resume_receipt':{}}):
            with self.assertRaises(TypeError):
                create_configured_human_router(object(),**value)
