"""Result completeness, safe diagnostic projection and public/private boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lightyear_calibration.contracts import seal, CalibrationError
from lightyear_calibration.journey_order import save,RUNS
from lightyear_calibration.qualified_judge import evaluate,STATUSES
from lightyear_calibration.qualified_diagnostics import compiler
from lightyear_calibration.qualified_contract import trace_diagnostics


class Results(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name)/RUNS/'journey-test';self.run.mkdir(parents=True)
        save(self.run/'plan.json',seal({'scenario':'operations'}))
        self.structure=patch('lightyear_calibration.qualified_judge.structural_result',return_value=seal({'passed':True}))
        self.structure.start();self.addCleanup(self.structure.stop)

    def executions(self,code=0):
        for lane in ('oracle','postgresql'):
            save(self.run/'cases/operations/1/execution'/lane/'execution.json',seal({'exit_code':code}))

    def test_missing_capture_always_writes_result(self):
        value=evaluate(self.run);self.assertEqual('insufficient-evidence',value['status']);self.assertTrue((self.run/'gate.json').exists())

    def test_execution_failure_never_calls_private_judge(self):
        self.executions(1)
        def forbidden(*args):raise AssertionError('Must not judge incomplete execution')
        self.assertEqual('execution-failure',evaluate(self.run,verifier=forbidden)['status'])

    def test_unexpected_judge_exception_is_recorded(self):
        self.executions()
        def broken(*args):raise RuntimeError('private sentinel')
        v=evaluate(self.run,verifier=broken);self.assertEqual('judge-error',v['status']);self.assertFalse(v['builder_visible'])
        self.assertEqual('private sentinel',json.loads((self.run/'gate.json').read_text())['error']['message'])

    def test_known_business_failure_is_not_a_judge_crash(self):
        self.executions()
        def wrong(*args):raise CalibrationError('Quantity outcome differs')
        self.assertEqual('business-failure',evaluate(self.run,verifier=wrong)['status'])

    def test_success_is_test_equipment_not_factory_success(self):
        self.executions();v=evaluate(self.run,verifier=lambda _:seal({'passed':True}))
        self.assertEqual('passed',v['status']);self.assertFalse(v['autonomous_success'])

    def test_missing_engine_witness_is_inconclusive(self):
        self.executions();v=evaluate(self.run,verifier=lambda _:seal({'passed':False,'database_observers':{'oracle':{'passed':False}}}))
        self.assertEqual('insufficient-evidence',v['status'])

    def test_corrupt_execution_is_not_business_failure(self):
        self.executions();p=self.run/'cases/operations/1/execution/oracle/execution.json';p.write_text('broken')
        self.assertEqual('judge-error',evaluate(self.run)['status'])


class Diagnostics(unittest.TestCase):
    def test_preserved_ms92_compiler_failures(self):
        fixture=Path(__file__).parent/'fixtures/qualification/compiler-regressions.json'
        for case in json.loads(fixture.read_text(encoding='utf-8')):
            with self.subTest(code=case['expected'][0]['code']):
                self.assertEqual(case['expected'],compiler(case['input']))

    def test_interrupted_trace_is_not_a_missing_field_repair(self):
        from tools.qualification_feedback import export
        with tempfile.TemporaryDirectory() as temporary:
            run=Path(temporary);where=run/'cases/operations/1/execution/oracle'
            save(where/'execution.json',seal({'exit_code':1}))
            (where/'journey.xml').write_text('<properties><entry key="status">failed</entry></properties>')
            declaration={'trace_fields':['status','invoice.id'],'optional_trace_fields':[]}
            self.assertEqual([],export(run,declaration,root=run,api={}))
            save(where/'execution.json',seal({'exit_code':0}))
            out=export(run,declaration,root=run,api={})
            self.assertEqual(['missing-field'],[x['code'] for x in out])

    def test_checked_exception_has_location_without_source_echo(self):
        log='[ERROR] LightyearOperationsTest.java:[17]\n[ERROR] SECRET_ROW\n[ERROR] Unhandled exception type SQLException\n'
        out=compiler(log);self.assertEqual('unhandled-checked-exception',out[0]['code']);self.assertEqual(17,out[0]['line'])
        self.assertNotIn('SECRET_ROW',json.dumps(out))

    def test_compiler_locations_do_not_bleed(self):
        log='LightyearOperationsTest.java:[1]\nunknown error\nLightyearOperationsTest.java:[2]\n[ERROR] Unhandled exception type SQLException'
        out=compiler(log);self.assertEqual([2],[x['line'] for x in out])

    def test_business_message_cannot_escape(self):
        out=compiler('LightyearOperationsTest.java:[3]\n[ERROR] expected: <58.04> but was: <SECRET_ROW>')
        self.assertEqual([],out)

    def test_type_and_import(self):
        for msg,code in [('Type mismatch: cannot convert from String to boolean','incompatible-types'),
                         ('The import org.example.Missing cannot be resolved','unresolved-import')]:
            self.assertEqual(code,compiler('LightyearOperationsTest.java:[1] '+msg)[0]['code'])

    def test_trace_does_not_echo_unknown_names_or_values(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'trace.xml';p.write_text('<properties><entry key="SECRET_KEY">58.04</entry></properties>')
            out=trace_diagnostics(p,{'trace_fields':['status'],'optional_trace_fields':[]})
            self.assertIn({'category':'trace-contract','code':'missing-field','field':'status'},out)
            self.assertNotIn('SECRET',json.dumps(out));self.assertNotIn('58.04',json.dumps(out))


if __name__=='__main__':unittest.main()
