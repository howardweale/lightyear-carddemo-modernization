"""Small synthetic observations test the effect comparator, not native execution."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lightyear_calibration.contracts import seal, CalibrationError
from lightyear_calibration.native_effects import row_delta, compare_observations, capture_rows


def observation(lane, tables=None, structure=None):
    return seal({'lane':lane,'evidence_class':'native-database-observation','structure_query_sha256':'fixture',
                 'tables':tables or {},'structure':structure or {}})


class NativeEffectTests(unittest.TestCase):
    def test_oracle_timezone_offset_is_selected_as_native_text(self):
        statements=[]
        class Cursor:
            description=[('DATENEXTRUN',)]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,statement):statements.append(statement);self.done=False
            def fetchmany(self,size):
                if self.done:return []
                self.done=True;return [('2023-11-06T14:37:45.000000+02:00',)]
        class Connection:
            def cursor(self):return Cursor()
        def metadata(connection,statement):
            if "nested='NO'" in statement:return [{'table_name':'AD_SCHEDULER'}]
            if "LIKE '%TIME ZONE%'" in statement:return [{'table_name':'AD_SCHEDULER','column_name':'DATENEXTRUN','data_type':'TIMESTAMP(6) WITH TIME ZONE'}]
            return []
        with tempfile.TemporaryDirectory() as directory,patch('lightyear_calibration.native_effects.query',metadata):
            root=Path(directory)/'capture';result=capture_rows(Connection(),'oracle',root)
            entry=result['tables']['ad_scheduler']
            with gzip.open(root/entry['raw_file'],'rt') as handle:record=json.loads(handle.readline())
            self.assertEqual('2023-11-06T14:37:45.000000+02:00',record['datenextrun'])
            self.assertTrue(any('TO_CHAR' in sql and 'TZH:TZM' in sql for sql in statements))

    def test_higher_timezone_precision_is_not_silently_truncated(self):
        def metadata(connection,statement):
            if "LIKE '%TIME ZONE%'" in statement:return [{'table_name':'T','column_name':'V','data_type':'TIMESTAMP(9) WITH TIME ZONE'}]
            return []
        with tempfile.TemporaryDirectory() as directory,patch('lightyear_calibration.native_effects.query',metadata):
            with self.assertRaisesRegex(CalibrationError,'precision exceeds'):
                capture_rows(None,'oracle',Path(directory)/'capture')

    def test_row_collector_contract_change_blocks_delta(self):
        before={k:observation(k) for k in ('oracle','postgresql')};after={}
        for k,v in before.items():
            data={key:value for key,value in v.items() if key!='content_sha256'};data['row_query_contract']='new';after[k]=seal(data)
        with self.assertRaisesRegex(CalibrationError,'row observation contract'):
            compare_observations(before,after,{k:{'returncode':0} for k in before})

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
