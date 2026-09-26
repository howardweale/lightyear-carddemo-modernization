"""Negative controls for native schema accounting and enforcement differences."""
from copy import deepcopy
import hashlib
import unittest

from lightyear_calibration.contracts import CalibrationError, digest, seal
from lightyear_calibration.native_catalog import ORACLE_QUERIES, PG_QUERIES
from lightyear_calibration.schema_equivalence import assess, compare_foreign_keys, foreign_keys, compare_keys, key_declarations


def native(lane):
    oracle = lane == 'oracle'
    queries = ORACLE_QUERIES if oracle else PG_QUERIES
    data = {k: [] for k in queries}
    data['identity'] = [{'current_schema': 'ADEMPIERE' if oracle else 'adempiere',
                         'session_user': 'ADEMPIERE' if oracle else 'adempiere', 'time_zone': 'UTC'}]
    if oracle:
        data['nls_session'] = [{'parameter': 'NLS_NUMERIC_CHARACTERS', 'value': '.,'}]
    else:
        data['settings'] = [{'name': k, 'setting': v} for k, v in
                            [('search_path','adempiere, pg_catalog'),('TimeZone','UTC'),('standard_conforming_strings','on')]]
    for i, name in enumerate(('parent', 'child'), 1):
        data['tables'].append({'table_name': name.upper() if oracle else name, 'table_type': 'BASE TABLE'})
        data['columns'].append({'table_name': name.upper() if oracle else name,
                                'column_name': 'ID' if oracle else 'id', 'data_type': 'NUMBER' if oracle else 'numeric',
                                'data_precision': 10, 'data_scale': 0, 'numeric_precision': 10, 'numeric_scale': 0,
                                'nullable': 'N', 'is_nullable': 'NO'})
        if not oracle:
            data['objects'].append({'oid': i, 'relname': name, 'relrowsecurity': False, 'relforcerowsecurity': False})
            data['attributes'].append({'attrelid': i, 'attnum': 1, 'attname': 'id', 'attisdropped': False})
    if oracle:
        data['constraints'] = [
            {'constraint_name':'PK_PARENT','constraint_type':'P','table_name':'PARENT'},
            {'constraint_name':'FK_CHILD','constraint_type':'R','table_name':'CHILD', 'r_owner':'ADEMPIERE',
             'r_constraint_name':'PK_PARENT','delete_rule':'NO ACTION','deferrable':'DEFERRABLE',
             'deferred':'DEFERRED','status':'ENABLED','validated':'VALIDATED'}]
        data['constraint_columns'] = [{'constraint_name': k, 'column_name':'ID','position':1}
                                      for k in ('PK_PARENT','FK_CHILD')]
    else:
        data['constraints'] = [{'oid': 100, 'conname': 'different_fk_name', 'contype':'f','table_name':'child',
                                'conrelid':2,'confrelid':1,'conkey':[1],'confkey':[1],
                                'confdeltype':'a','confupdtype':'a','confmatchtype':'s',
                                'condeferrable':True,'condeferred':True,'convalidated':True}]
        data['triggers'] = [{'table_name': 'child', 'tgconstraint':100,'tgisinternal':True,'tgenabled':'O'} for _ in range(4)]
    return data


def captured(lane, data=None):
    data = data or native(lane)
    queries = ORACLE_QUERIES if lane == 'oracle' else PG_QUERIES
    return seal({'lane':lane,'evidence_class':'native-catalog-observation','query_set_sha256':digest(queries),
                 'import_binding':{'ms84_checkpoint_sha256':'a'*64,'state_sha256':('b' if lane=='oracle' else 'c')*64},
                 'query_errors':[], 'results':{k:{'sql_sha256':hashlib.sha256(sql.encode()).hexdigest(), 'rows':data[k]}
                                              for k,sql in queries.items()}})


class SchemaEquivalenceTests(unittest.TestCase):
    def test_key_column_order_is_retained_without_changing_uniqueness_set(self):
        left = {('roles', 'P', ('role_id', 'user_id')): [{'column_order': ['role_id', 'user_id']}]}
        right = {('roles', 'P', ('role_id', 'user_id')): [{'column_order': ['user_id', 'role_id']}]}
        result = compare_keys(left, right)[0]
        self.assertEqual('column-set-match', result['status'])
        self.assertFalse(result['column_order_matches'])
        self.assertEqual('missing-postgresql', compare_keys(left, {})[0]['status'])

    def test_key_column_omission_cannot_match(self):
        data = native('oracle'); data['constraint_columns'] = [x for x in data['constraint_columns'] if x['constraint_name'] != 'PK_PARENT']
        with self.assertRaises(CalibrationError): key_declarations(data, 'oracle')

    def compare(self, left=None, right=None):
        return compare_foreign_keys(foreign_keys(left or native('oracle'),'oracle'),
                                    foreign_keys(right or native('postgresql'),'postgresql'))

    def test_constraint_names_do_not_define_equivalence(self):
        self.assertEqual('catalog-contract-match', self.compare()[0]['status'])

    def test_missing_relationship_is_not_zero_or_equal(self):
        pg = native('postgresql'); pg['constraints'] = []
        self.assertEqual('missing-postgresql', self.compare(right=pg)[0]['status'])

    def test_delete_update_and_deferred_rules_are_not_suppressed(self):
        for key, value in [('confdeltype','c'),('confupdtype','c'),('confmatchtype','f'),
                           ('condeferrable',False),('condeferred',False)]:
            with self.subTest(key=key):
                pg = native('postgresql'); pg['constraints'][0][key] = value
                self.assertEqual('enforcement-difference',self.compare(right=pg)[0]['status'])

    def test_disabled_or_missing_internal_trigger_is_not_enforced(self):
        for missing in (False, True):
            pg = native('postgresql')
            if missing: pg['triggers'].pop()
            else: pg['triggers'][0]['tgenabled']='D'
            self.assertEqual('enforcement-difference', self.compare(right=pg)[0]['status'])

    def test_both_unvalidated_still_blocks(self):
        oracle, pg = native('oracle'), native('postgresql')
        oracle['constraints'][1]['validated']='NOT VALIDATED';pg['constraints'][0]['convalidated']=False
        self.assertEqual('unenforced-or-unvalidated', self.compare(oracle,pg)[0]['status'])

    def test_column_order_and_referenced_column_are_part_of_identity(self):
        pg = native('postgresql');pg['attributes'].append({'attrelid':1,'attnum':2,'attname':'other_id','attisdropped':False})
        pg['constraints'][0]['confkey']=[2]
        self.assertEqual({'missing-oracle','missing-postgresql'}, {x['status'] for x in self.compare(right=pg)})

    def test_incomplete_or_duplicate_constraint_columns_fail_closed(self):
        for position in (2, 1):
            oracle=native('oracle');oracle['constraint_columns'].append({'constraint_name':'FK_CHILD','column_name':'OTHER','position':position})
            with self.assertRaises(CalibrationError): foreign_keys(oracle,'oracle')

    def test_external_target_requires_its_captured_schema(self):
        oracle=native('oracle');oracle['constraints'][1]['r_owner']='OTHER'
        with self.assertRaises(CalibrationError): foreign_keys(oracle,'oracle')

    def test_duplicate_relationships_remain_reviewable(self):
        oracle=native('oracle');c={**oracle['constraints'][1],'constraint_name':'FK_DUP'}
        oracle['constraints'].append(c);oracle['constraint_columns'].append({'constraint_name':'FK_DUP','column_name':'ID','position':1})
        self.assertEqual('duplicate-relationship-review',self.compare(left=oracle)[0]['status'])

    def test_matching_catalogs_never_promote_unprobed_application_or_schema(self):
        result=assess({lane:captured(lane) for lane in ('oracle','postgresql')})
        self.assertEqual(1,result['counts']['foreign_key_catalog_matches'])
        self.assertFalse(result['schema_equivalence']);self.assertFalse(result['application_equivalence'])
        self.assertTrue(result['remaining_obligations'])

    def test_nullability_and_defaults_are_independently_counted(self):
        pg=native('postgresql');pg['columns'][0].update(is_nullable='YES',column_default='now()')
        result=assess({'oracle':captured('oracle'),'postgresql':captured('postgresql',pg)})
        self.assertEqual(1,result['counts']['nullable_differences'])
        self.assertEqual(1,result['counts']['default_definition_differences'])

    def test_query_missing_or_failed_cannot_be_an_empty_schema(self):
        for mode in ('missing','failed','empty'):
            pair={lane:captured(lane) for lane in ('oracle','postgresql')}
            raw=deepcopy(pair['oracle']);raw.pop('content_sha256')
            if mode=='missing': del raw['results']['views']
            elif mode=='failed': raw['query_errors']=['permission denied']
            else: raw['results']['tables']['rows']=[]
            pair['oracle']=seal(raw)
            with self.assertRaises(CalibrationError):assess(pair)

    def test_tampering_or_simulated_catalog_cannot_acquire_native_claim(self):
        for mode in ('tamper','simulated','lane','lineage'):
            pair={lane:captured(lane) for lane in ('oracle','postgresql')}
            raw=deepcopy(pair['oracle']);raw.pop('content_sha256')
            if mode=='simulated':raw['evidence_class']='simulated'
            elif mode=='lane':raw['lane']='postgresql'
            elif mode=='lineage':raw['import_binding']['ms84_checkpoint_sha256']='d'*64
            else:raw['query_errors']=['error']
            pair['oracle']=raw if mode=='tamper' else seal(raw)
            with self.assertRaises(CalibrationError):assess(pair)
