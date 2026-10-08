"""Real parser regressions; no engine, container or model execution."""
import json,os,subprocess,unittest
from pathlib import Path
from copy import deepcopy
from lightyear_data.tsql_procedures.postgresql_syntax import contract
from lightyear_data.tsql_procedures.comparison_v9 import compare
from lightyear_data.tsql_procedures.native_evidence import sha
from test_tsql_review import inputs,ast

class PgContracts(unittest.TestCase):
    def setUp(self):
        try:import pglast
        except ImportError:self.skipTest('install .[tsql] for pinned PostgreSQL parser')
    def test_real_target_ast_not_keyword_scan(self):
        for query in ('SELECT x FROM t FETCH FIRST 1 ROW ONLY','SELECT DISTINCT ON(x) x FROM t',
                      'SELECT array_agg(x) FROM t','SELECT statement_timestamp()',
                      "CREATE FUNCTION f() RETURNS SETOF int LANGUAGE plpgsql AS $$BEGIN RETURN QUERY EXECUTE 'SELECT x FROM t LIMIT 1'; END$$"):
            self.assertTrue(contract(query)['policy_obligations'],query)
        self.assertFalse(contract("SELECT 'LIMIT 1' AS x")['policy_obligations'])
    def test_orderless_twin_is_not_accepted_on_accidental_matching_rows(self):
        a,b,m=inputs([])
        a['observation']['source_syntax']['semantic_catalogue']=dict(result_producers_complete=True,result_contracts=[dict(ordered=True,resolved=True,key_indices=[0])])
        s='SELECT value FROM t';b['observation']['target_source']=s;b['baseline']={'procedure_sha256':sha(s.encode())}
        result=compare(a,b,m)
        self.assertEqual(result['verdict'],'divergent')
        self.assertIn('target-order-contract-missing',[d['observable'] for d in result['differences']])
    def test_multiset_difference_survives_unresolved_sort_and_count(self):
        for rules in ([],[dict(ordered=True,resolved=False,key_indices=[-1])]):
            a,b,m=inputs([]);a['observation']['source_syntax']['semantic_catalogue']=dict(result_producers_complete=True,result_contracts=rules)
            b['observation']['result_sets'][0]['rows']=[['wrong']]
            self.assertEqual(compare(a,b,m)['verdict'],'divergent')
    def test_target_qualified_key_never_binds_other_table_column(self):
        r=contract('SELECT h.id FROM h JOIN d ON h.id=d.x ORDER BY d.id')
        self.assertFalse(r['result_contracts'][0]['resolved'])
    def test_datetime_rounding_does_not_hide_wrong_value(self):
        from lightyear_data.tsql_procedures.value_contract import datetime_value
        a=dict(type='datetime',value='2026-10-01T00:00:00.000');b=dict(type='datetime',value='2026-10-01T00:00:00.001')
        self.assertNotEqual(datetime_value(a,'datetime'),datetime_value(b,'datetime'))

    def test_refcursor_and_literal_dynamic_contracts_are_narrow(self):
        root=Path(__file__).resolve().parents[1]/'data-modernization/tsql-procedures/typed-corpus-r1'
        r=contract((root/'multiple-result-sets/correct.sql').read_text())
        self.assertFalse(r['policy_obligations']);self.assertEqual([x['cursor'] for x in r['result_contracts']],['first_set','second_set'])
        self.assertFalse(contract((root/'dynamic-parameter-binding/correct.sql').read_text())['policy_obligations'])
        unsafe="CREATE FUNCTION f() RETURNS int LANGUAGE plpgsql AS $$ DECLARE x int; BEGIN EXECUTE 'SELECT generate_series(1,3)' INTO x; RETURN x; END $$;"
        self.assertIn('target-dynamic-scalar-unresolved',contract(unsafe)['policy_obligations'])

@unittest.skipUnless(os.environ.get('TSQL_BRIDGE'),'requires built ScriptDom bridge')
class ScriptDomContracts(unittest.TestCase):
    def parse(self,sql):
        done=subprocess.run(['dotnet',os.environ['TSQL_BRIDGE']],input=sql,text=True,capture_output=True)
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        return json.loads(done.stdout)['semantic_catalogue']
    def test_nonreturning_queries_and_set_operators(self):
        for query in ('SELECT id FROM t UNION SELECT id FROM u ORDER BY id',
                      'SELECT id FROM t INTERSECT SELECT id FROM u ORDER BY id',
                      'SELECT id FROM t EXCEPT SELECT id FROM u ORDER BY id',
                      '(SELECT id FROM t) ORDER BY id'):
            with self.subTest(query=query):
                rules=self.parse(query)['result_contracts'];self.assertEqual(len(rules),1);self.assertTrue(rules[0]['ordered'])
        r=self.parse('DECLARE c CURSOR FOR SELECT id FROM t; SELECT id INTO #x FROM t; SELECT id FROM t ORDER BY id;')
        self.assertEqual(len(r['result_contracts']),1)
        self.assertEqual(len(self.parse('UPDATE t SET id=1 OUTPUT inserted.id')['result_contracts']),1)
        self.assertEqual(len(self.parse('UPDATE t SET id=1 OUTPUT inserted.id INTO #x')['result_contracts']),0)
    def test_qualified_sort_and_alias(self):
        self.assertFalse(self.parse('SELECT h.id FROM h JOIN d ON h.id=d.x ORDER BY d.id')['result_contracts'][0]['resolved'])
        self.assertTrue(self.parse('SELECT h.id AS value FROM h ORDER BY value')['result_contracts'][0]['resolved'])
    def test_literal_assignment_exec_has_no_result(self):
        r=self.parse("DECLARE @r int; EXEC sp_executesql N'SELECT @r=@p',N'@r int OUTPUT,@p int',@r=@r OUTPUT,@p=1; SELECT @r;")
        self.assertTrue(r['exec_contracts'][0]['no_results_proven'])

    def test_called_procedure_result_contract_from_native_catalogue(self):
        from lightyear_data.tsql_procedures.semantics import contract as source_contract,resolve_results
        def parsed(sql):
            done=subprocess.run(['dotnet',os.environ['TSQL_BRIDGE']],input=sql,text=True,capture_output=True,check=True)
            return json.loads(done.stdout)
        caller='CREATE PROCEDURE dbo.parent AS BEGIN EXEC dbo.child; END;'
        child='CREATE PROCEDURE dbo.child AS BEGIN SELECT id FROM dbo.t ORDER BY id; END;'
        bound=source_contract(parsed(caller));p=parsed(child)
        obs={'dependency_catalogue':dict(modules=[[1,'dbo','child','P',child]],parsed={'1':p})}
        result=resolve_results(bound,obs)
        self.assertFalse(result['policy_obligations']);self.assertEqual(len(result['result_contracts']),1)
        self.assertTrue(result['result_contracts'][0]['ordered'])
        obs['dependency_catalogue']['modules'][0][4]+=' changed'
        with self.assertRaisesRegex(ValueError,'callee-source'):resolve_results(bound,obs)
