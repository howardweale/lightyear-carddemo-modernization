from copy import deepcopy
import unittest
from test_tsql_coverage_policy import sql_input
from lightyear_data.tsql_procedures.coverage import sql_summary, pg_summary
from lightyear_data.tsql_procedures.m0 import coverage_union, expand
from lightyear_data.tsql_procedures.corpus import artifacts
from pathlib import Path
import json


class M0AcceptanceTests(unittest.TestCase):
    def record(self, offsets):
        raw=sql_input(offsets)
        return dict(raw=raw,summary=sql_summary(raw))

    def test_declared_cases_union_exact_sites(self):
        a=self.record((0,10,15,30));b=self.record((0,10,30))
        self.assertFalse(a['summary']['eligible'])
        self.assertFalse(b['summary']['eligible'])
        self.assertTrue(coverage_union([a,b])['eligible'])
        self.assertFalse(coverage_union([a,a])['eligible'])

    def test_no_changed_source_or_claimed_counts(self):
        a=self.record((0,10,15,30));b=deepcopy(a)
        b['summary']['eligible']=True
        with self.assertRaisesRegex(ValueError,'replay'):coverage_union([a,b])
        b=deepcopy(a);b['raw']['modules'][0]['definition']='changed'
        with self.assertRaises(ValueError):coverage_union([a,b])

    def test_pg_anonymous_fractions_never_added(self):
        row=dict(stmtid=1,stmtname='SQL statement',exec_stmts=None,lineno=3)
        raw=dict(schema='tsql-postgresql-coverage-input/1',modules=[dict(name='dbo.trap()',definition='body',
            before=[row],after=[dict(row,exec_stmts=1)],branch_fraction=.5)])
        r=dict(raw=raw,summary=pg_summary(raw))
        self.assertFalse(coverage_union([r,r])['eligible'])
        raw=deepcopy(raw);raw['modules'][0]['branch_fraction']=1
        self.assertTrue(coverage_union([r,dict(raw=raw,summary=pg_summary(raw))])['eligible'])

    def test_cases_keep_procedure_bytes(self):
        generated=artifacts(Path(__file__).resolve().parents[1])
        manifest=json.loads(generated['data-modernization/tsql-procedures/corpus.json'])
        cases=expand(manifest['procedures'])
        self.assertEqual(len(cases),45)
        for item in manifest['procedures']:
            for case in item['coverage_scenarios']:
                for role in ('source','correct','wrong'):
                    self.assertEqual(case['assets'][role],item['assets'][role])
        self.assertEqual(sum(i['cases'][0]['repeated_runs']*2 for i in cases),106)


if __name__=='__main__':unittest.main()
