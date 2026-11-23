"""CI-only two-phase refusals/ordering; no scanner, context or worker execution."""
import ast,os,unittest
from pathlib import Path
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_human_lifecycle import original_scanner_relations,finalize_configured_controller


class ConfiguredHumanLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.root=Path(__file__).resolve().parents[1]

    def function(self,path,name):
        tree=ast.parse((self.root/path).read_text())
        return next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)

    def test_passed_receipt_cannot_finalize_controller(self):
        with self.assertRaisesRegex(ContractError,'native-controller'):
            finalize_configured_controller({'status':'passed'},object(),object(),object(),object(),'unused')

    def test_arbitrary_scanner_or_objects_cannot_supply_original_relations(self):
        with self.assertRaisesRegex(ContractError,'original-scanner-types'):
            original_scanner_relations(object(),object(),object(),object(),lambda *args:None)

    def test_native_types_do_not_make_a_replacement_scanner_original(self):
        from lightyear_factory.orchestrator import FactoryOrchestrator
        from lightyear_factory.workspace import IsolatedWorkspace
        from lightyear_factory.ledger import RunLedger
        with self.assertRaisesRegex(ContractError,'native-scanner-code'):
            original_scanner_relations(object.__new__(FactoryOrchestrator),object(),
                object.__new__(IsolatedWorkspace),object.__new__(RunLedger),lambda *args:None)

    def test_native_lifecycle_finalizes_after_scanner_and_before_first_role(self):
        function=self.function('src/lightyear_factory/orchestrator.py','_run')
        def lines(name):
            return [n.lineno for n in ast.walk(function) if isinstance(n,ast.Call)
                    and ((isinstance(n.func,ast.Name) and n.func.id==name)
                      or (isinstance(n.func,ast.Attribute) and n.func.attr==name))]
        self.assertEqual(len(lines('finalize_configured_controller')),1)
        self.assertLess(lines('bind_configured_controller')[0],lines('_bind_isolation_scan')[0])
        self.assertLess(lines('_bind_isolation_scan')[0],lines('finalize_configured_controller')[0])
        self.assertLess(lines('finalize_configured_controller')[0],min(lines('_authorize')))

    def test_early_binding_does_not_capture_terminal_origin(self):
        function=self.function('src/lightyear_execution/configured_human_controller.py','bind_configured_controller')
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
            and n.func.id=='capture_configured_terminal_origin' for n in ast.walk(function)))
