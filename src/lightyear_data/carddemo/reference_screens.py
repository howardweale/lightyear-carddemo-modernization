"""Raw COBOL adapters for account view/update and authorization list/detail.

Business decisions, field assignments, COMMAREA layouts and messages execute
from pinned source. Ports model byte-record CICS reads/rewrites and IMS parent
navigation in memory. This is a deterministic reference, not native CICS/IMS.
The BMS protocol uses private symbolic octets: these are not wire encodings.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import re
from .reference_control import Program,Machine,Unsupported,Reader,Token
from .reference_declarations import layout
from .reference_storage import Memory
from .reference_values import Values
from .reference_source import logical,expand,procedure_tokens
from .reference_signon import SignonReference,Returned,TransferScreen
from .screens import parse

BASIC={
 'DFHBMPRO':dict(protected=True,modified=False,hidden=False),
 'DFHBMUNP':dict(protected=False,modified=False,hidden=False),
 'DFHBMPRF':dict(protected=True,modified=True,hidden=False,intensity='NORMAL'),
 'DFHBMFSE':dict(protected=False,modified=True,hidden=False,intensity='NORMAL'),
 'DFHBMASB':dict(protected=True,autoskip=True,modified=False,hidden=False,intensity='BRIGHT'),
 'DFHBMDAR':dict(protected=False,modified=False,hidden=True,intensity='DARK')}
COLORS={'DFHRED':'RED','DFHGREEN':'GREEN','DFHNEUTR':'NEUTRAL','DFHDFCOL':None}
SYMBOLS={name:bytes([n]).decode('cp037') for n,name in enumerate(list(BASIC)+list(COLORS),1)}
AIDS={name:bytes([n+32]).decode('cp037') for n,name in enumerate(['ENTER','CLEAR','PA1','PA2']+['PF'+str(i) for i in range(1,25)])}

def declarations_for(raw,path,root,section='WORKING-STORAGE'):
    rows=list(logical(raw,str(path)))
    begin=next(i+1 for i,(code,_,_) in enumerate(rows) if code.strip()==section+' SECTION.')
    end=next((i for i in range(begin,len(rows)) if re.search(r'\b(?:SECTION|DIVISION)\b',rows[i][0])),len(rows))
    selected=expand(rows[begin:end],root,omit=('DFHAID','DFHBMSCA'))
    # SQL INCLUDE is a precompiler declaration, not executable SQL.
    out=[];i=0
    while i<len(selected):
        code,source,line=selected[i];i+=1
        if re.match(r'\s*EXEC SQL',code):
            while 'END-EXEC' not in code:
                code+=' '+selected[i][0];i+=1
            include=re.fullmatch(r'\s*EXEC\s+SQL\s+INCLUDE\s+(SQLCA|AUTHFRDS)\s+END-EXEC[.]\s*',code)
            if not include:raise Unsupported('reference SQL declaration')
            if include[1]=='SQLCA':out += ['01 SQLCODE PIC S9(9) COMP.','01 SQLSTATE PIC X(5).']
            else:
                found=list(root.rglob('AUTHFRDS.dcl'))
                if len(found)!=1:raise Unsupported('reference DCL source')
                dcl=list(logical(found[0].read_bytes(),str(found[0])))
                at=next(j for j,(text,_,_) in enumerate(dcl) if re.match(r'\s*01\s',text))
                out += [text for text,_,_ in dcl[at:]]
        else:out.append(code)
    return layout(('\n'.join('       '+code for code in out)+'\n').encode(),str(path)+':'+section)

class RecordStore:
    """Byte images and keys supplied by the independently loaded fixture.

    Records carry dataset, raw bytes, primary/alternate keys and IMS parent
    identities. Changes are transactional and observable, never read back from
    the candidate to determine expected results.
    """
    def __init__(self,records=()):
        self.records=deepcopy(list(records));self.events=[];self.parent=None;self.position=-1;self.locked={};self.fraud=[]
    def begin(self):self.saved=deepcopy((self.records,self.fraud));self.events=[];self.locked={};self.parent=None;self.position=-1
    def rollback(self):self.records,self.fraud=deepcopy(self.saved);self.events.append({'operation':'ROLLBACK'})
    def read(self,dataset,key,update=False):
        matches=[r for r in self.records if dataset in r['keys'] and r['keys'][dataset]==key]
        matches.sort(key=lambda r:r['identity'])
        record=matches[0] if matches else None
        if update and record is not None:self.locked[dataset]=record
        self.events.append(dict(operation='READ',dataset=dataset,key=key.hex(),found=record is not None,update=update))
        return record
    def rewrite(self,dataset,raw):
        if dataset not in self.locked:raise Unsupported('reference REWRITE without update lock')
        self.locked[dataset]['raw']=raw;self.events.append(dict(operation='REWRITE',dataset=dataset,raw=raw.hex()))

class ScreenReference(SignonReference):
    def __init__(self,root,clock=None,store=None):
        # Avoid parsing the unexpanded procedure in SignonReference.
        from pathlib import Path
        from datetime import timezone
        self.root=Path(root);self.clock=clock or datetime(2026,10,17,12,34,56,tzinfo=timezone.utc)
        self.source=self.find(self.program_name,'.cbl');self.raw=self.source.read_bytes()
        self.program=Program(self.raw,str(self.source),procedure_tokens(self.raw,str(self.source),self.root))
        self.model=parse(self.find(self.mapset,'.bms').read_bytes(),self.mapset+'.bms')['maps'][0] if self.mapset else None
        self.store=store if store is not None else RecordStore();self.trace=[]
    def storage(self):
        m=Memory();m.add(declarations_for(self.raw,self.source,self.root))
        protocol=['01 CICS-ENV.',' 05 EIBCALEN PIC S9(4) COMP.',' 05 EIBAID PIC X.',' 05 EIBRESP PIC S9(9) COMP.',' 05 DIBSTAT PIC X(2).']
        protocol += [' 05 DFH'+name+" PIC X VALUE X'"+value.encode('cp037').hex()+"'." for name,value in AIDS.items()]
        protocol += [' 05 '+name+" PIC X VALUE X'"+value.encode('cp037').hex()+"'." for name,value in SYMBOLS.items()]
        m.add(layout(('\n'.join('       '+line for line in protocol)+'\n').encode(),'reference protocol symbols'))
        if self.program_name=='COPAUS2C':m.add(declarations_for(self.raw,self.source,self.root,'LINKAGE'))
        else:m.add(layout(b'       01 DFHCOMMAREA PIC X(32767).\n','reference linkage capacity'))
        return m
    def interact(self,aid,fields=None,commarea=None):
        self.memory=self.storage();self.input=fields or {};self.frame=None;self.ended=False;self.next_program=self.program_name;self.returned_area=None
        self.store.begin();m=self.memory
        if commarea is not None:
            raw=bytes.fromhex(commarea);m.write('DFHCOMMAREA',raw.decode('cp037'));m.write('EIBCALEN',len(raw))
        else:m.write('EIBCALEN',0)
        m.write('EIBAID',AIDS.get(aid,AIDS['ENTER']))
        self.values=Values(m,clock=self.clock,external=self.external,call=self.call)
        machine=Machine(self.program,self.values)
        try:
            if '0000-MAIN' in self.program.paragraphs:machine.run('0000-MAIN','0000-MAIN-EXIT')
            else:machine.run('MAIN-PARA')
        except Returned:pass
        except TransferScreen as transfer:self.next_program=transfer.program
        except Exception:
            self.store.rollback();raise
        finally:self.trace=machine.trace
        area=self.returned_area if self.returned_area is not None else m.raw('CARDDEMO-COMMAREA')
        return dict(program=self.next_program,screen=self.frame,ended=self.ended,trace=self.trace,commarea=area.hex(),events=self.store.events)
    def response(self,o,values,code=0):
        self.memory.write('EIBRESP',code)
        if 'RESP' in o:values.assign(o['RESP'],code)
        if 'RESP2' in o:values.assign(o['RESP2'],0)
    def external(self,items,values):
        kind,operation,o,flags=self.operands(items);m=self.memory
        if kind=='DLI':return self.dli(operation,o,values)
        if kind=='SQL':return self.sql(items,values)
        if kind!='CICS':raise Unsupported('reference external '+kind)
        if operation=='READ':
            dataset=str(values.value(o.get('DATASET',o.get('FILE')))).strip();r=Reader(o['RIDFLD']);name,start,length=values.reference(r)
            key=m.raw(name)
            if start is not None:key=key[start:] if length is None else key[start:start+length]
            if 'KEYLENGTH' in o:key=key[:int(values.value(o['KEYLENGTH']))]
            record=self.store.read(dataset,key,'UPDATE' in flags);self.response(o,values,13 if record is None else 0)
            if record is not None:values.assign(o['INTO'],record['raw'].decode('cp037'))
        elif operation=='REWRITE':
            dataset=str(values.value(o.get('DATASET',o.get('FILE')))).strip();r=Reader(o['FROM']);name,_,_=values.reference(r)
            raw=m.raw(name)
            if 'LENGTH' in o:raw=raw[:int(values.value(o['LENGTH']))]
            self.store.rewrite(dataset,raw);self.response(o,values)
        elif operation=='SYNCPOINT':
            if 'ROLLBACK' in flags:self.store.rollback()
            self.response(o,values)
        elif operation=='UNLOCK':self.store.locked.clear();self.response(o,values)
        elif operation=='HANDLE':
            if flags not in (['ABEND'],['ABEND','CANCEL']) or set(o)-{'LABEL','PROGRAM'}:raise Unsupported('reference HANDLE grammar')
        elif operation in ('RETURN','XCTL'):
            if 'COMMAREA' in o:
                r=Reader(o['COMMAREA']);name,_,_=values.reference(r);self.returned_area=m.raw(name)
                if 'LENGTH' in o:self.returned_area=self.returned_area[:int(values.value(o['LENGTH']))]
            if operation=='XCTL':raise TransferScreen(str(values.value(o['PROGRAM'])).rstrip())
            raise Returned()
        elif operation=='LINK':
            if str(values.value(o['PROGRAM'])).strip()!='COPAUS2C':raise Unsupported('reference LINK target')
            linked=FraudReference(self.root,self.clock,self.store);linked.memory=linked.storage();linked.values=Values(linked.memory,clock=self.clock,external=linked.external)
            r=Reader(o['COMMAREA']);name,_,_=values.reference(r)
            linked.memory.write('DFHCOMMAREA',m.raw(name).decode('cp037'))
            linked.returned_area=None
            vm=Machine(linked.program,linked.values)
            try:vm.run('MAIN-PARA')
            except Returned:pass
            values.assign(o['COMMAREA'],linked.memory.raw('DFHCOMMAREA').decode('cp037'));self.response(o,values)
        elif operation=='ASKTIME':values.assign(o['ABSTIME'],0)
        elif operation=='FORMATTIME':values.assign(o['MMDDYY'],self.clock.strftime('%m/%d/%y'))
        elif operation=='SEND':
            super().external(items,values)
            if self.frame is not None and 'attributes' in self.frame:
                reverse={v:k for k,v in SYMBOLS.items()}
                for f in self.model['fields']:
                    name=f['name']
                    if not name:continue
                    for suffix in ('A','C'):
                        try:raw=m.raw(name+suffix).decode('cp037')
                        except Unsupported:continue
                        symbol=reverse.get(raw)
                        if suffix=='A' and symbol in BASIC:self.frame['attributes'][name].update(BASIC[symbol])
                        elif suffix=='C' and symbol in COLORS:self.frame['attributes'][name]['color']=COLORS[symbol] or f['color']
        else:super().external(items,values)
    def dli(self,operation,o,values):
        m=self.memory;status='  '
        if operation in ('SCHD','TERM'):pass
        elif operation in ('GU','GNP'):
            segment=''.join(t.text for t in o['SEGMENT']);where=o.get('WHERE');key=None
            if where:
                equals=next(i for i,t in enumerate(where) if t.text=='=');r=Reader(where[equals+1:]);name,_,_=values.reference(r);key=m.raw(name)
            records=[r for r in self.store.records if r.get('segment')==segment]
            if operation=='GNP':records=[r for r in records if r.get('parent')==self.store.parent]
            records.sort(key=lambda r:(r['segment_key'],r['identity']))
            if operation=='GU':self.store.position=-1;self.store.parent=None
            candidate=next(((i,r) for i,r in enumerate(records) if (key is None or r['segment_key']==key) and (operation=='GU' or i>self.store.position)),None)
            if candidate is None:status='GE'
            else:
                index,record=candidate;values.assign(o['INTO'],record['raw'].decode('cp037'))
                if operation=='GU':self.store.parent=record['identity'];self.store.position=-1
                else:self.store.position=index;self.store.locked[segment]=record
        elif operation=='REPL':
            segment=''.join(t.text for t in o['SEGMENT']);r=Reader(o['FROM']);name,_,_=values.reference(r)
            self.store.rewrite(segment,m.raw(name))
        else:raise Unsupported('reference DLI operation '+operation)
        m.write('DIBSTAT',status)
    def call(self,items,values):
        # CEEDAYS is a native library port, bounded to the mask used by this slice.
        r=Reader(items);name=values.atom(r)
        if name!='CSUTLDTC':raise Unsupported('reference CALL target')
        r.pop('USING');args=values.operands(r.items[r.at:])
        if len(args)!=3 or str(values.value(args[1])).strip()!='YYYYMMDD':raise Unsupported('reference date library contract')
        text=str(values.value(args[0])).strip()
        try:datetime.strptime(text,'%Y%m%d')
        except ValueError:raise Unsupported('invalid date reached CEEDAYS port; no native feedback-code claim')
        # The source wrapper passes zero severity/message for a valid date.
        values.assign(args[2],'0000'+' '*11+'0000'+' '+'Date is valid'.ljust(15)+' '+' '*9+text.ljust(10)+' '+' '*10+'YYYYMMDD'.ljust(10))
    def sql(self,items,values):raise Unsupported('SQL outside linked fraud adapter')

class AccountViewReference(ScreenReference):program_name='COACTVWC';mapset='COACTVW'
class AccountUpdateReference(ScreenReference):program_name='COACTUPC';mapset='COACTUP'
class AuthorizationListReference(ScreenReference):program_name='COPAUS0C';mapset='COPAU00'
class AuthorizationDetailReference(ScreenReference):program_name='COPAUS1C';mapset='COPAU01'

class FraudReference(ScreenReference):
    program_name='COPAUS2C';mapset=None
    def sql(self,items,values):
        # Parse the actual source SQL hosts and column order; no field mapping table.
        text=' '.join(t.text for t in items);m=self.memory
        def host(name):
            if name=='MERCHANT-NAME':return m.read('MERCHANT-NAME-TEXT')[:int(m.read('MERCHANT-NAME-LEN'))]
            value=m.read(name)
            return value if isinstance(value,Decimal) else value.rstrip(' ')
        def timestamp(value):return datetime.strptime(value,'%y-%m-%d %H.%M.%S%f').isoformat(sep=' ')
        if text.startswith('SQL INSERT INTO CARDDEMO . AUTHFRDS'):
            columns=text.split('(',1)[1].split(')',1)[0].split();hosts=re.findall(r': ([A-Z][A-Z0-9-]*)',text)
            if len(columns)!=26 or len(hosts)!=25:raise Unsupported('reference SQL INSERT arity')
            row={};at=0
            for column in columns:
                if column=='FRAUD_RPT_DATE':value=self.clock.date().isoformat()
                else:value=host(hosts[at]);at+=1
                if column=='AUTH_TS':value=timestamp(value)
                row[column.lower()]=value
            exists=any((r['card_num'],r['auth_ts'])==(row['card_num'],row['auth_ts']) for r in self.store.fraud)
            if not exists:self.store.fraud.append(row)
            m.write('SQLCODE',-803 if exists else 0)
        elif text.startswith('SQL UPDATE CARDDEMO . AUTHFRDS'):
            key=(host('CARD-NUM'),timestamp(host('AUTH-TS')));found=False
            for row in self.store.fraud:
                if (row['card_num'],row['auth_ts'])==key:
                    row.update(auth_fraud=host('AUTH-FRAUD'),fraud_rpt_date=self.clock.date().isoformat());found=True
            m.write('SQLCODE',0 if found else 100)
        else:raise Unsupported('reference SQL statement')
        m.write('SQLSTATE','00000')
