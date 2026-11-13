"""CI-only original controller configuration checks; no admitted context or I/O."""
import os
from pathlib import Path
import tempfile
from types import MethodType
import unittest
from lightyear_factory.contracts import ContractError
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_execution.configured_receipt_controller import _require_original_context_inputs


class OriginalContextInputs(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        temp=tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP'])
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        # Original constructor, configuration only. No provider, context,
        # authority registry, controller.run(), assembler or scanner is invoked.
        self.controller=FactoryOrchestrator(root/'source',root/'runs',None)
        self.root=root

    def test_original_default_configuration_returns_no_authority(self):
        self.assertIsNone(_require_original_context_inputs(self.controller))
        self.assertIsNone(self.controller.execution_context)
        for name in ('graph_path','evidence_path','memory_store','approved_projection',
                     'prepare_workspace','feedback_vocabulary'):
            with self.subTest(missing=name):
                delattr(self.controller,name)
                try:
                    with self.assertRaisesRegex(ContractError,'original-context-inputs'):
                        _require_original_context_inputs(self.controller)
                finally:setattr(self.controller,name,None)
        self.assertFalse((self.root/'runs').exists())

    def changed(self,name):
        setattr(self.controller,name,object())
        with self.assertRaisesRegex(ContractError,'original-context-inputs'):
            _require_original_context_inputs(self.controller)
        self.assertFalse((self.root/'runs').exists())

    def test_graph_path_substitution_refused(self):self.changed('graph_path')
    def test_evidence_path_substitution_refused(self):self.changed('evidence_path')
    def test_memory_store_substitution_refused(self):self.changed('memory_store')
    def test_approved_projection_substitution_refused(self):self.changed('approved_projection')
    def test_early_workspace_callback_substitution_refused(self):self.changed('prepare_workspace')
    def test_feedback_vocabulary_substitution_refused(self):self.changed('feedback_vocabulary')

    def test_instance_context_and_scan_method_substitutions_refused_without_call(self):
        called=[]
        def changed(owner,*args,**kwargs):called.append(True)
        for name in ('_context','_scan_controller_value'):
            with self.subTest(name=name):
                setattr(self.controller,name,MethodType(changed,self.controller))
                try:
                    with self.assertRaisesRegex(ContractError,'original-context-method'):
                        _require_original_context_inputs(self.controller)
                finally:delattr(self.controller,name)
        self.assertEqual(called,[])

    def test_unrelated_object_cannot_supply_controller_configuration(self):
        with self.assertRaisesRegex(ContractError,'native-context-input-owner'):
            _require_original_context_inputs(object())
