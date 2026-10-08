import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.tsql_scriptdom.coverage_controls_v2 import controls,EXPECTED,SCHEMAS
from lightyear_data.tsql_procedures.coverage_v2 import PgCoverage,SqlCoverage
from lightyear_data.tsql_procedures.native_evidence import sha

class CoverageRevision2Tests(unittest.TestCase):
    def test_revision_two_union_replays_and_rejects_mixed_revisions(self):
        from copy import deepcopy
        from test_tsql_coverage_policy import sql_input
        from lightyear_data.tsql_procedures.coverage_v2 import sql_summary
        from lightyear_data.tsql_procedures.m0_v2 import coverage_union
        raw=sql_input((0,10,15,10,30))
        raw['schema']='tsql-sqlserver-coverage-input/2'
        record={'raw':raw,'summary':sql_summary(raw)}
        self.assertEqual(coverage_union([record])['minimum_module_branch_fraction'],1)
        legacy=deepcopy(record);legacy['raw']['schema']='tsql-sqlserver-coverage-input/1'
        with self.assertRaisesRegex(ValueError,'coverage-mixed-revisions'):
            coverage_union([record,legacy])

    def test_nine_fixed_controls_with_two_new_native_obligations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);c=controls(root)
            self.assertEqual({x['id'] for x in c['procedures']},set(EXPECTED))
            self.assertEqual(c['coverage_schemas'],['dbo','business'])
            for item in c['procedures']:
                self.assertEqual(len(item['cases']),1)
                case=item['cases'][0]
                self.assertEqual((case['id'],case['parameters'],case['repeated_runs']),('single',{},1))
                self.assertIn('source_session',case);self.assertIn('target_session',case)
                for a in item['assets'].values():self.assertEqual(sha((root/a['path']).read_bytes()),a['sha256'])
            business=next(x for x in c['procedures'] if x['id']=='coverage-non-dbo-schema')
            self.assertIn('business.trap',business['calling_convention']['target'])
            self.assertNotIn('dbo.',(root/business['assets']['source']['path']).read_text())
            source_setup=(root/business['assets']['source-setup']['path']).read_text()
            target_setup=(root/business['assets']['target-setup']['path']).read_text()
            self.assertTrue(source_setup.startswith('CREATE SCHEMA business;\nGO\n'))
            self.assertIn('CREATE SCHEMA IF NOT EXISTS business',target_setup)
            view=next(x for x in c['procedures'] if x['id']=='coverage-view-excluded')
            self.assertIn('CREATE VIEW dbo.coverage_view',(root/view['assets']['source-setup']['path']).read_text())
    def test_pg_schema_filter_is_bound_parameter_not_sql_interpolation(self):
        from unittest.mock import Mock
        calls=[]
        def query(c,sql,args=()):
            calls.append((sql,args));return [('2.10',)] if 'extversion' in sql else []
        with patch('lightyear_data.tsql_procedures.coverage_v2.query',side_effect=query):
            PgCoverage(Mock(),SCHEMAS).start()
        sql,args=calls[-1];self.assertIn('ANY(%s)',sql);self.assertEqual(args,(['dbo','business'],))
    def test_sql_views_are_recorded_without_parsing(self):
        from unittest.mock import Mock
        calls=[]
        def query(c,sql,args=()):
            calls.append(sql)
            if "o.type='V'" in sql:return [('dbo','coverage_view','CREATE VIEW dbo.coverage_view AS SELECT 1 value')]
            if '@@SPID' in sql:return [(42,)]
            return []
        with tempfile.TemporaryDirectory() as tmp:
            bridge=Path(tmp)/'bridge';bridge.write_bytes(b'fixture')
            with patch('lightyear_data.tsql_procedures.coverage_v2.query',side_effect=query),patch('subprocess.run',side_effect=AssertionError('no view parser')):
                c=SqlCoverage(Mock(),'fixture',bridge)
        self.assertEqual(c.excluded_views[0]['name'],'dbo.coverage_view')
        self.assertTrue(any("o.type IN ('P','FN','TF','TR')" in sql for sql in calls))
