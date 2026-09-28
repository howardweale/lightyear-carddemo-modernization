"""Every supported envelope version must preserve inspectable terminal results."""
import importlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import seal,CalibrationError
from lightyear_calibration.journey_order import RUNS,save


class Versions(unittest.TestCase):
    def test_all_five_result_classes_remain_persisted_and_private(self):
        for name in ('qualified_judge','qualified_judge_v3'):
            module=importlib.import_module('lightyear_calibration.'+name)
            for desired in ('passed','business-failure','execution-failure','judge-error','insufficient-evidence'):
                with self.subTest(version=module.VERSION,status=desired),tempfile.TemporaryDirectory() as temporary:
                    run=Path(temporary)/RUNS/'journey-test'
                    save(run/'plan.json',seal({'scenario':'operations'}))
                    for lane in ('oracle','postgresql'):
                        if desired=='insufficient-evidence' and lane=='postgresql':continue
                        save(run/'cases/operations/1/execution'/lane/'execution.json',
                             seal({'exit_code':1 if desired=='execution-failure' else 0}))
                    def check(_):
                        if desired=='business-failure':raise CalibrationError('Quantity outcome differs')
                        if desired=='judge-error':raise RuntimeError('PRIVATE EXPECTED VALUE')
                        return seal({'passed':True})
                    with patch.object(module,'structural_result',return_value=seal({'passed':True})):
                        value=module.evaluate(run,verifier=check)
                    self.assertEqual(desired,value['status'])
                    self.assertEqual(value,json.loads((run/'gate.json').read_bytes()))
                    self.assertFalse(value['builder_visible'])
                    self.assertFalse(value['autonomous_success'])


if __name__=='__main__':unittest.main()
