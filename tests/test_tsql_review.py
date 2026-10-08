"""Regression cases are synthetic offline evidence, never native qualification."""
import unittest
from copy import deepcopy
from test_tsql_native import lane
from lightyear_data.tsql_procedures.comparison_v6 import compare
from lightyear_data.tsql_procedures.semantics import contract
from lightyear_data.tsql_procedures.policy import profile
from lightyear_data.tsql_procedures.value_contract import error_equivalent, result_sets
from lightyear_data.tsql_procedures.invocation import bind
from lightyear_data.tsql_procedures.casegen import generate,shrink

def node(kind,start=0,size=100):return dict(kind=kind,start_utf16=start,length_utf16=size,line=1)
def ast(nodes):return dict(schema='tsql-scriptdom/1',parsed=True,errors=[],input_sha256='a'*64,
    version='synthetic',ast_nodes=nodes)
def inputs(nodes,family=1):
    a,b=lane('sqlserver'),lane('postgresql')
    a['baseline']={'procedure_sha256':'a'*64}
    a['observation']['source_syntax']=ast(nodes)
    mapping=profile(dict(id='customer-arbitrary-name',trap_family=family,assets={},calling_convention={}))
    return a,b,mapping

class ReviewTests(unittest.TestCase):
    def test_inventory_named_typed_parameters(self):
        item=dict(procedure_contract=dict(schema='business',name='calculate',parameters=[
            dict(name='@x',type='int',output=False,has_default=False)]),cases=[dict(parameters={'x':-7})])
        self.assertEqual(bind(item)[0],'[business].[calculate]')
        self.assertEqual(bind(item)[1][0]['value'],-7)
        item['cases'][0]['parameters']={'x':'7'}
        with self.assertRaisesRegex(ValueError,'integer-type'):bind(item)
    def test_case_generation_and_same_failure_shrinking(self):
        cases=generate([dict(name='x',type='int')],{'x':7},branch_values={'x':[42]})
        self.assertIn({'x':42},[c['parameters'] for c in cases])
        result=shrink({'x':12345},'wrong-return',lambda case:'wrong-return' if case['x']==1 else 'another-error')
        self.assertEqual(result['case'],{'x':1})
    def test_order_is_not_sorted_away(self):
        a,b,m=inputs([node('OrderByClause')])
        a['observation']['result_sets'][0]['rows']=[[None],['a'],['B']]
        b['observation']['result_sets'][0]['rows']=[['B'],['a'],[None]]
        r=compare(a,b,m)
        self.assertEqual(r['verdict'],'divergent')
        self.assertEqual(r['differences'][0]['trap_family'],26)
        a['observation']['source_syntax']=ast([])
        self.assertFalse(compare(a,b,m)['differences'])
    def test_policy_comes_from_syntax_not_label(self):
        a,b,m=inputs([node('UpdateSpecification'),node('FromClause',30,20)])
        self.assertIn('update-from-cardinality-unproven',[x['observable'] for x in compare(a,b,m)['unresolved']])
        b['observation']['result_sets'][0]['rows']=[['impossible']]
        self.assertEqual(compare(a,b,m)['verdict'],'divergent')
        a,b,m=inputs([],18)
        self.assertNotIn('unordered-choice-policy-required',[x['observable'] for x in compare(a,b,m)['unresolved']])
    def test_nested_order_does_not_order_outer_top(self):
        r=contract(ast([node('SelectStatement'),node('QuerySpecification'),node('TopRowFilter',2,5),
            node('QuerySpecification',40,40),node('OrderByClause',60,10)]))
        self.assertEqual(r['policy_obligations'][0]['kind'],'unordered-top')
    def test_syntax_hash_binding(self):
        a,b,m=inputs([]);a['baseline']['procedure_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'syntax-source'):compare(a,b,m)
    def test_unknown_return_is_unsupported_not_divergent(self):
        a,b,m=inputs([]);b['observation'].update(return_code=None,return_contract_supported=False)
        r=compare(a,b,m)
        self.assertFalse(r['differences'])
        self.assertIn('unmapped-return-contract',[x['observable'] for x in r['unresolved']])
    def test_error_map_is_explicit_and_ambiguous_547_stays_closed(self):
        self.assertTrue(error_equivalent({'number':2627},{'sqlstate':'23505'},{}))
        self.assertFalse(error_equivalent({'number':8134},{'sqlstate':'23505'},{}))
        self.assertIsNone(error_equivalent({'number':547},{'sqlstate':'23503'},{}))
        self.assertIsNone(error_equivalent({'number':547},{'sqlstate':'23503'},{'constraint_kind':'foreign-key'}))
        self.assertTrue(error_equivalent({'number':547,'message':'conflicted with FOREIGN KEY constraint'},{'sqlstate':'23503'},{}))
        self.assertIsNone(error_equivalent({'number':50000},{'sqlstate':'P0001'},{}))
    def test_types_retain_numeric_values(self):
        a=lane('sqlserver')['observation'];a['result_sets'][0]['columns'][0]['type_code']='106'
        a['result_sets'][0]['rows']=[[{'type':'decimal','value':'1.2300'}]]
        self.assertEqual(result_sets(a,'sqlserver')[0]['rows'],[[{'type':'decimal','value':'1.23'}]])
        text='12345678901234567890123456789012345.6700'
        a['result_sets'][0]['rows']=[[{'type':'decimal','value':text}]]
        self.assertEqual(result_sets(a,'sqlserver')[0]['rows'][0][0]['value'],text[:-2])
    def test_extended_table_type_contract_and_unknowns(self):
        from lightyear_data.tsql_procedures.value_contract import table_contract
        a={'engine':'sqlserver','tables':{'t':{'columns':[['x','decimal',17,38,9,True]],'primary_key':[]}}}
        b={'engine':'postgresql','tables':{'t':{'columns':[['x','numeric(38,9)',False,False]],'primary_key':[]}}}
        self.assertEqual(table_contract(a),table_contract(b))
        b['tables']['t']['columns'][0][1]='my_custom_domain'
        with self.assertRaisesRegex(ValueError,'unmapped-table'):table_contract(b)
    def test_coverage_v2_schema_selection_and_v1_is_fixed(self):
        from lightyear_data.tsql_procedures.native import NativeEngine
        from lightyear_data.tsql_procedures.coverage_v2 import PgCoverage
        with self.assertRaisesRegex(ValueError,'schema-fixed'):
            NativeEngine('postgresql',None,'lytsql_123456789abc',coverage_schemas=('business',))
        engine=NativeEngine('postgresql',None,'lytsql_123456789abc',coverage_revision=2,coverage_schemas=('business',))
        self.assertEqual(engine.coverage_schemas,('business',))
        with self.assertRaisesRegex(ValueError,'coverage-schemas'):PgCoverage(None,())
    def test_tower_policy_cannot_accept_unbound_or_unsigned_decision(self):
        from lightyear_data.tsql_procedures.tower_policy import admit,bindings
        with self.assertRaisesRegex(ValueError,'bindings'):
            admit({},b'',{},scope='fixture',head='a'*64,now=None)
        with self.assertRaises(Exception):
            admit({},b'',bindings({}, {}, {}, {}),scope='fixture',head='a'*64,now=None)

if __name__=='__main__':unittest.main()

class SecondReviewTests(unittest.TestCase):
    def test_exec_and_dynamic_results_cannot_be_equivalent_by_multiset(self):
        for kind in ('ExecuteStatement','ExecutableProcedureReference','ExecutableStringList'):
            a,b,m=inputs([node(kind)])
            a['observation']['result_sets'][0]['rows']=[[None],['a'],['B']]
            b['observation']['result_sets'][0]['rows']=[['B'],['a'],[None]]
            r=compare(a,b,m)
            self.assertNotEqual(r['verdict'],'equivalent')
            self.assertIn('unresolved-exec-result-origin',[v['observable'] for v in r['unresolved']])

    def test_schema_types_and_error_classes(self):
        from lightyear_data.tsql_procedures.value_contract import table_contract
        for source,target in [('datetime','timestamp without time zone'),('smalldatetime','timestamp without time zone'),
            ('float','double precision'),('real','real'),('text','text'),('ntext','text'),('rowversion','bytea')]:
            a={'engine':'sqlserver','tables':{'t':{'columns':[['x',source,8,53,0,True]],'primary_key':[]}}}
            b={'engine':'postgresql','tables':{'t':{'columns':[['x',target,False,False]],'primary_key':[]}}}
            with self.subTest(source=source):self.assertEqual(table_contract(a),table_contract(b))
        for number,state in [(8152,'22001'),(2628,'22001'),(8115,'22003'),(1205,'40P01')]:
            self.assertTrue(error_equivalent({'number':number},{'sqlstate':state},{}))
        self.assertTrue(error_equivalent({'number':50000,'message':'business rule'},{'sqlstate':'P0001','message':'business rule'},{}))
        self.assertFalse(error_equivalent({'number':50000,'message':'business rule'},{'sqlstate':'P0001','message':'other'},{}))

    def test_datetime_ticks_and_exact_decimal_table_values(self):
        from lightyear_data.tsql_procedures.value_contract import datetime_value
        def dt(text):return dict(type='datetime',value='2026-10-01T00:00:00.'+text)
        self.assertEqual(datetime_value(dt('003000'),'datetime'),datetime_value(dt('003333'),'datetime'))
        self.assertNotEqual(datetime_value(dt('003000'),'datetime'),datetime_value(dt('007000'),'datetime'))
        with self.assertRaisesRegex(ValueError,'naive'):
            datetime_value(dict(type='datetime',value='2026-10-01T00:00:00+02:00'),'datetime')

    def test_order_contract_is_per_result_and_ties_are_multisets(self):
        a,b,m=inputs([node('OrderByClause')])
        raw=a['observation']['source_syntax']
        raw['semantic_catalogue']={'result_contracts':[
            dict(ordered=True,resolved=True,key_indices=[0]),dict(ordered=False,resolved=True,key_indices=[])]}
        for lane_value in (a,b):
            rs=lane_value['observation']['result_sets'][0]
            rs['columns']*=2;rs['rows']=[['a','x'],['a','y'],['b','z']]
            lane_value['observation']['result_sets'].append(deepcopy(rs))
        b['observation']['result_sets'][0]['rows']=[['a','y'],['a','x'],['b','z']]
        b['observation']['result_sets'][1]['rows'].reverse()
        self.assertFalse(compare(a,b,m)['differences'])
        b['observation']['result_sets'][0]['rows'].reverse()
        self.assertEqual(compare(a,b,m)['verdict'],'divergent')

    def test_547_cannot_be_authorized_by_old_profile(self):
        a,b,m=inputs([])
        a['observation']['error']={'number':547,'message':'ambiguous constraint'}
        b['observation']['error']={'sqlstate':'23514'}
        m=profile(dict(id='public-check',trap_family=1,assets={},calling_convention={'public_error_equivalence':'check-constraint-547-23514'}))
        self.assertIn('error-map-required',[u['observable'] for u in compare(a,b,m)['unresolved']])

    def test_source_policy_and_target_volatile_selection(self):
        from lightyear_data.tsql_procedures.semantics import target_contract
        for kind in ('SetRowCountStatement','SelectSetVariable'):
            self.assertTrue(contract(ast([node(kind)]))['policy_obligations'])
        for source in ('SELECT x FROM t LIMIT 1','SELECT CURRENT_TIMESTAMP','SELECT row_number() OVER (ORDER BY x)',"SELECT string_agg(x,',') FROM t"):
            self.assertTrue(target_contract(source)['policy_obligations'])
        self.assertFalse(target_contract("SELECT 'LIMIT 1' AS x")['policy_obligations'])

    def test_key_join_cardinality_is_bound_to_rhs_primary_key(self):
        from lightyear_data.tsql_procedures.semantics import unique_update_join
        j=dict(closed=True,join_type='Inner',target=['a'],left=dict(alias='a',parts=['dbo','a']),
               right=dict(alias='b',parts=['dbo','b']),equalities=[[['a','id'],['b','id']]])
        state={'tables':{'["dbo","a"]':dict(columns=[['id']],primary_key=['id']),
                         '["dbo","b"]':dict(columns=[['id']],primary_key=['id'])}}
        self.assertTrue(unique_update_join(j,state))
        state['tables']['["dbo","b"]']['primary_key']=[]
        self.assertFalse(unique_update_join(j,state))

    def test_money_boundaries_and_nullable_shrink(self):
        from lightyear_data.tsql_procedures.casegen import boundaries
        self.assertIn('922337203685477.5807',boundaries('money'))
        self.assertIn('-922337203685477.5808',boundaries('money'))
        self.assertEqual(shrink({'x':123},'same',lambda c:'same')['case'],{'x':None})

    def test_native_dictionary_table_rows_use_date_storage_ticks(self):
        from lightyear_data.tsql_procedures.value_contract import normalized_tables
        a=dict(tables={'t':dict(columns=[['at','datetime']],primary_key=[],rows=[{'at':dict(type='datetime',value='2026-10-01T00:00:00.003')}])})
        b=dict(tables={'t':dict(columns=[['at','timestamp without time zone']],primary_key=[],rows=[{'at':dict(type='datetime',value='2026-10-01T00:00:00.003333')}])})
        self.assertEqual(*normalized_tables(a,b))

    def test_profile_failure_preserves_ownership_of_created_database(self):
        from unittest.mock import patch
        from contextlib import nullcontext
        from lightyear_data.tsql_procedures.native import NativeEngine
        engine=NativeEngine('postgresql',lambda db:nullcontext(object()),'lytsql_123456789abc')
        def execute(conn,sql):
            if sql.startswith('ALTER DATABASE'):
                self.assertIn('lytsql_123456789abc_b1',engine.owned)
                raise RuntimeError('profile failed')
        with patch('lightyear_data.tsql_procedures.native.execute',side_effect=execute):
            with self.assertRaisesRegex(RuntimeError,'profile failed'):engine.provision('b1','','')
        self.assertEqual(engine.owned,{'lytsql_123456789abc_b1'})
