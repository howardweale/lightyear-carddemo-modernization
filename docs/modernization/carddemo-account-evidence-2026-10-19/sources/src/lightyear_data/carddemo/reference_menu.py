"""Raw COMEN01C adapter: menu contents and role decisions come from COBOL.

Out-of-range menu subscripts after an error SEND remain an explicit source
fault. They are not silently assigned a successful return or invented data.
"""
from .reference_signon import SignonReference,Returned,TransferScreen
from .reference_control import Machine,Unsupported
from .reference_declarations import layout
from .reference_values import Values

class MenuReference(SignonReference):
    program_name='COMEN01C'
    mapset='COMEN01'
    def interact(self,aid,fields=None,commarea=None):
        self.memory=self.storage();self.input=fields or {};self.frame=None;self.ended=False;self.next_program=self.program_name
        m=self.memory;width=m.descriptor('CARDDEMO-COMMAREA')[1]['length']
        m.add(layout(('       01 DFHCOMMAREA PIC X('+str(width)+').\n').encode(),'CICS received commarea'))
        if commarea is None:
            m.write('CDEMO-USER-TYPE','U');m.write('CDEMO-PGM-CONTEXT',0 if aid=='INITIAL' else 1)
            commarea=m.raw('CARDDEMO-COMMAREA').hex()
        received=bytes.fromhex(commarea)
        if len(received)!=width:raise Unsupported('menu COMMAREA width')
        m.write('DFHCOMMAREA',received.decode('cp037'));m.write('EIBCALEN',width)
        m.write('EIBAID',bytes([0x7D if aid=='ENTER' else 0xF3 if aid=='PF3' else 0xFF]).decode('cp037'))
        self.values=Values(m,clock=self.clock,external=self.external);machine=Machine(self.program,self.values)
        try:machine.run('MAIN-PARA')
        except Returned:pass
        except TransferScreen as transfer:self.next_program=transfer.program
        finally:self.trace=machine.trace
        return dict(program=self.next_program,screen=self.frame,ended=self.ended,trace=self.trace,commarea=m.raw('CARDDEMO-COMMAREA').hex())
    def external(self,items,values):
        kind,operation,options,flags=self.operands(items)
        if kind=='CICS' and operation=='INQUIRE':
            if values.value(options['PROGRAM']).strip()!='COPAUS0C':raise Unsupported('reference installation query')
            self.memory.write('EIBRESP',0) # The six-screen public slice installs COPAUS0C.
            return
        return super().external(items,values)
