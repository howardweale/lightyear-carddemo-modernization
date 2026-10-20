"""Pinned CSUTLDTC wrapper with a bounded Gregorian YYYYMMDD CEEDAYS port.

Feedback numbers and Lilian epoch follow IBM's CEEDAYS specification:
https://www.ibm.com/docs/en/zos/2.5.0?topic=services-ceedaysconvert-date-lilian-format
This models a documented library boundary; it is not native LE execution.
"""
from datetime import date
from .reference_control import Program,Machine,Reader,Unsupported,ProgramExit
from .reference_source import procedure_tokens
from .reference_screens import declarations_for
from .reference_storage import Memory
from .reference_declarations import layout
from .reference_values import Values

class DateReference:
    def __init__(self,root):
        paths=list(root.rglob('CSUTLDTC.cbl'))
        if len(paths)!=1:raise Unsupported('date wrapper source')
        self.path=paths[0];self.raw=self.path.read_bytes();self.root=root
        self.program=Program(self.raw,str(self.path),procedure_tokens(self.raw,str(self.path),root))
    def interact(self,text,mask):
        m=Memory();m.add(declarations_for(self.raw,self.path,self.root));m.add(declarations_for(self.raw,self.path,self.root,'LINKAGE'))
        m.add(layout(b'       01 RETURN-CODE PIC S9(9) COMP.\n','COBOL runtime return-code'))
        m.write('LS-DATE',text);m.write('LS-DATE-FORMAT',mask)
        values=Values(m,call=self.call);vm=Machine(self.program,values)
        try:vm.run('REFERENCE-ENTRY')
        except ProgramExit:pass
        self.trace=vm.trace;return m.read('LS-RESULT')
    def call(self,items,values):
        r=Reader(items);name=values.atom(r)
        if name!='CEEDAYS':raise Unsupported('date reference external library')
        r.pop('USING');args=values.operands(r.items[r.at:])
        if len(args)!=4:raise Unsupported('CEEDAYS arity')
        names=[values.reference(Reader(a))[0] for a in args];m=values.memory
        def varying(name):
            raw=m.raw(name);width=int.from_bytes(raw[:2],'big',signed=True)
            if not 0<=width<=256:raise Unsupported('CEEDAYS varying length')
            return raw[2:2+width].decode('cp037').rstrip(' ')
        text,mask=map(varying,names[:2]);code='FC-INVALID-DATE';lilian=0
        if mask!='YYYYMMDD':raise Unsupported('CEEDAYS mask outside slice')
        if len(text)!=8 or not text.isascii() or not text.isdigit():code='FC-NON-NUMERIC-DATA'
        elif int(text[:4])<1582:code='FC-UNSUPP-RANGE'
        elif not 1<=int(text[4:6])<=12:code='FC-INVALID-MONTH'
        else:
            try:
                parsed=date(int(text[:4]),int(text[4:6]),int(text[6:]));lilian=(parsed-date(1582,10,14)).days
                if lilian<1:code='FC-UNSUPP-RANGE';lilian=0
            except ValueError:code='FC-BAD-DATE-VALUE'
        m.write(names[2],lilian);m.write(names[3],'\0'*12);values.set_condition(code)
