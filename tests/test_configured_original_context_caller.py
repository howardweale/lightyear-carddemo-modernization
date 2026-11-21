"""CI source relations for native caller guards; no admission or execution."""
import ast,os,unittest
from pathlib import Path

class OriginalContextCallerRelations(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.root=Path(__file__).resolve().parents[1]
        tree=ast.parse((self.root/'src/lightyear_factory/orchestrator.py').read_bytes())
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='FactoryOrchestrator')
        self.methods={n.name:n for n in owner.body if isinstance(n,ast.FunctionDef)}

    def check_native_caller(self,module,function):
        # Derive the caller from the actual native class, independently of the
        # observation helper. The public run wrapper delegates to that method.
        callers=[name for name,method in self.methods.items() if any(
            isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and isinstance(n.func.value,ast.Name) and n.func.value.id=='self'
            and n.func.attr=='_context' for n in ast.walk(method))]
        self.assertEqual(len(callers),1)
        wrapper_calls=[n.func.attr for n in ast.walk(self.methods['run']) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
            and n.func.value.id=='self']
        self.assertEqual(wrapper_calls.count(callers[0]),1)
        tree=ast.parse((self.root/('src/lightyear_execution/'+module+'.py')).read_bytes())
        helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
        checked=[]
        for n in ast.walk(helper):
            if not (isinstance(n,ast.Compare) and ast.unparse(n.left)=='parent.f_code'
                    and len(n.ops)==1 and isinstance(n.ops[0],ast.Is)):continue
            right=n.comparators[0]
            self.assertIsInstance(right,ast.Attribute);self.assertEqual(right.attr,'__code__')
            self.assertIsInstance(right.value,ast.Attribute)
            self.assertEqual(ast.unparse(right.value.value),'FactoryOrchestrator')
            checked.append(right.value.attr)
        self.assertEqual(checked,callers)
        relations={ast.unparse(n) for n in ast.walk(helper) if isinstance(n,ast.Compare)}
        self.assertIn("parent.f_locals.get('self') is controller",relations)
        self.assertIn("parent.f_locals.get('order') is order",relations)
        self.assertIn("parent.f_locals.get('workspace') is workspace",relations)
        self.assertIn('caller.f_code is FactoryOrchestrator._context.__code__',relations)

    def test_clean_observer_guard_matches_actual_native_context_caller(self):
        self.check_native_caller('configured_receipt_clean_control','record_original_clean_context')

    def test_answer_stimulus_guard_matches_actual_native_context_caller(self):
        self.check_native_caller('configured_receipt_answer_stimulus','prepare_original_answer_fragment')
