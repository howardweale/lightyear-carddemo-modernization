import ast,json,unittest
from pathlib import Path
from unittest.mock import patch
from tools.ms94_equipment import schedule
from tools.ms94_judge import evaluate
from lightyear_calibration.contracts import seal

ROOT=Path(__file__).resolve().parents[1]


class EquipmentTests(unittest.TestCase):
    def test_exact_preregistered_denominators(self):
        slots=schedule();self.assertEqual(len(slots),56)
        for s in ('operations','procure-to-pay'):
            self.assertEqual(sum(x['scenario']==s and x['fault']=='none' for x in slots),10)
        faults={x['fault'] for x in slots}-{'none'};self.assertEqual(len(faults),12)
        for f in faults:self.assertEqual([x['repeat'] for x in slots if x['fault']==f],[1,2,3])

    def test_exception_classification_keeps_unknown_errors_private(self):
        base={'status':'judge-error','passed':False,'error':{'stage':'combined-native-judge',
              'type':'CalibrationError','message':'Operations business boundary failed'}}
        with patch('tools.ms94_judge.read_json',return_value={'scenario':'operations'}),patch('tools.ms94_judge.save'):
            with patch('tools.ms94_judge.original',return_value=seal(base)):
                self.assertEqual(evaluate(Path('test'))['status'],'business-failure')
            base['error']['message']='Unexpected private parser failure'
            with patch('tools.ms94_judge.original',return_value=seal(base)):
                self.assertEqual(evaluate(Path('test'))['status'],'judge-error')

    def test_public_contract_covers_all_unique_row_shapes(self):
        for scenario,module in [('operations','operations_journey'),('procure-to-pay','procurement_journey')]:
            public=json.loads((ROOT/f'factory/idempiere/qualification-ms94/{scenario}-shapes.json').read_text())
            tree=ast.parse((ROOT/f'src/lightyear_calibration/{module}.py').read_text(encoding='utf-8'))
            calls={ast.unparse(n) for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='only'}
            self.assertEqual(calls,set(public['unique_row_selectors']))
            self.assertTrue(public['requirements']);self.assertFalse(public['private_business_expected_values_included'])
        ops=json.loads((ROOT/'factory/idempiere/qualification-ms94/operations-shapes.json').read_text())
        self.assertIn('Two shipment-linked invoice lines are rejected.',' '.join(ops['requirements']))

    def test_closed_reference_only_fault_authority(self):
        from lightyear_calibration.ms94_faults import inject
        for plan in ({'qualification_only':False,'model_calls':0,'fault':'wrong-tax'},
                     {'qualification_only':True,'model_calls':1,'fault':'wrong-tax'}):
            with patch('lightyear_calibration.ms94_faults.read_json',return_value=plan):
                with self.assertRaises(Exception):inject({'fault':'wrong-tax','lane':'oracle'})


if __name__=='__main__':unittest.main()
