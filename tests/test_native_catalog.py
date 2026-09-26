"""Synthetic catalog fixtures exercise admission; these are not runtime receipts."""
from copy import deepcopy
import hashlib
import unittest
from lightyear_calibration.contracts import CalibrationError, digest, seal
from lightyear_calibration.native_catalog import ORACLE_QUERIES, PG_QUERIES, project_capture, context_from_captures
from lightyear_calibration.sql_gate import compare_pair


def fixture(lane):
    queries = ORACLE_QUERIES if lane=='oracle' else PG_QUERIES
    rows = {k:[] for k in queries}
    rows['identity'] = [{'current_schema':'ADEMPIERE' if lane=='oracle' else 'adempiere'}]
    rows['tables'] = [{'table_name':'ACCOUNTS'}] if lane=='oracle' else [{'table_name':'accounts','table_type':'BASE TABLE'}]
    rows['columns'] = ([{'table_name':'ACCOUNTS','column_name':n,'data_type':'NUMBER','data_precision':10,'data_scale':0,'nullable':'N'} for n in ('ID','AMOUNT')]
        if lane=='oracle' else [{'table_name':'accounts','column_name':n,'data_type':'numeric','numeric_precision':10,'numeric_scale':0,'is_nullable':'NO'} for n in ('id','amount')])
    if lane=='oracle':
        rows['identity'][0]['time_zone'] = '+00:00'
        rows['nls_session'] = [{'parameter':'NLS_NUMERIC_CHARACTERS','value':'.,'}]
    else:
        rows['settings'] = [{'name':k,'setting':v} for k,v in {'search_path':'adempiere','standard_conforming_strings':'on','TimeZone':'Etc/UTC'}.items()]
    return seal({'lane':lane,'evidence_class':'native-catalog-observation','query_set_sha256':digest(queries),'query_errors':[],
        'results':{k:{'sql_sha256':hashlib.sha256(sql.encode()).hexdigest(),'rows':rows[k]} for k,sql in queries.items()}})


def mutate(snapshot, fn):
    data = deepcopy(snapshot); data.pop('content_sha256'); fn(data); return seal(data)


class NativeCatalogTests(unittest.TestCase):
    def test_incomplete_tampered_or_simulated_metadata_never_promotes(self):
        for change in [lambda s:s['results'].pop('triggers'), lambda s:s.update(query_errors=['denied']),
                       lambda s:s.update(evidence_class='simulated'), lambda s:s.update(query_set_sha256='0'*64),
                       lambda s:s['results']['tables'].update(sql_sha256='0'*64)]:
            with self.subTest(change=change),self.assertRaises(CalibrationError):
                project_capture(mutate(fixture('oracle'),change))
        tampered=fixture('oracle');tampered['results']['triggers']['rows'].append({'table_name':'ACCOUNTS'})
        with self.assertRaises(CalibrationError):project_capture(tampered)

    def test_side_effects_and_unknown_types_are_preserved(self):
        cap=mutate(fixture('oracle'),lambda s:s['results']['triggers']['rows'].append({'table_name':'ACCOUNTS','trigger_name':'AUDIT_WRITE'}))
        self.assertTrue(project_capture(cap)['tables']['accounts']['triggers'])
        cap=mutate(fixture('oracle'),lambda s:s['results']['columns']['rows'][0].update(data_type='VARCHAR2'))
        self.assertIsNone(project_capture(cap)['tables']['accounts']['columns']['id']['type'])

    def test_generated_columns_and_rls_without_policies_remain_blockers(self):
        cap=mutate(fixture('postgresql'),lambda s:s['results']['columns']['rows'][0].update(is_generated='ALWAYS'))
        self.assertTrue(project_capture(cap)['tables']['accounts']['constraints'])
        cap=mutate(fixture('postgresql'),lambda s:s['results']['objects']['rows'].append({'relname':'accounts','relrowsecurity':True,'relforcerowsecurity':False}))
        self.assertTrue(project_capture(cap)['tables']['accounts']['row_policies'])

    def test_oracle_view_is_not_a_base_table_and_quoted_name_is_not_folded(self):
        cap=mutate(fixture('oracle'),lambda s:s['results']['views']['rows'].append({'view_name':'V_ACCOUNTS'}))
        self.assertEqual('view',project_capture(cap)['tables']['v_accounts']['kind'])
        cap=mutate(fixture('oracle'),lambda s:s['results']['tables']['rows'].append({'table_name':'MixedName'}))
        self.assertNotIn('mixedname',project_capture(cap)['tables'])

    def test_effective_session_preserved_and_missing_object_remains_unknown(self):
        snaps={lane:fixture(lane) for lane in ('oracle','postgresql')}
        template={'cases':{'a':{'lanes':{lane:{'session':{},'tables':{'accounts':{},'absent':{'complete':False}},'observed_declarations':[]} for lane in snaps}}}}
        ctx=context_from_captures(template,snaps)
        self.assertFalse(ctx['cases']['a']['lanes']['oracle']['tables']['absent']['complete'])
        sql='UPDATE accounts SET amount=5 WHERE id=1;'
        self.assertEqual('equivalent',compare_pair('a',sql,sql,context_case=ctx['cases']['a'],context_enabled=True)['verdict'])
        snaps['postgresql']=mutate(snaps['postgresql'],lambda s:s['results']['settings']['rows'][0].update(setting='adempiere, pg_catalog'))
        ctx=context_from_captures(template,snaps)
        self.assertEqual(['adempiere','pg_catalog'],ctx['cases']['a']['lanes']['postgresql']['session']['search_path'])
        self.assertEqual('indeterminate',compare_pair('a',sql,sql,context_case=ctx['cases']['a'],context_enabled=True)['verdict'])


if __name__=='__main__':unittest.main()
