"""Regression cases are synthetic offline evidence, never native qualification."""
import unittest
from copy import deepcopy
from test_tsql_native import lane
from lightyear_data.tsql_procedures.comparison_v5 import compare
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
        self.assertTrue(error_equivalent({'number':547},{'sqlstate':'23503'},{'constraint_kind':'foreign-key'}))
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
