"""Offline boundary tests; actual native results live in separate VM evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import types
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_data.contracts import seal
from lightyear_data.tsql_procedures.native import go_batches, NativeEngine, _QmarkConnection, tds_tokens
from lightyear_data.tsql_procedures.capture import state_changes, query
from lightyear_data.tsql_procedures.native_evidence import compare, write, seal_pair, replay_pair


def lane(engine):
    state=seal({'schema':'tsql-state-capture/1','engine':engine,'all_user_tables_captured':True,
                'tables':{},'table_inventory':[],'identity_sequence_state':{}})
    obs={'result_sets':[{'columns':[{'name':'value','type_code':'167' if engine=='sqlserver' else '25'}], 'rows':[['7']]}],
         'output_parameters':{},'return_code':0,'error':None,'temp_objects':[],
         'tds_tokens':[],'notices':[],'transaction_after':[0,0] if engine=='sqlserver' else 'IDLE',
         'side_effects':state_changes(state,state)}
    return {'before':state,'after':state,'observation':obs,
            'reset':{'outer_rollback':False,'method':'golden-backup-restore' if engine=='sqlserver' else 'fresh-database-from-template'}}


class NativeTests(unittest.TestCase):
    def test_rpc_direct_and_dispatch_completion_both_captured(self):
        class Session:
            def process_end(self,marker): self.done_flags=0; self.rows_affected=-1
            def process_msg(self,marker): self.messages=[{'message':'notice'}]
        module=types.ModuleType('pytds.tds_session');module._TdsSession=Session
        package=types.ModuleType('pytds');package.tds_session=module
        original=Session.process_end
        with patch.dict('sys.modules',{'pytds':package,'pytds.tds_session':module}):
            session=Session()
            with tds_tokens(session) as tokens:
                session.process_end(254)
                session.process_msg(171)
            self.assertEqual([v['token'] for v in tokens],[254,171])
            self.assertIs(Session.process_end,original)

    def test_literal_percent_does_not_enable_parameter_formatting(self):
        class Cursor:
            def execute(self,*args):
                self.args=args
                if len(args)==2: raise AssertionError('empty tuple enables formatting')
            def fetchmany(self,n): return []
            def close(self): pass
        class Connection:
            def cursor(self): return Cursor()
        self.assertEqual(query(_QmarkConnection(Connection()),"SELECT name WHERE name LIKE '#%'"),[])

    def test_go_lexer(self):
        self.assertEqual(len(go_batches("SELECT 'a\nGO\nb';\nGO\n/* GO\n/*x*/\n*/ SELECT 2;\nGO\n")),2)
        self.assertEqual(len(go_batches('SELECT [GO]; -- x\nGO -- end\n')),1)
        for bad in ("SELECT 'x",'/* x','SELECT 1\nGO 2\n'):
            with self.assertRaises(ValueError): go_batches(bad)

    def test_native_return_mapping_reads_actual_result_and_rejects_inconsistency(self):
        psycopg=types.ModuleType('psycopg');psycopg.Error=type('PsycopgError',(Exception,),{})
        class Cursor:
            description=[('value',25,None,None,None,None,None),('tsql_return_code',23,None,None,None,None,None)]
            rows=[['1',-4]]
            def execute(self,sql):pass
            def fetchall(self):return self.rows
            def __enter__(self):return self
            def __exit__(self,*args):pass
        class Connection:
            def cursor(self):return Cursor()
            def add_notice_handler(self,handler):pass
            def remove_notice_handler(self,handler):pass
        item={'calling_convention':{'target':'SELECT * FROM dbo.trap()',
            'result_return_mapping':{'column':'tsql_return_code','type':'integer'}}}
        engine=NativeEngine('postgresql',None,'lytsql_123456abcdef')
        with patch.dict('sys.modules',{'psycopg':psycopg}):
            result=engine._pg_call(Connection(),item)
            self.assertEqual(result['return_code'],-4)
            self.assertEqual(result['result_sets'][0]['rows'],[['1']])
            Cursor.rows=[['1',-4],['2',0]]
            with self.assertRaisesRegex(ValueError,'return-column-inconsistent'):engine._pg_call(Connection(),item)

    def test_unowned_drop_cannot_connect(self):
        def denied(_): raise AssertionError('must not connect')
        engine=NativeEngine('postgresql',denied,'lytsql_123456abcdef')
        with self.assertRaises(ValueError): engine.drop('production')
        with self.assertRaises(ValueError): engine.name('../bad')

    def test_no_certificate_from_match(self):
        a,b=lane('sqlserver'),lane('postgresql')
        result=compare(a,b,1)
        self.assertEqual(result['observed_status'],'match-on-compared-observables')
        self.assertEqual(result['verdict'],'insufficient-evidence')

    def test_value_mutant_and_no_silent_trimming(self):
        a,b=lane('sqlserver'),lane('postgresql')
        b['observation']['result_sets'][0]['rows']=[['7 ']]
        self.assertEqual(compare(a,b,1)['verdict'],'divergent')
        self.assertEqual(compare(a,b,25)['verdict'],'insufficient-evidence')

    def test_replay_recomputes_and_rejects_tampering(self):
        key=Ed25519PrivateKey.generate()
        public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); a,b=lane('sqlserver'),lane('postgresql')
            write(d/'source.json',a); write(d/'target.json',b)
            write(d/'comparison.json',compare(a,b,1))
            m=seal_pair(d,{'trap_family':1},key)
            self.assertTrue(replay_pair(d,public,m['content_sha256'])['comparison_recomputed'])
            (d/'target.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'evidence-changed'): replay_pair(d,public,m['content_sha256'])

    def test_changed_deltas_fail(self):
        a,b=lane('sqlserver'),lane('postgresql')
        b['observation']['side_effects']['tables']['extra']={}
        with self.assertRaisesRegex(ValueError,'side-effect-replay'): compare(a,b,1)


if __name__=='__main__': unittest.main()
