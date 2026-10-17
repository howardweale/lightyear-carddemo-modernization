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

if __name__=='__main__':unittest.main()
