"""Pinned COSGN00C execution through the raw-source VM and explicit CICS ports.

This is the first executable screen baseline. Other five programs remain outside
this adapter until their CICS/DLI/storage operations are implemented; callers
must retain that denominator. It never reads Java bindings or candidate frames.
"""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import re
from .reference_control import Program,Machine,Reader,Unsupported,tokens
from .reference_declarations import layout
from .reference_storage import Memory
from .reference_values import Values
from .screens import parse

class Returned(Exception):pass
class TransferScreen(Exception):
    def __init__(self,program):self.program=program

class SignonReference:
    program_name='COSGN00C'
    mapset='COSGN00'
    def __init__(self,root,clock=None,users=None):
        self.root=Path(root);self.clock=clock or datetime(2026,10,17,12,34,56,tzinfo=timezone.utc);self.users=users or {}
        self.source=self.find(self.program_name,'.cbl');self.raw=self.source.read_bytes();self.program=Program(self.raw,str(self.source));self.trace=[]
        self.model=parse(self.find(self.mapset,'.bms').read_bytes(),self.mapset+'.bms')['maps'][0]
    def find(self,name,suffix):
        found=[p for p in self.root.rglob('*') if p.stem==name and p.suffix.lower()==suffix]
        if len(found)!=1:raise Unsupported('reference source absent/ambiguous: '+name)
        return found[0]
    def storage(self):
        m=Memory();lines=self.raw.decode().splitlines();begin=next(i for i,l in enumerate(lines) if 'WORKING-STORAGE SECTION.' in l)+1
        end=next(i for i,l in enumerate(lines) if 'LINKAGE SECTION.' in l)
        chunk=[]
        def flush():
            if any(l[7:72].strip() for l in chunk if len(l)>7 and l[6] not in '*/'):
                m.add(layout(('\n'.join(chunk)+'\n').encode(),str(self.source)))
            chunk.clear()
        for line in lines[begin:end]:
            code='' if len(line)<7 or line[6] in '*/' else line[7:72]
            match=re.fullmatch(r'\s*COPY\s+([A-Z0-9]+)\.\s*',code)
            if match:
                flush();name=match[1]
                if name not in ('DFHAID','DFHBMSCA'):
                    path=self.find(name,'.cpy');m.add(layout(path.read_bytes(),str(path)))
            else:chunk.append(line)
        flush()
        # External protocol constants, not business-field mappings.
        protocol="""01 CICS-ENV.
  05 EIBCALEN PIC S9(4) COMP.
  05 EIBAID PIC X.
  05 EIBRESP PIC S9(9) COMP.
  05 DFHENTER PIC X VALUE X'7D'.
  05 DFHPF3 PIC X VALUE X'F3'.
"""
        m.add(layout(('\n'.join('       '+l for l in protocol.splitlines())+'\n').encode(),'CICS protocol'))
        return m
    def interact(self,aid,fields=None):
        self.memory=self.storage();self.input=fields or {};self.frame=None;self.ended=False;self.next_program='COSGN00C'
        m=self.memory;m.write('EIBCALEN',0 if aid=='INITIAL' else m.descriptor('CARDDEMO-COMMAREA')[1]['length'])
        # Unrecognized AIDs enter the source's WHEN OTHER path.
        m.write('EIBAID',bytes([0x7D if aid=='ENTER' else 0xF3 if aid=='PF3' else 0xFF]).decode('cp037'))
        self.values=Values(m,clock=self.clock,external=self.external)
        machine=Machine(self.program,self.values)
        try:machine.run('MAIN-PARA')
        except Returned:pass
        except TransferScreen as transfer:self.next_program=transfer.program
        self.trace=machine.trace
        return dict(program=self.next_program,screen=self.frame,ended=self.ended,trace=self.trace,commarea=m.raw('CARDDEMO-COMMAREA').hex())
    def operands(self,items):
        r=Reader(items);kind=r.pop().text;operation=r.pop().text;options={};flags=[]
        while r.peek():
            name=r.pop().text
            if r.peek()=='(':
                r.pop();body=[];depth=1
                while depth:
                    t=r.pop()
                    if t.text=='(':depth+=1
                    if t.text==')':depth-=1
                    if depth:body.append(t)
                options[name]=body
            else:flags.append(name)
        return kind,operation,options,flags
    def external(self,items,values):
        kind,operation,o,flags=self.operands(items);m=self.memory
        if kind!='CICS':raise Unsupported('signon port '+kind)
        if operation=='RECEIVE':
            for f in self.model['fields']:
                name=f['name']
                if not name:continue
                if not f['protected'] or name in self.input:
                    text=self.input.get(name,'')
                    if len(text)>f['length']:raise Unsupported('reference input too long')
                    m.write(name+'I',text);m.write(name+'L',len(text))
            for key in ('RESP','RESP2'):
                if key in o:values.assign(o[key],0)
        elif operation=='SEND':
            if 'TEXT' in flags:
                self.ended=True;self.frame=dict(message=values.value(o['FROM']).rstrip(' '));return
            frame=dict(values={},attributes={},cursor='',message='')
            for f in self.model['fields']:
                name=f['name']
                if not name:continue
                raw=m.raw(name+'O');text=raw.decode('cp037') if any(raw) else f.get('initial','')
                frame['values'][name]=text.ljust(f['length'])[:f['length']]
                frame['attributes'][name]={k:f[k] for k in ('protected','hidden','color','highlight')}
                frame['attributes'][name].update(basic=f['attributes'],modified='FSET' in f['attributes'])
                if 'IC' in f['attributes']:frame['cursor']=name
                if m.read(name+'L')==-1:frame['cursor']=name
            frame['message']=frame['values']['ERRMSG'].rstrip(' ');self.frame=frame
        elif operation=='ASSIGN':
            # Public reference APPLID/SYSID are blank; no claim about a live CICS region.
            for target in o.values():values.assign(target,'')
        elif operation=='READ':
            if values.value(o['DATASET']).strip()!='USRSEC':raise Unsupported('reference dataset')
            key=values.value(o['RIDFLD']);raw=self.users.get(key)
            values.assign(o['RESP'],0 if raw is not None else 13);values.assign(o['RESP2'],0)
            if raw is not None:values.assign(o['INTO'],raw.decode('cp037'))
        elif operation=='XCTL':raise TransferScreen(values.value(o['PROGRAM']).rstrip())
        elif operation=='RETURN':raise Returned()
        else:raise Unsupported('signon CICS operation '+operation)