"""Adversarial checks for the explicit runtime-value policy, not native runs."""
import unittest
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from lightyear_calibration.contracts import canonical,digest,seal,CalibrationError
from lightyear_calibration.native_reconciliation import field_rule, valid_uuid, reconcile, POLICY, MAINTENANCE_POLICY, HISTORY_POLICY, exact_decimal, reapplication_rule


def snapshot(root,lane,records):
    root.mkdir();tables={}
    for table,values in records.items():
        data=b''.join(canonical(v)+b'\n' for v in values);file=table+'.gz'
        (root/file).write_bytes(gzip.compress(data,mtime=0))
        tables[table]={'rows':len(values),'row_multiset':{digest(v):1 for v in values},'raw_file':file,'raw_file_sha256':hashlib.sha256((root/file).read_bytes()).hexdigest()}
    for table in POLICY['engine_only_tables'][lane]:tables[table]={'rows':0,'row_multiset':{}}
    value=seal({'lane':lane,'evidence_class':'native-database-observation','tables':tables,'structure':{'columns':[{'table_name':table,'column_name':key} for table,values in records.items() for key in (values[0] if values else ['id','amount'])]}})
    (root/'state.json').write_text(json.dumps(value));return root


class ReconciliationRulesTests(unittest.TestCase):
    def rule(self, table, column, left, right, **options):
        args=dict(script='migration.sql', windows={'oracle':{'started_at':'2026-09-26T01:00:00.100000+00:00','finished_at':'2026-09-26T01:00:02+00:00'},
                                                 'postgresql':{'started_at':'2026-09-26T01:00:00.100000+00:00','finished_at':'2026-09-26T01:00:02+00:00'}},new_row=True)
        args.update(options)
        row={'name':'migration.sql','status':'CO','isapply':'Y'}
        return field_rule(table,column,left,right,row,row,**args)

    def test_different_registration_names_require_exact_executed_pair(self):
        names={'oracle':'a.sql','postgresql':'b.sql'}
        a={'name':'a.sql','filename':'oracle/a.sql','status':'CO','isapply':'Y'}
        b={'name':'b.sql','filename':'postgresql/b.sql','status':'CO','isapply':'Y'}
        args=dict(script='a.sql',windows=None,new_row=True,policy=HISTORY_POLICY,script_names=names)
        self.assertEqual('paired-executed-registration-name-or-path',field_rule('ad_migrationscript','name','a.sql','b.sql',a,b,**args))
        self.assertIsNone(field_rule('ad_migrationscript','name','a.sql','wrong.sql',a,{**b,'name':'wrong.sql'},**args))
        self.assertIsNone(field_rule('ad_migrationscript','name','a.sql','b.sql',a,{**b,'status':'ER'},**args))

    def test_registration_checks_exact_lane_path_and_script(self):
        self.assertEqual('engine-registration-path',self.rule('ad_migrationscript','filename','oracle/migration.sql','postgresql/migration.sql'))
        self.assertIsNone(self.rule('ad_migrationscript','filename','oracle/other.sql','postgresql/migration.sql'))
        self.assertIsNone(self.rule('ad_migrationscript','status','CO','ER'))
        self.assertIsNone(self.rule('ad_migrationscript','filename','oracle/migration.sql','postgresql/migration.sql',new_row=False))

    def test_generated_uuid_requires_new_unique_valid_values(self):
        a,b='5c58d01a-e425-0765-e063-020011ac7071','01a0db16-8e4d-7c5e-9378-8f6f835030de'
        self.assertTrue(valid_uuid(a));self.assertFalse(valid_uuid('00000000-0000-0000-0000-000000000000'))
        self.assertEqual('fresh-unique-generated-UUID',self.rule('ad_treenodemm','ad_treenodemm_uu',a,b,unique_uuid=True))
        self.assertIsNone(self.rule('ad_treenodemm','ad_treenodemm_uu',a,b,unique_uuid=False))
        self.assertIsNone(self.rule('ad_column','ad_column_uu',a,b,unique_uuid=True))
        self.assertIsNone(self.rule('ad_treenodemm','ad_treenodemm_uu',a,'bad',unique_uuid=True))

    def test_clock_requires_recorded_window_and_narrow_field(self):
        a,b='2026-09-26T01:00:00','2026-09-26T01:00:00.54321'
        self.assertEqual('timestamp-within-recorded-native-execution',self.rule('ad_treenodemm','created',a,b))
        self.assertIsNone(self.rule('ad_treenodemm','created','2020-01-01T00:00:00',b))
        self.assertIsNone(self.rule('ad_treenodemm','created',a,b,new_row=False))
        self.assertIsNone(self.rule('ad_column','updated',a,b))
        self.assertIsNone(self.rule('ad_treenodemm','created',a,'2026-09-26T01:00:00.050000'))

    def test_historical_existing_tree_clock_remains_bounded(self):
        a,b='2026-09-26T01:00:00','2026-09-26T01:00:00.54321'
        self.assertEqual('timestamp-within-recorded-native-execution',self.rule('ad_treenodemm','updated',a,b,new_row=False,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('ad_treenodemm','created',a,b,new_row=False,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('ad_treenodemm','updated','2020-01-01T00:00:00',b,new_row=False,policy=HISTORY_POLICY))

    def test_history_translation_uuid_requires_a_fresh_unique_row(self):
        a,b='5c58d01a-e425-0765-e063-020011ac7071','01a0db16-8e4d-7c5e-9378-8f6f835030de'
        self.assertEqual('fresh-unique-generated-UUID',self.rule('ad_message_trl','ad_message_trl_uu',a,b,unique_uuid=True,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('ad_message_trl','ad_message_trl_uu',a,b,unique_uuid=True,new_row=False,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('ad_message_trl','msgtext','From','To',policy=HISTORY_POLICY))

    def test_column_update_clock_does_not_admit_literal_or_business_differences(self):
        a,b='2026-09-26T01:00:01','2026-09-26T01:00:02'
        self.assertEqual('timestamp-within-recorded-native-execution',self.rule('ad_column','updated',a,b,new_row=False,policy=HISTORY_POLICY))
        self.assertEqual('timestamp-within-recorded-native-execution',self.rule('ad_printformatitem','updated',a,b,new_row=False,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('ad_printformatitem','seqno',1,2,new_row=False,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('ad_column','updated','2021-09-27T11:38:02',b,new_row=False,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('ad_column','created',a,b,new_row=False,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('ad_column','readonlylogic','N',None,new_row=False,policy=HISTORY_POLICY))

    def test_account_metadata_clocks_do_not_relax_existing_creation_or_amounts(self):
        a,b='2026-09-26T01:00:00','2026-09-26T01:00:00.54321'
        self.assertEqual('timestamp-within-recorded-native-execution',self.rule('m_product_acct','created',a,b,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('m_product_acct','created',a,b,new_row=False,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('m_product_acct','balance',10,11,policy=HISTORY_POLICY))
        self.assertIsNone(self.rule('c_charge_acct','updated','2020-01-01T00:00:00',b,new_row=False,policy=HISTORY_POLICY))

    def test_decimal_equality_is_exact_and_finite(self):
        self.assertTrue(exact_decimal({'decimal':'23.9'},{'decimal':'23.90'}))
        self.assertFalse(exact_decimal({'decimal':'23.9'},{'decimal':'23.9001'}))
        self.assertFalse(exact_decimal({'decimal':'NaN'},{'decimal':'NaN'}))
        self.assertFalse(exact_decimal('23.9',{'decimal':'23.9'}))

    def test_reapplication_audit_requires_exact_calls_and_preserves_other_lane(self):
        name='old.sql';statement="SELECT register_migration_script('old.sql') FROM dual"
        call={'started_at':'2026-09-26T01:00:00+00:00','finished_at':'2026-09-26T01:00:02+00:00',
              'statement_sha256':hashlib.sha256(statement.encode()).hexdigest(),'function_return':name+' was already applied'}
        proof=seal({'script':name,'calls':{'oracle':[call],'postgresql':[]},'native_function_contract':'coalesce-description-space-append-reapplied-and-update-clock'})
        old={lane:{'name':name,'status':'CO','isapply':'Y','description':None,'updated':'2020-01-01T00:00:00'} for lane in ('oracle','postgresql')}
        self.assertTrue(reapplication_rule('description','  reapplied',None,old,proof))
        self.assertFalse(reapplication_rule('description','  reapplied reapplied',None,old,proof))
        self.assertFalse(reapplication_rule('description','  reapplied','  reapplied',old,proof))
        self.assertTrue(reapplication_rule('updated','2026-09-26T01:00:01','2020-01-01T00:00:00',old,proof))
        self.assertFalse(reapplication_rule('updated','2026-09-26T01:00:03','2020-01-01T00:00:00',old,proof))
        self.assertFalse(reapplication_rule('filename','oracle/old.sql','postgresql/old.sql',old,proof))

    def test_timezone_requires_both_native_offsets_and_equal_instant(self):
        a,b='2023-11-06T14:37:45.000000+00:00','2023-11-06T15:37:45+01:00'
        self.assertEqual('native-timestamptz-same-instant',self.rule('ad_scheduler','datenextrun',a,b,utc_column_verified=True))
        self.assertIsNone(self.rule('ad_scheduler','datenextrun',a,b))
        self.assertIsNone(self.rule('ad_scheduler','datenextrun','2023-11-06T14:37:45',b,utc_column_verified=True))
        self.assertIsNone(self.rule('ad_scheduler','datenextrun',a,'2023-11-06T14:37:45+01:00',utc_column_verified=True))

    def test_text_and_business_values_are_not_normalized(self):
        self.assertIsNone(self.rule('ad_column','help','hello\nworld','hello\r\nworld'))
        self.assertIsNone(self.rule('ad_sequence','currentnext',100,101))
        self.assertIsNone(self.rule('account','amount',1,2))

    def test_maintenance_updated_exception_is_narrow_and_time_bounded(self):
        a,b='2026-09-26T01:00:00','2026-09-26T01:00:00.54321'
        self.assertEqual('timestamp-within-recorded-native-execution',self.rule('ad_field','updated',a,b,new_row=False,policy=MAINTENANCE_POLICY))
        self.assertIsNone(self.rule('ad_field','created',a,b,new_row=False,policy=MAINTENANCE_POLICY))
        self.assertIsNone(self.rule('account','updated',a,b,new_row=False,policy=MAINTENANCE_POLICY))
        self.assertIsNone(self.rule('ad_field','updated','2020-01-01T00:00:00',b,new_row=False,policy=MAINTENANCE_POLICY))

    def test_native_checkpoint_blocks_business_drift_and_tampered_raw_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);keys={lane:{'account':['id']} for lane in ('oracle','postgresql')}
            before={lane:snapshot(root/lane,lane,{'account':[{'id':1,'amount':10}]}) for lane in keys}
            prior=reconcile(before,keys);self.assertTrue(prior['admitted'])
            after={lane:snapshot(root/('after-'+lane),lane,{'account':[{'id':1,'amount':20 if lane=='oracle' else 21}]}) for lane in keys}
            result=reconcile(after,keys,before=before,prior=prior)
            self.assertFalse(result['admitted']);self.assertEqual('amount',result['unresolved_differences'][0]['column'])
            (after['oracle']/'account.gz').write_bytes(b'changed')
            with self.assertRaisesRegex(CalibrationError,'Raw rows changed'):reconcile(after,keys,before=before,prior=prior)

    def test_mixed_row_capture_contracts_block_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);keys={lane:{'account':['id']} for lane in ('oracle','postgresql')}
            folders={lane:snapshot(root/lane,lane,{'account':[{'id':1,'amount':10}]}) for lane in keys}
            path=folders['oracle']/'state.json';value=json.loads(path.read_text());value.pop('content_sha256');value['row_query_contract']='different-contract';path.write_text(json.dumps(seal(value)))
            with self.assertRaisesRegex(CalibrationError,'Mixed row observation'):reconcile(folders,keys)

    def test_boolean_is_not_implicitly_equal_to_numeric_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);keys={lane:{'account':['id']} for lane in ('oracle','postgresql')}
            folders={lane:snapshot(root/lane,lane,{'account':[{'id':1,'amount':0 if lane=='oracle' else False}]}) for lane in keys}
            result=reconcile(folders,keys)
            self.assertFalse(result['admitted'])
            self.assertEqual('amount',result['unresolved_differences'][0]['column'])

    def test_prior_checkpoint_is_bound_to_actual_before_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);keys={lane:{'account':['id']} for lane in ('oracle','postgresql')}
            before={lane:snapshot(root/lane,lane,{'account':[{'id':1,'amount':10}]}) for lane in keys}
            prior=reconcile(before,keys)
            other={lane:snapshot(root/('other-'+lane),lane,{'account':[{'id':1,'amount':11}]}) for lane in keys}
            with self.assertRaisesRegex(CalibrationError,'Prior checkpoint differs'):reconcile(other,keys,before=other,prior=prior)


    def test_primary_key_expansion_retains_only_unchanged_bound_witnesses(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);before={};after={};values={'oracle':'a','postgresql':'b'}
            for lane in values:
                records={'meta':[{'id':1,'client':0,'token':values[lane]}]}
                before[lane]=snapshot(root/('before-'+lane),lane,records)
                after[lane]=snapshot(root/('after-'+lane),lane,records)
                path=before[lane]/'state.json';value=json.loads(path.read_text())
                value['structure']['constraints']=([{'table_name':'META','constraint_name':'META_PK','constraint_type':'P'}] if lane=='oracle' else [{'table_name':'meta','definition':'PRIMARY KEY (id)'}])
                if lane=='oracle':value['structure']['index_columns']=[{'table_name':'META','index_name':'META_PK','column_name':'ID','column_position':1}]
                value.pop('content_sha256');path.write_text(json.dumps(seal(value)))
            prior=seal({'admitted':True,'policy_sha256':digest(POLICY),'state_sha256':{lane:json.loads((p/'state.json').read_text())['content_sha256'] for lane,p in before.items()},'allowed_differences':[{'table':'meta','key':'[1]','column':'token','oracle':'a','postgresql':'b','rule':'previously-verified-test-witness'}]})
            keys={lane:{'meta':['id','client']} for lane in values}
            result=reconcile(after,keys,before=before,prior=prior)
            self.assertTrue(result['admitted'])
            self.assertEqual('[1,0]',result['allowed_differences'][0]['key'])
            self.assertEqual('[1]',result['allowed_differences'][0]['previous_key'])
            changed=snapshot(root/'changed','oracle',{'meta':[{'id':1,'client':0,'token':'changed'}]})
            result=reconcile({**after,'oracle':changed},keys,before=before,prior=prior)
            self.assertFalse(result['admitted'])
            unobserved={**before,'oracle':snapshot(root/'unobserved','oracle',{'meta':[{'id':1,'client':0,'token':'a'}]})}
            prior.pop('content_sha256');prior['state_sha256']={lane:json.loads((p/'state.json').read_text())['content_sha256'] for lane,p in unobserved.items()};prior=seal(prior)
            self.assertFalse(reconcile(after,keys,before=unobserved,prior=prior)['admitted'])

    def test_dual_view_must_be_the_exact_native_constant_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);keys={lane:{'account':['id']} for lane in ('oracle','postgresql')}
            folders={lane:snapshot(root/lane,lane,{'account':[{'id':1,'amount':10}]}) for lane in keys}
            path=folders['postgresql']/'state.json';value=json.loads(path.read_text());value.pop('content_sha256')
            value['structure']['views']=[{'viewname':'dual','definition':" SELECT 'X'::character varying AS dummy;"}];path.write_text(json.dumps(seal(value)))
            self.assertTrue(reconcile(folders,keys,policy=HISTORY_POLICY)['admitted'])
            value['structure']['views'][0]['definition']="SELECT 'X'::character varying AS dummy WHERE FALSE;";path.write_text(json.dumps(seal(value)))
            self.assertFalse(reconcile(folders,keys,policy=HISTORY_POLICY)['admitted'])

    def test_same_instant_inference_requires_native_types_and_offset_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);keys={lane:{'ad_scheduler':['id']} for lane in ('oracle','postgresql')}
            folders={lane:snapshot(root/lane,lane,{'ad_scheduler':[{'id':1,'datenextrun':('2023-11-06T14:37:45.000000+00:00' if lane=='oracle' else '2023-11-06T14:37:45+00:00')}]}) for lane in keys}
            for lane,path in folders.items():
                file=path/'state.json';v=json.loads(file.read_text());v.pop('content_sha256');v['row_query_contract']='all-columns-v2-preserve-native-timezone-offsets'
                for c in v['structure']['columns']:
                    if c['column_name']=='datenextrun':c['data_type']='TIMESTAMP(6) WITH TIME ZONE' if lane=='oracle' else 'timestamp with time zone'
                file.write_text(json.dumps(seal(v)))
            self.assertTrue(reconcile(folders,keys)['admitted'])
            file=folders['oracle']/'state.json';v=json.loads(file.read_text());v.pop('content_sha256')
            for c in v['structure']['columns']:c['data_type']='VARCHAR2'
            file.write_text(json.dumps(seal(v)))
            self.assertFalse(reconcile(folders,keys)['admitted'])

if __name__=='__main__':unittest.main()
