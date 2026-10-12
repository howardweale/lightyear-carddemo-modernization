import hashlib
import unittest
from lightyear_mainframe.generic_scenario_ir import BoundSource,translate

def bound(path,text):return BoundSource(path,text,hashlib.sha256(text.encode()).hexdigest())
def program(body):return bound('synthetic.cbl','       IDENTIFICATION DIVISION.\n       PROGRAM-ID. SYNTHETIC.\n       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n       01 ROW.\n          05 A PIC S9(3)V99 COMP-3.\n          05 B PIC S9(4)V99.\n       PROCEDURE DIVISION.\n'+body)

class GenericIRTests(unittest.TestCase):
    def test_typed_arithmetic_layout_and_guarded_flow(self):
        d=translate(program('           COMPUTE B = A * 2 + 1\n           IF B > 0\n             ADD A TO B\n           ELSE\n             MOVE 0 TO B\n           END-IF\n           STOP RUN.\n'),{})
        self.assertEqual([],d['issues']);self.assertEqual('-999.99',d['fields'][0]['domain']['minimum'])
        self.assertEqual('COMP-3',d['fields'][0]['usage']);self.assertEqual(3,d['fields'][0]['length'])
        self.assertTrue(any(e['source']=='A' and e['target']=='B' for e in d['data_flow']))
        assigns=[s for s in d['statements'] if s['kind']=='assignment'];self.assertTrue(assigns[1]['guards'][0]['outcome']);self.assertFalse(assigns[2]['guards'][0]['outcome'])
    def test_source_and_copybook_hash_binding(self):
        p=bound('p.cbl','       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n       COPY FIELDS.\n       PROCEDURE DIVISION.\n           MOVE 1 TO A.\n')
        c=bound('fields.cpy','       01 ROW.\n          05 A PIC 9(2).\n')
        d=translate(p,{'FIELDS':c});self.assertEqual(c.sha256,d['sources']['fields.cpy']);self.assertEqual('fields.cpy',d['fields'][0]['location']['path'])
        with self.assertRaisesRegex(ValueError,'hash-mismatch'):translate(p,{'FIELDS':BoundSource(c.path,c.text+' ',c.sha256)})
    def test_unsupported_string_io_and_call_are_located(self):
        d=translate(program("           CALL 'OUTSIDE'.\n           READ SOME-FILE.\n           IF 'A' < 'B'\n             CONTINUE\n           END-IF.\n"),{})
        self.assertFalse(d['translation_complete']);self.assertTrue(all(i['path']=='synthetic.cbl' and i['line']>0 for i in d['issues']))
        self.assertTrue(any('collation' in i['reason'] for i in d['issues']))
    def test_aliasing_not_silently_translated(self):
        p=bound('p','       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n       01 R.\n          05 A PIC 9.\n          05 B REDEFINES A PIC X.\n       PROCEDURE DIVISION.\n           MOVE 1 TO A.\n')
        d=translate(p,{});self.assertFalse(d['translation_complete']);self.assertEqual([],d['data_flow'])
    def test_dataset_keys_must_bind_layout(self):
        with self.assertRaisesRegex(ValueError,'key-unbound'):translate(program('           CONTINUE.\n'),{},datasets=[{'dataset':'IN','record':'ROW','keys':['ROW.MISSING']}])
    def test_never_solve_or_execute_and_reject_unbound(self):
        d=translate(program('           COMPUTE B = UNKNOWN + 1.\n'),{})
        self.assertFalse(d['translation_complete']);self.assertEqual([],d['data_flow']);self.assertEqual(0,d['solver_calls']);self.assertEqual(0,d['executions'])
    def test_precedence_and_decimal_types(self):
        d=translate(program('           COMPUTE B = ( A + 1 ) * 2.\n'),{})
        self.assertEqual('*',d['statements'][0]['expression']['value']);self.assertEqual('+',d['statements'][0]['expression']['operands'][0]['value'])
