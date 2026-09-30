import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import seal
from lightyear_calibration.journey_order import RUNS
from tools import ms94_v6_gate as gate


class ContractGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.run=self.root/RUNS/'journey-test'
        self.run.mkdir(parents=True)
        contract=self.root/'factory/idempiere/qualification-ms94-v3/public/operations.json'
        contract.parent.mkdir(parents=True)
        contract.write_text(json.dumps({'trace_fields':['order.id','invoice.id'],'optional_trace_fields':[]}))
        (self.run/'plan.json').write_text(json.dumps(seal({'judge_version':gate.VERSION,
            'equipment_revision':gate.EQUIPMENT_REVISION,'scenario':'operations','inputs_sha256':{}})))
        for lane in gate.LANES:
            d=self.run/'cases/operations/1/execution'/lane;d.mkdir(parents=True)
            (d/'execution.json').write_text(json.dumps(seal({'exit_code':0})))
            (d/'journey.xml').write_text('<properties><entry key="order.id">1</entry><entry key="invoice.id">2</entry></properties>')

    def test_nonnumeric_id_never_enters_business_judge(self):
        for p in self.run.glob('cases/*/*/execution/*/journey.xml'):
            p.write_text(p.read_text().replace('>1<','>private-bad-id<'))
        with patch.object(gate,'base_evaluate') as base:
            result=gate.evaluate(self.run);base.assert_not_called()
        self.assertEqual(result['status'],'contract-violation')
        self.assertNotIn('private-bad-id',json.dumps(result))

    def test_missing_candidate_trace_nonvoid(self):
        for p in self.run.glob('cases/*/*/execution/*/journey.xml'):p.unlink()
        self.assertEqual(gate.evaluate(self.run)['status'],'contract-violation')

    def test_missing_execution_stays_insufficient(self):
        (self.run/'cases/operations/1/execution/oracle/execution.json').unlink()
        with patch.object(gate,'base_evaluate',return_value={'status':'insufficient-evidence','passed':False,'checks':{}}):
            self.assertEqual(gate.evaluate(self.run)['status'],'insufficient-evidence')

    def test_one_lane_runtime_error_takes_precedence(self):
        (self.run/'cases/operations/1/execution/oracle/execution.json').write_text(json.dumps(seal({'exit_code':1})))
        (self.run/'cases/operations/1/execution/postgresql/journey.xml').unlink()
        with patch.object(gate,'base_evaluate',return_value={'status':'execution-failure','passed':False,'checks':{}}):
            self.assertEqual(gate.evaluate(self.run)['status'],'execution-failure')

    def test_healthy_observer_missing_witness_is_contract_failure(self):
        base={'status':'insufficient-evidence','passed':False,'checks':{'combined':{'database_observers':
            {lane:{'rollback_observed':False,'lock_wait_observed':True} for lane in gate.LANES}}}}
        with patch.object(gate,'base_evaluate',return_value=base):
            self.assertEqual(gate.evaluate(self.run)['status'],'contract-violation')

    def test_broken_observer_is_not_candidate_failure(self):
        base={'status':'judge-error','passed':False,'checks':{},'error':{'stage':'combined-native-judge'}}
        with patch.object(gate,'base_evaluate',return_value=base):
            self.assertEqual(gate.evaluate(self.run)['status'],'judge-error')

    def test_old_plan_cannot_be_reinterpreted(self):
        (self.run/'plan.json').write_text(json.dumps(seal({'judge_version':gate.VERSION,'scenario':'operations','inputs_sha256':{}})))
        with self.assertRaises(Exception):gate.evaluate(self.run)

if __name__=='__main__':unittest.main()
