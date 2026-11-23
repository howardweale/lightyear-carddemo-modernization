"""CI-only physical-send scope/refusal tests; no fabricated passed authority."""
import ast,os
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_human_transport import (
    configured_transport_action,require_configured_transport)


class ConfiguredTransportBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.row=dict(role='planner',provider='openai-responses',model='pinned-model',
            transport_kind='input-token-count',provider_attempt=1,
            invocation={'call_sequence':1})

    def test_count_and_generation_retain_each_original_role_scope(self):
        actions={'planner':'factory:plan','failure_analyst':'factory:analyze-failure',
                 'builder':'factory:build'}
        for role,action in actions.items():
            for kind in ('input-token-count','responses'):
                row=dict(self.row,role=role,transport_kind=kind)
                self.assertEqual(configured_transport_action(row,'pinned-model',1),action)

    def test_retry_fallback_wrong_role_model_and_sequence_refused(self):
        for update in ({'provider_attempt':2},{'provider_attempt':True},{'role':'verifier'},
                       {'provider':'other'},{'model':'other'},{'transport_kind':'other'},
                       {'invocation':{'call_sequence':2}}, {'invocation':{'call_sequence':True}}):
            with self.assertRaisesRegex(ContractError,'scope-refused'):
                configured_transport_action(dict(self.row,**update),'pinned-model',1)

    def test_data_scope_validation_does_not_mutate_reservation(self):
        original=deepcopy(self.row)
        configured_transport_action(self.row,'pinned-model',1)
        self.assertEqual(self.row,original)

    def test_receipt_cannot_reach_live_controller_or_authorization(self):
        with patch('lightyear_execution.configured_human_controller.verify_configured_controller') as verify:
            with self.assertRaisesRegex(ContractError,'native-controller'):
                require_configured_transport({'status':'passed'},self.row)
            verify.assert_not_called()

    def test_public_or_missing_context_cannot_use_configured_send_guard(self):
        from lightyear_factory.orchestrator import FactoryOrchestrator
        controller=object.__new__(FactoryOrchestrator);controller.execution_context=None
        with self.assertRaisesRegex(ContractError,'native-context'):
            require_configured_transport(controller,self.row)

    def test_native_sink_checks_configured_authority_before_durable_reservation(self):
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'src/lightyear_factory/orchestrator.py').read_text())
        function=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
                      and n.name=='_reserve_model_transport')
        guards=[n.lineno for n in ast.walk(function) if isinstance(n,ast.Call)
                and isinstance(n.func,ast.Name) and n.func.id=='require_configured_transport']
        writes=[n.lineno for n in ast.walk(function) if isinstance(n,ast.Call)
                and isinstance(n.func,ast.Attribute) and n.func.attr=='append']
        self.assertEqual(len(guards),1);self.assertEqual(len(writes),1)
        self.assertLess(guards[0],writes[0])
