"""Byte storage for the raw-source reference, independent of the Java codec.

Screen adapters compile pinned declarations with reference_declarations,
independently of the candidate binding generator. No candidate edit AST or
candidate values are read. BMS model parsing is still a shared dependency.
"""
from decimal import Decimal, ROUND_DOWN
import re
from .reference_control import Unsupported,Figurative

class Memory:
    def __init__(self):self.regions=[];self.names={};self.conditions={};self.entries={};self.indexes={};self.index_values={}
    def add(self,layout,source_text=''):
        region=bytearray(b'\x40'*layout['record_length']);index=len(self.regions);self.regions.append(region)
        fields=layout['fields'];groups={};seen=set()
        for f in fields:
            path=f['path'];name=path.split('.')[-1]
            self._register(path,(index,f))
            if name!=path:self._register(name,(index,f))
            parts=path.split('.')
            for i in range(1,len(parts)):
                prefix='.'.join(parts[:i]);span=groups.setdefault(prefix,[f['offset'],f['offset']+f['length']]);span[0]=min(span[0],f['offset']);span[1]=max(span[1],f['offset']+f['length'])
            positions=set(range(f['offset'],f['offset']+f['length']))
            if not positions&seen:self.write(path,Decimal(0) if f['digits'] else '')
            seen|=positions
        for group in layout.get("groups",[]):groups[group["path"]]=[group["offset"],group["offset"]+group["length"]]
        for path,(start,end) in groups.items():
            f=dict(path=path,offset=start,length=end-start,digits=0,scale=0,usage='DISPLAY',signed=False)
            self._register(path,(index,f));name=path.split('.')[-1]
            if name!=path:self._register(name,(index,f))
        for name,value in layout.get("initials",[]):self.write(name,value)
        for name,item in layout.get('conditions',{}).items():
            self.conditions[name]=None if name in self.conditions else item
        self.indexes.update(layout.get('indexes',{}))
        self.index_values.update({name:1 for name in layout.get('indexes',{})})
        lines=source_text.splitlines()
        for f in fields:
            line=f.get('line',0)
            if not 1<=line<=len(lines):continue
            match=re.search(r"\bVALUE\s+('(?:[^']|'')*'|ZERO(?:S|ES)?|SPACES?|[-+]?[0-9]+)",lines[line-1],re.I)
            if match:
                token=match[1];value=token[1:-1].replace("''","'") if token.startswith("'") else '' if token.upper().startswith('SPACE') else Decimal(0) if token.upper().startswith('ZERO') else Decimal(token)
                self.write(f['path'],value)
    def _register(self,name,item):
        self.entries[(item[0],item[1]["path"])]=item
        if name in self.names and self.names[name]!=item:self.names[name]=None
        else:self.names[name]=item
    def descriptor(self,name):
        if name in self.names and self.names[name] is not None:return self.names[name]
        indexes=re.findall(r'\[([0-9]+)\]',name);plain=re.sub(r'\[[0-9]+\]','',name)
        matches=[]
        for item in self.entries.values():
            path=item[1]['path'];candidate=re.sub(r'\[[0-9]+\]','',path)
            wanted=plain.split('.');actual=candidate.split('.')
            # COBOL OF/IN may omit intervening groups. Each supplied qualifier
            # must occur in ancestor order, with the exact elementary leaf.
            qualified=actual[-1]==wanted[-1];cursor=0
            for qualifier in wanted[:-1]:
                try:cursor=actual[:-1].index(qualifier,cursor)+1
                except ValueError:qualified=False;break
            if qualified and re.findall(r'\[([0-9]+)\]',path)==indexes:matches.append(item)
        if len(matches)!=1:raise Unsupported('reference storage absent/ambiguous: '+name)
        return matches[0]
    def raw(self,name):
        region,f=self.descriptor(name);return bytes(self.regions[region][f['offset']:f['offset']+f['length']])
    def read(self,name):
        _,f=self.descriptor(name);raw=self.raw(name)
        if not f['digits']:return raw.decode('cp037')
        usage=f['usage'];negative=False
        if usage in ('BINARY','COMP-5'):number=int.from_bytes(raw,'big',signed=f['signed'])
        elif usage=='COMP-3':
            nibbles=raw.hex().upper();sign=nibbles[-1];digits=nibbles[:-1]
            if sign not in ('C','D','F') or not digits.isdigit():raise Unsupported('invalid reference packed decimal')
            number=int(digits)*(-1 if sign=='D' else 1)
        elif usage=='DISPLAY':
            data=bytearray(raw)
            if f['signed']:
                at=0 if f.get('sign')=='LEADING' else len(data)-1
                if f.get('separate'):
                    sign=bytes([data.pop(at)]).decode('cp037')
                    if sign not in ('+','-'):raise Unsupported('invalid reference separate sign')
                    negative=sign=='-'
                else:
                    zone=data[at]>>4
                    if zone not in (12,13,15):raise Unsupported('invalid reference zoned sign')
                    negative=zone==13;data[at]=0xF0|(data[at]&15)
            if any(not 0xF0<=b<=0xF9 for b in data):
                if not f['signed'] and not f['scale']:return bytes(data).decode('cp037')
                raise Unsupported('invalid reference numeric bytes')
            number=int(bytes(data).decode('cp037'))*(-1 if negative else 1)
        else:raise Unsupported('reference usage '+usage)
        return Decimal(number).scaleb(-f['scale'])
    def display(self,name):
        _,f=self.descriptor(name);v=self.read(name)
        if not isinstance(v,Decimal):return v
        digits=str(abs(int(v.scaleb(f['scale'])))).zfill(f['digits'])
        if f['scale']:digits=digits[:-f['scale']]+'.'+digits[-f['scale']:]
        return ('-' if v<0 else '')+digits
    def write(self,name,value):
        region,f=self.descriptor(name);width=f['length']
        figurative=isinstance(value,Figurative)
        if figurative:value=str(value)*width
        if not f['digits']:
            # Internal alphanumeric MOVE truncates at the receiving width.
            if f.get('edited') and not figurative and str(value).strip(' \0'):
                value=self.edit_number(value,f['expanded'])
            text=str(value).encode('cp037');raw=text[-width:].rjust(width,b'\x40') if f.get('justified') else text[:width].ljust(width,b'\x40')
        elif isinstance(value,str) and f['usage']=='DISPLAY' and not f['signed'] and not f['scale'] and not value.isdigit():
            raw=value.encode('cp037')[:width].ljust(width,b'\x40')
        else:
            number=Decimal(value).scaleb(f['scale']).to_integral_value(rounding=ROUND_DOWN);integer=int(number)
            if abs(integer)>=10**f['digits'] and f['usage']!='COMP-5':integer=(abs(integer)%(10**f['digits']))*(-1 if integer<0 else 1)
            if integer<0 and not f['signed']:integer=abs(integer)
            digits=str(abs(integer)).zfill(f['digits'])
            if f['usage'] in ('BINARY','COMP-5'):raw=integer.to_bytes(width,'big',signed=f['signed'])
            elif f['usage']=='COMP-3':raw=bytes.fromhex((digits+('D' if integer<0 else 'C' if f['signed'] else 'F')).zfill(width*2))
            elif f['usage']=='DISPLAY':
                raw=bytearray(digits.encode('cp037'))
                if f['signed']:
                    if f.get('separate'):
                        sign=('-' if integer<0 else '+').encode('cp037');raw=sign+raw if f.get('sign')=='LEADING' else raw+sign
                    else:
                        at=0 if f.get('sign')=='LEADING' else len(raw)-1;raw[at]=(0xD0 if integer<0 else 0xC0)|(raw[at]&15)
            else:raise Unsupported('reference numeric usage')
        if len(raw)!=width:raise Unsupported('reference receiving width')
        self.regions[region][f['offset']:f['offset']+width]=raw
    @staticmethod
    def edit_number(value,picture):
        # Fixed +/-, Z suppression and decimal insertion in the pinned pictures.
        number=Decimal(value);scale=len(picture.split('.')[1]) if '.' in picture else 0
        slots=sum(c in 'Z9' for c in picture);digits=str(abs(int(number.scaleb(scale)))).zfill(slots)[-slots:]
        out=[];at=0;significant=False
        for c in picture:
            if c in 'Z9':
                digit=digits[at];at+=1
                if c=='9' or digit!='0':significant=True
                out.append(digit if significant else ' ')
            elif c==',':out.append(',' if significant else ' ')
            elif c=='+':out.append('-' if number<0 else '+')
            elif c=='-':out.append('-' if number<0 else ' ')
            elif c=='.':out.append('.');significant=True
            else:raise Unsupported('reference edited picture symbol')
        return ''.join(out)
    def write_slice(self,name,start,length,value):
        region,f=self.descriptor(name);n=f['length'];length=n-start if length is None else length
        if start<0 or length<1 or start+length>n:raise Unsupported('reference modification bounds')
        raw=str(value).encode('cp037')[:length].ljust(length,b'\x40');offset=f['offset']+start
        self.regions[region][offset:offset+length]=raw
    def initialize(self,name):
        region,target=self.descriptor(name);prefix=target['path']+'.';seen=set()
        for item in self.names.values():
            if item is None:continue
            r,f=item
            if r!=region or not (f['path']==target['path'] or f['path'].startswith(prefix)):continue
            if any(other is not None and other[0]==r and other[1]['path'].startswith(f['path']+'.') for other in self.names.values()):continue
            positions=set(range(f['offset'],f['offset']+f['length']))
            if not positions&seen and 'FILLER' not in f['path']:self.write(f['path'],Decimal(0) if f['digits'] else '')
            seen|=positions
