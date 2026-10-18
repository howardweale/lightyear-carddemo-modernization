"""Independent control-flow component checks; not a six-screen P5 claim."""
from decimal import Decimal
from pathlib import Path
import unittest
from lightyear_data.carddemo.reference_control import Program,Machine,Unsupported,tokens

class ScalarPort:
    def __init__(self):self.values={'X':Decimal(0),'RESULT':'','FLAG':False}
    def value(self,items):
        text=''.join(t.text for t in items)
        if text.startswith("'"):return text[1:-1]
        if text in self.values:return self.values[text]
        return Decimal(text)
    def assign(self,targets,value,string=False):
        for target in targets:self.values[target.text]=value
    def predicate(self,items):
        parts=[t.text for t in items]
        if len(parts)==1:return bool(self.values[parts[0]])
        left=self.value(items[:1]);right=self.value(items[2:])
        return {'=':left==right,'>':left>right,'<':left<right}[parts[1]]
    def set_condition(self,name):self.values[name]=True
    def initialize(self,items):
        for t in items:self.values[t.text]=Decimal(0)
    def external(self,items):raise Unsupported('no external operation authorized in component fixture')

def source(text):return ('\n'.join('       '+line for line in text.splitlines())+'\n').encode()

class ReferenceControlTests(unittest.TestCase):
    def test_raw_branches_and_perform_range_have_physical_trace(self):
        raw=source("""PROCEDURE DIVISION.
MAIN.
    MOVE 2 TO X
    PERFORM 1200-CHECK THRU 1200-CHECK-EXIT.
1200-CHECK.
    IF X = 2
        MOVE 'YES' TO RESULT
    ELSE
        MOVE 'NO' TO RESULT
    END-IF.
1200-CHECK-EXIT.
    EXIT.
""")
        program=Program(raw,'fixture.cbl');port=ScalarPort();machine=Machine(program,port);machine.run('MAIN')
        self.assertEqual('YES',port.values['RESULT']);self.assertIn(('fixture.cbl',7),machine.trace)
        changed=Program(raw.replace(b'IF X = 2',b'IF X = 3'),'mutant.cbl');mutant=ScalarPort();Machine(changed,mutant).run('MAIN')
        self.assertEqual('NO',mutant.values['RESULT'])
    def test_loop_evaluate_and_bound(self):
        raw=source("""PROCEDURE DIVISION.
MAIN.
    PERFORM VARYING X FROM 1 BY 1 UNTIL X > 3
        CONTINUE
    END-PERFORM
    EVALUATE X
      WHEN 4 MOVE 'FOUR' TO RESULT
      WHEN OTHER MOVE 'BAD' TO RESULT
    END-EVALUATE.
""")
        port=ScalarPort();Machine(Program(raw,'loop.cbl'),port).run('MAIN');self.assertEqual('FOUR',port.values['RESULT'])
        with self.assertRaisesRegex(Unsupported,'bound'):Machine(Program(raw.replace(b'BY 1',b'BY 0'),'loop.cbl'),ScalarPort(),limit=10).run('MAIN')
    def test_real_signon_parses_without_production_edit_compiler(self):
        path=Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens/upstream/app/cbl/COSGN00C.cbl'
        program=Program(path.read_bytes(),str(path))
        self.assertIn('READ-USER-SEC-FILE',program.paragraphs)
        self.assertEqual('SET',program.paragraphs['MAIN-PARA'][0].verb)
        self.assertGreater(sum(len(v) for v in program.paragraphs.values()),20)
    def test_unsupported_syntax_is_never_skipped(self):
        with self.assertRaises(Unsupported):Program(source('PROCEDURE DIVISION.\nMAIN.\n ALTER X TO PROCEED TO Y.'),'bad.cbl')
        with self.assertRaises(Unsupported):tokens(b'      -    CONTINUED\n','bad.cbl')

class ReferenceStorageTests(unittest.TestCase):
    def memory(self):
        from lightyear_mainframe.records import compile_copybook
        from lightyear_data.carddemo.reference_storage import Memory
        raw=source("""01 RECORD-A.
    05 TEXT-A PIC X(4).
    05 NUMBER-A REDEFINES TEXT-A PIC 9(4).
    05 PACKED-A PIC S9(5)V99 COMP-3.
    05 BINARY-A PIC S9(9) COMP.
    05 DATE-A.
        10 YEAR-A PIC 9(4).
        10 FILLER PIC X VALUE '/'.
        10 MONTH-A PIC 9(2).
""").decode()
        memory=Memory();memory.add(compile_copybook(raw,storage_overlays=True).manifest(),raw);return memory
    def test_overlay_numeric_encoding_and_source_filler(self):
        m=self.memory();m.write('TEXT-A','1234');self.assertEqual(Decimal(1234),m.read('NUMBER-A'))
        m.write('PACKED-A',Decimal('-12.34'));self.assertEqual(bytes.fromhex('0001234d'),m.raw('PACKED-A'))
        m.write('BINARY-A',Decimal(-123));self.assertEqual(bytes.fromhex('ffffff85'),m.raw('BINARY-A'))
        m.write('YEAR-A',2026);m.write('MONTH-A',10);self.assertEqual('2026/10',m.read('DATE-A'))
        m.write_slice('TEXT-A',1,2,'ZZ');self.assertEqual('1ZZ4',m.read('NUMBER-A'))
    def test_expression_predicate_and_figurative_moves_from_raw_tokens(self):
        from lightyear_data.carddemo.reference_values import Values
        m=self.memory();state=Values(m);m.write('TEXT-A','abcd')
        lex=lambda text:tokens(source(text),'expression.cbl')
        self.assertEqual('BC',state.value(lex('FUNCTION UPPER-CASE(TEXT-A(2:2))')))
        self.assertTrue(state.predicate(lex("TEXT-A = 'abcd' OR 'efgh'")))
        self.assertFalse(state.predicate(lex('TEXT-A IS NUMERIC')))
        state.assign(lex('TEXT-A'),state.value(lex('LOW-VALUES')));self.assertEqual(b'\x00'*4,m.raw('TEXT-A'))
        self.assertTrue(state.predicate(lex('TEXT-A = LOW-VALUES')))
        state.assign(lex('TEXT-A'),state.value(lex('ZEROS')));self.assertEqual('0000',m.read('TEXT-A'))

    def test_numeric_items_keep_numeric_order_but_invalid_display_reaches_source_validation(self):
        from lightyear_data.carddemo.reference_values import Values
        m=self.memory();state=Values(m);m.write('TEXT-A','0009');m.write('BINARY-A',11)
        lex=lambda text:tokens(source(text),'expression.cbl')
        self.assertFalse(state.predicate(lex('NUMBER-A > BINARY-A')))
        m.write('TEXT-A','0012');self.assertTrue(state.predicate(lex('NUMBER-A > BINARY-A')))
        m.write('TEXT-A','XX00')
        self.assertTrue(state.predicate(lex('NUMBER-A IS NOT NUMERIC OR NUMBER-A > BINARY-A')))
        self.assertFalse(state.predicate(lex('NUMBER-A IS NUMERIC')))

class ReferenceDeclarationTests(unittest.TestCase):
    def load(self,name):
        from lightyear_data.carddemo.reference_declarations import layout
        from lightyear_data.carddemo.reference_storage import Memory
        root=Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens/upstream'
        paths=[p for p in root.rglob('*') if p.name.lower()==(name+'.cpy').lower()];self.assertEqual(1,len(paths),name)
        raw=paths[0].read_bytes();m=Memory();m.add(layout(raw,str(paths[0])));return m
    def test_pinned_bms_input_and_output_share_physical_bytes(self):
        m=self.load('COSGN00');m.write('COSGN0AO.USERIDO','USER0001')
        self.assertEqual('USER0001',m.read('COSGN0AI.USERIDI'))
        m.write('COSGN0AI.USERIDL',-1);self.assertEqual(bytes.fromhex('ffff'),m.raw('USERIDL'))
        self.assertEqual(m.descriptor('COSGN0AI')[1]['offset'],m.descriptor('COSGN0AO')[1]['offset'])
    def test_menu_overlay_keeps_multiline_values_and_larger_extent(self):
        m=self.load('COMEN02Y')
        self.assertEqual(Decimal(11),m.read('CDEMO-MENU-OPT-COUNT'))
        self.assertEqual('COACTVWC',m.read('CDEMO-MENU-OPT-PGMNAME[1]'))
        self.assertEqual('COPAUS0C',m.read('CDEMO-MENU-OPT-PGMNAME[11]'))
        self.assertEqual('Account Update',m.read('CDEMO-MENU-OPT-NAME[2]').strip())
        self.assertEqual(46*12,m.descriptor('CDEMO-MENU-OPTIONS')[1]['length'])
    def test_qualifiers_are_resolved_instead_of_discarded(self):
        from lightyear_data.carddemo.reference_declarations import layout
        from lightyear_data.carddemo.reference_storage import Memory
        from lightyear_data.carddemo.reference_values import Values
        m=Memory();m.add(layout(source("01 A.\n 05 SHARED PIC X(2) VALUE 'AA'.\n01 B.\n 05 SHARED PIC X(2) VALUE 'BB'."),'qualified.cpy'))
        with self.assertRaises(Unsupported):m.read('SHARED')
        self.assertEqual('AA',Values(m).value(tokens(source('SHARED OF A'),'expr')))
        self.assertEqual('BB',Values(m).value(tokens(source('SHARED OF B'),'expr')))

class RawSignonTests(unittest.TestCase):
    def reference(self):
        from lightyear_data.carddemo.reference_signon import SignonReference
        return SignonReference(Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens/upstream')
    def test_initial_and_invalid_fields_execute_pinned_program(self):
        r=self.reference();initial=r.interact('INITIAL')
        self.assertEqual('USERID',initial['screen']['cursor'])
        self.assertEqual('10/17/26',initial['screen']['values']['CURDATE'])
        self.assertEqual('12:34:56 ',initial['screen']['values']['CURTIME'])
        blank=r.interact('ENTER',{})
        self.assertEqual('Please enter User ID ...',blank['screen']['message'])
        missing_password=r.interact('ENTER',{'USERID':'MISSING'})
        self.assertEqual('PASSWD',missing_password['screen']['cursor'])
        self.assertEqual('MISSING ',missing_password['screen']['values']['USERID'])
        missing_user=r.interact('ENTER',{'USERID':'MISSING','PASSWD':'PASSWORD'})
        self.assertEqual('User not found. Try again ...',missing_user['screen']['message'])
        self.assertGreater(len(missing_user['trace']),20)
        invalid=r.interact('PF1',{'USERID':'IGNORED','PASSWD':'IGNORED'})
        self.assertEqual('        ',invalid['screen']['values']['PASSWD'])
        self.assertEqual('        ',invalid['screen']['values']['USERID'])
        self.assertEqual('________',initial['screen']['values']['PASSWD'])
    def test_source_password_and_user_type_decide_transfer(self):
        r=self.reference();m=r.storage();m.write('SEC-USR-ID','TESTUSER');m.write('SEC-USR-PWD','PASSWORD');m.write('SEC-USR-TYPE','U')
        r.users={'TESTUSER':m.raw('SEC-USER-DATA')}
        self.assertEqual('COMEN01C',r.interact('ENTER',{'USERID':'testuser','PASSWD':'password'})['program'])
        wrong=r.interact('ENTER',{'USERID':'TESTUSER','PASSWD':'WRONG'})
        self.assertEqual('Wrong Password. Try again ...',wrong['screen']['message'])
        self.assertEqual('WRONG   ',wrong['screen']['values']['PASSWD'])
        self.assertTrue(r.interact('PF3')['ended'])

class ReferenceExpandedSourceTests(unittest.TestCase):
    def test_account_update_copies_keep_original_locations_and_replacements(self):
        from lightyear_data.carddemo.reference_source import procedure_tokens
        root=Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens/upstream'
        source_path=root/'app/cbl/COACTUPC.cbl';items=procedure_tokens(source_path.read_bytes(),str(source_path),root)
        self.assertFalse(any(t.text=='COPY' for t in items))
        copy_tokens=[t for t in items if t.source.endswith('CSSETATY.cpy')]
        self.assertGreater(len(copy_tokens),100)
        self.assertTrue(any(t.text=='FLG-CURR-BAL-NOT-OK' for t in copy_tokens))
        self.assertTrue(all(t.line>0 for t in copy_tokens))
        self.assertTrue(any(t.source.endswith('CSUTLDPY.cpy') for t in items))
    def test_inspect_uses_parallel_character_conversion(self):
        from lightyear_data.carddemo.reference_declarations import layout
        from lightyear_data.carddemo.reference_storage import Memory
        from lightyear_data.carddemo.reference_values import Values
        m=Memory();m.add(layout(source("01 DATA-A.\n 05 TEXT-A PIC X(4) VALUE 'AB A'."),'fixture'))
        state=Values(m)
        raw=source("PROCEDURE DIVISION.\nMAIN.\n INSPECT TEXT-A CONVERTING 'AB' TO 'BA'\n INSPECT TEXT-A REPLACING ALL ' ' BY '0'.")
        Machine(Program(raw,'inspect'),state).run('MAIN');self.assertEqual('BA0B',m.read('TEXT-A'))

class RawMenuTests(unittest.TestCase):
    def reference(self):
        from lightyear_data.carddemo.reference_menu import MenuReference
        return MenuReference(Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens/upstream')
    def test_menu_rows_and_received_fields_come_from_source(self):
        r=self.reference();initial=r.interact('INITIAL')
        self.assertEqual('01. Account View',initial['screen']['values']['OPTN001'].rstrip())
        self.assertEqual('11. Pending Authorization View',initial['screen']['values']['OPTN011'].rstrip())
        error=r.interact('PF1',{'OPTION':'11'},initial['commarea'])
        self.assertEqual('11',error['screen']['values']['OPTION'])
        self.assertTrue(error['screen']['message'])
    def test_source_menu_transfers_include_explicit_outside_slice_routes(self):
        for option,program in [('1','COACTVWC'),('2','COACTUPC'),('11','COPAUS0C'),('3','COCRDLIC')]:
            with self.subTest(option=option):
                r=self.reference();initial=r.interact('INITIAL')
                self.assertEqual(program,r.interact('ENTER',{'OPTION':option},initial['commarea'])['program'])
        r=self.reference();initial=r.interact('INITIAL')
        self.assertEqual('COSGN00C',r.interact('PF3',{},initial['commarea'])['program'])
    def test_invalid_subscript_is_disclosed_instead_of_fabricated(self):
        r=self.reference();initial=r.interact('INITIAL')
        with self.assertRaises(Unsupported):r.interact('ENTER',{'OPTION':'00'},initial['commarea'])
        self.assertIn('valid option number',r.frame['message'])
        for value in ('XX','!'):
            r=self.reference();initial=r.interact('INITIAL')
            with self.assertRaisesRegex(Unsupported,'nonnumeric reference subscript'):
                r.interact('ENTER',{'OPTION':value},initial['commarea'])
            self.assertIn('valid option number',r.frame['message'])

class RawRemainingScreenTests(unittest.TestCase):
    root=Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens/upstream'
    def test_all_four_raw_procedures_and_linked_action_have_storage(self):
        from lightyear_data.carddemo.reference_screens import AccountViewReference,AccountUpdateReference,AuthorizationListReference,AuthorizationDetailReference,FraudReference
        for adapter in (AccountViewReference,AccountUpdateReference,AuthorizationListReference,AuthorizationDetailReference,FraudReference):
            with self.subTest(program=adapter.program_name):
                reference=adapter(self.root);memory=reference.storage()
                self.assertTrue(reference.program.paragraphs)
                self.assertGreater(len(memory.entries),100)
                if adapter is FraudReference:self.assertEqual(11+9+200+52,memory.descriptor('DFHCOMMAREA')[1]['length'])
                else:self.assertGreater(memory.descriptor('CARDDEMO-COMMAREA')[1]['length'],100)
    def test_raw_account_initial_receive_and_missing_account(self):
        from lightyear_data.carddemo.reference_screens import AccountViewReference,AccountUpdateReference
        from lightyear_data.carddemo.reference_menu import MenuReference
        for option,adapter in [('1',AccountViewReference),('2',AccountUpdateReference)]:
            with self.subTest(program=adapter.program_name):
                menu=MenuReference(self.root);first=menu.interact('INITIAL')
                transfer=menu.interact('ENTER',{'OPTION':option},first['commarea'])
                reference=adapter(self.root);frame=reference.interact('INITIAL',commarea=transfer['commarea'])
                self.assertEqual('ACCTSID',frame['screen']['cursor'])
                for value in ('','00000000000','XXXXXXXXXXX','99999999999'):
                    result=reference.interact('ENTER',{'ACCTSID':value},frame['commarea'])
                    self.assertTrue(result['screen']['message'])
                    self.assertFalse(any(e['operation']=='REWRITE' for e in result['events']))
    def test_edited_decimal_receivers_use_source_width_and_suppression(self):
        from lightyear_data.carddemo.reference_declarations import layout
        from lightyear_data.carddemo.reference_storage import Memory
        m=Memory();m.add(layout(source('01 A.\n 05 BAL PIC +ZZZ,ZZZ,ZZZ.99.\n 05 AMT PIC -zzzzzzz9.99.'),'edited'))
        m.write('BAL',Decimal('-1234.56'));self.assertEqual('-      1,234.56',m.read('BAL'))
        m.write('AMT',Decimal('0'));self.assertEqual('        0.00',m.read('AMT'))
    def test_record_store_rollback_restores_all_locked_writes(self):
        from lightyear_data.carddemo.reference_screens import RecordStore
        store=RecordStore([dict(identity='1',keys={'ACCTDAT':b'key'},raw=b'original')]);store.begin()
        store.read('ACCTDAT',b'key',True);store.rewrite('ACCTDAT',b'updated');store.rollback()
        self.assertEqual(b'original',store.read('ACCTDAT',b'key')['raw'])

class RawDateReferenceTests(unittest.TestCase):
    def test_pinned_wrapper_handles_documented_leap_date_feedback(self):
        from lightyear_data.carddemo.reference_date import DateReference
        root=Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens/upstream'
        reference=DateReference(root)
        valid=reference.interact('20000229','YYYYMMDD');self.assertEqual('0000',valid[:4]);self.assertEqual('0000',valid[15:19])
        invalid=reference.interact('19900229','YYYYMMDD');self.assertEqual('0003',invalid[:4]);self.assertEqual('2508',invalid[15:19])
        self.assertTrue(reference.trace)

if __name__=='__main__':unittest.main()
