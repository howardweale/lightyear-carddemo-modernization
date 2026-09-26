"""Small synthetic observations test the effect comparator, not native execution."""
from copy import deepcopy
import unittest
from lightyear_calibration.contracts import seal, CalibrationError
from lightyear_calibration.native_effects import row_delta, compare_observations


def observation(lane, tables=None, structure=None):
    return seal({'lane':lane,'evidence_class':'native-database-observation','structure_query_sha256':'fixture',
                 'tables':tables or {},'structure':structure or {}})


class NativeEffectTests(unittest.TestCase):
    def test_duplicate_rows_are_counted(self):
        self.assertEqual({'removed':{'a':1},'added':{'b':2}},row_delta({'a':2},{'a':1,'b':2}))

    def test_matching_rows_do_not_override_failure_or_schema_changes(self):
        before={k:observation(k) for k in ('oracle','postgresql')}
        after={k:observation(k,{'x':{'rows':1,'row_multiset':{'same':1}}}) for k in before}
        execution={k:{'returncode':0} for k in before}
        result=compare_observations(before,after,execution)
        self.assertEqual('observed-effects-match',result['status'])
        self.assertFalse(result['application_equivalence'])
        self.assertFalse(result['historical_upgrade_equivalence'])
        execution['oracle']['returncode']=1
        self.assertEqual('execution-failed',compare_observations(before,after,execution)['status'])
        execution['oracle']['returncode']=0
        after['oracle']=observation('oracle',after['oracle']['tables'],{'columns':[{'new_type':'NUMBER'}]})
        self.assertEqual('observed-rows-match-structure-review-required',compare_observations(before,after,execution)['status'])

    def test_runtime_registration_values_are_never_suppressed(self):
        before={k:observation(k) for k in ('oracle','postgresql')}
        after={k:observation(k,{'ad_migrationscript':{'rows':1,'row_multiset':{k+'-clock':1}}}) for k in before}
        result=compare_observations(before,after,{k:{'returncode':0} for k in before})
        self.assertEqual('observed-effects-differ',result['status'])
        self.assertTrue(result['non_registration_row_effects_match'])
        self.assertTrue(result['registration_effects_retained'])

    def test_weaker_or_tampered_lane_cannot_produce_native_comparison(self):
        before={k:observation(k) for k in ('oracle','postgresql')}
        after=deepcopy(before);bad=dict(after['oracle']);bad.pop('content_sha256');bad['evidence_class']='simulated';after['oracle']=seal(bad)
        with self.assertRaises(CalibrationError):compare_observations(before,after,{k:{'returncode':0} for k in before})

        after=deepcopy(before);after['oracle']['tables']['bad']={}
        with self.assertRaises(CalibrationError):compare_observations(before,after,{k:{'returncode':0} for k in before})

    def test_same_lane_cannot_be_presented_as_both_engines(self):
        before={k:observation('oracle') for k in ('oracle','postgresql')}
        with self.assertRaisesRegex(CalibrationError,'Mislabeled'):
            compare_observations(before,deepcopy(before),{k:{'returncode':0} for k in before})


if __name__=='__main__':unittest.main()
