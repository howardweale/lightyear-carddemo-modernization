from copy import deepcopy
import unittest
from lightyear_data.contracts import seal
from lightyear_data.tsql_procedures.coverage import sql_summary,pg_summary,replay_coverage,sha
from lightyear_data.tsql_procedures.policy import profile,validate,identity_contract,table_contract
from lightyear_data.tsql_procedures.corpus import corpus


def sql_input(offsets=(0,10,30)):
    source='x'*100
    span=lambda start,length:{'start_utf16':start,'length_utf16':length,'line':start+1}
    cat={'schema':'tsql-scriptdom-coverage/1','statements':[span(0,1),span(10,20),span(15,1),span(30,1)],
         'branches':[{'statement':span(10,20),'then_span':span(15,1),'else_span':None}],
         'handlers':[{'span':span(10,20)}]}
    xml='<RingBufferTarget>'+''.join('<event name="'+kind+'"><data name="object_id"><value>1</value></data>'
        '<data name="offset"><value>'+str(o*2)+'</value></data><action name="event_sequence"><value>'+str(i)+
        '</value></action></event>' for i,(o,kind) in enumerate((o,k) for o in offsets for k in
        ('sp_statement_starting','sp_statement_completed')))+'</RingBufferTarget>'
    return {'schema':'tsql-sqlserver-coverage-input/1','ring_xml':xml,'dropped_events':0,
            'modules':[{'object_id':1,'name':'dbo.trap','definition':source,'parsed':{'input_sha256':sha(source.encode()),
                       'parsed':True,'coverage_catalogue':cat}}]}


class CoveragePolicyTests(unittest.TestCase):
    def test_missing_branch_not_success(self):
        r=sql_summary(sql_input())
        self.assertEqual(r['statement_fraction'],.75)
        self.assertEqual(r['minimum_module_branch_fraction'],.5)
        self.assertFalse(r['eligible'])
        self.assertEqual([e['hit'] for e in r['modules'][0]['branches']],[False,True])

    def test_no_parent_completion_invents_false_edge(self):
        r=sql_summary(sql_input((0,30)))
        self.assertEqual(r['minimum_module_branch_fraction'],0)
        self.assertTrue(r['missing_error_paths'])

    def test_both_edges_across_visits(self):
        r=sql_summary(sql_input((0,10,15,10,30)))
        self.assertEqual(r['minimum_module_branch_fraction'],1)

    def test_loss_and_replay_tampering(self):
        raw=sql_input();record={'raw':raw,'summary':sql_summary(raw)}
        self.assertFalse(replay_coverage(record)['eligible'])
        record['summary']['eligible']=True
        with self.assertRaisesRegex(ValueError,'coverage-replay'):replay_coverage(record)
        raw['dropped_events']=1
        with self.assertRaisesRegex(ValueError,'events-lost'):sql_summary(raw)

    def test_pg_real_profiler_shape_and_missing_handler_proof(self):
        row={'stmtid':1,'stmtname':'SQL statement','exec_stmts':None,'lineno':3}
        raw={'modules':[{'name':'dbo.trap()','definition':'body','before':[row],
            'after':[dict(row,exec_stmts=1)],'branch_fraction':.9}]}
        r=pg_summary(raw)
        self.assertEqual(r['statement_fraction'],1)
        self.assertFalse(r['eligible'])
        self.assertTrue(r['missing_error_paths'])
        raw['modules'][0]['branch_fraction']=1
        self.assertTrue(pg_summary(raw)['eligible'])
        raw['modules'][0]['before'][0]['exec_stmts']=1
        with self.assertRaisesRegex(ValueError,'not-fresh'):pg_summary(raw)

    def test_policy_no_self_authorized_changes(self):
        item={'id':'public','trap_family':1,'assets':{},'calling_convention':{}}
        p=profile(item);validate(p)
        p=seal(dict(p,row_count_policy='silently-ignore'))
        with self.assertRaises(ValueError):validate(p)

    def test_identity_unconsumed_and_consumed_mapping(self):
        a={'engine':'sqlserver','identity_sequence_state':{'["dbo","items","id"]':
            {'last_value':None,'seed':'1','increment':'1'}}}
        b={'engine':'postgresql','identity_sequence_state':{'["dbo","items_id_seq"]':
            {'last_value':1,'is_called':False,'seed':1,'increment':1,'owner':['dbo','items','id']}}}
        self.assertEqual(identity_contract(a),identity_contract(b))
        a['identity_sequence_state']['["dbo","items","id"]']['last_value']='2'
        b['identity_sequence_state']['["dbo","items_id_seq"]'].update(last_value=2,is_called=True)
        self.assertEqual(identity_contract(a),identity_contract(b))
        b['identity_sequence_state']['["dbo","items_id_seq"]']['owner']=[None,None,None]
        with self.assertRaisesRegex(ValueError,'owner-unmapped'):identity_contract(b)

    def test_unknown_table_type_not_silently_equal(self):
        with self.assertRaisesRegex(ValueError,'unmapped-table-type'):
            table_contract({'engine':'sqlserver','tables':{'x':{'columns':[['x','money',8,19,4,False]],'primary_key':[]}}})

    def test_twin_returns_are_driven_by_handler(self):
        for row in corpus():
            if row['id'] in ('ci-unique','catch-retains-prior-work','xact-abort'):
                self.assertIn('EXCEPTION WHEN',row['correct_sql'])
                self.assertIn('THEN mapped_status:=',row['correct_sql'])
                self.assertIn('count(*)::text, mapped_status',row['correct_sql'])
                self.assertEqual(row['calling_convention']['result_return_mapping']['column'],'tsql_return_code')

    def test_v3_all_differences_have_class_and_unknown_mapping_blocks(self):
        from test_tsql_native import lane
        from lightyear_data.tsql_procedures.native_evidence import compare_v2
        a,b=lane('sqlserver'),lane('postgresql')
        mapping=profile({'id':'public','trap_family':4,'assets':{},'calling_convention':{}})
        b['observation']['result_sets'][0]['rows']=[['3.5']]
        result=compare_v2(a,b,mapping,revision=3)
        self.assertEqual(result['verdict'],'divergent')
        self.assertTrue(all(d['classification']=='lossy' for d in result['differences']))
        b['observation']['result_sets'][0]['columns'][0]['type_code']='unknown'
        result=compare_v2(a,b,mapping,revision=3)
        self.assertEqual(result['verdict'],'insufficient-evidence')
        self.assertIn('unsupported',{d['classification'] for d in result['unresolved']})

    def test_signed_match_without_qualified_coverage_never_equivalent(self):
        from test_tsql_native import lane
        from lightyear_data.tsql_procedures.native_evidence import compare_v2
        p=profile({'id':'public','trap_family':4,'assets':{},'calling_convention':{}})
        self.assertEqual(compare_v2(lane('sqlserver'),lane('postgresql'),p,revision=3)['verdict'],'insufficient-evidence')


if __name__=='__main__':unittest.main()
