import unittest
from lightyear_calibration.contracts import CalibrationError,seal
from lightyear_calibration.ms94_a3_checkpoint_v2 import catalog_binding,RECIPE
from lightyear_calibration.ms94_a3_checkpoint import RECIPE as PRIOR_RECIPE
from tests.test_ms94_a3_checkpoint import CheckpointTransformTests


class CatalogBindingTests(unittest.TestCase):
    def test_shared_predecessor_with_distinct_native_state_bindings(self):
        predecessor=seal({'admitted':True,'prior':'native'})
        states=[seal({'lane':lane}) for lane in ('oracle','postgresql')]
        bindings=[catalog_binding(predecessor,s) for s in states]
        self.assertEqual(bindings[0]['ms84_checkpoint_sha256'],bindings[1]['ms84_checkpoint_sha256'])
        self.assertNotEqual(bindings[0]['state_sha256'],bindings[1]['state_sha256'])
        self.assertEqual(set(bindings[0]),{'ms84_checkpoint_sha256','state_sha256'})
        self.assertEqual(RECIPE,PRIOR_RECIPE)

    def test_unadmitted_or_corrupted_predecessor_is_rejected(self):
        state=seal({'lane':'oracle'})
        for predecessor in (seal({'admitted':False}),{**seal({'admitted':True}),'admitted':False}):
            with self.assertRaises(CalibrationError):catalog_binding(predecessor,state)


if __name__=='__main__':unittest.main()
