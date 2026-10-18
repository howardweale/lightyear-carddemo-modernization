"""Independent physical declarations for the bounded raw COBOL reference.

No service bindings or edit ASTs are read. REDEFINES uses the maximum sibling
extent, including the public menu's 12-entry overlay over 11 initialized rows.
Unsupported clauses are rejected, never silently interpreted as padding.
"""
from dataclasses import dataclass,field
from decimal import Decimal
import re
from .reference_control import Unsupported,Figurative,Token

@dataclass
class Declaration:
    level:int
    name:str
    line:int
    source:str
    picture:str=''
    usage:str='DISPLAY'
    sign:str='TRAILING'
    separate:bool=False
    justified:bool=False
    occurs:int=1
    redefines:str=''
    indexes:list=field(default_factory=list)
    initial:object=None
    children:list=field(default_factory=list)
    conditions:list=field(default_factory=list)
    offset:int=0
    width:int=0
    shape:dict=field(default_factory=dict)

WORDS=re.compile(r",|'(?:[^']|'')*'|X'[0-9A-F]*'|[+-]?[0-9]+(?:\.[0-9]+)?|[A-Z][A-Z0-9-]*|[().+*/$,:-]",re.I)

def declarations(raw,source):
    # Period-delimited declarations; quoted periods do not terminate a sentence.
    text='';locations=[]
    for line_no,line in enumerate(raw.decode().splitlines(),1):
        if len(line)<7 or line[6] in '*/':continue
        if line[6]=='-':raise Unsupported('reference declaration continuation: '+source)
        code=line[7:72]+' ';text+=code;locations += [line_no]*len(code)
    rows=[];current=[];position=0
    for match in WORDS.finditer(text):
        if text[position:match.start()].strip():raise Unsupported('reference declaration token '+text[position:match.start()])
        position=match.end();word=match[0];word=word if word.startswith("'") else word.upper()
        if word==',':continue
        # A decimal point embedded in PIC is not a declaration terminator.
        if word=='.' and match.end()<len(text) and not text[match.end()].isspace() and any(t.text in ('PIC','PICTURE') for t in current):
            current.append(Token(word,source,locations[match.start()]));continue
        if word=='.':
            if current:rows.append(current);current=[]
        else:current.append(Token(word,source,locations[match.start()]))
    if current or text[position:].strip():raise Unsupported('reference declaration terminator')
    roots=[];stack=[];filler=0;last=None
    for row in rows:
        words=[t.text for t in row]
        if len(words)<2 or not words[0].isdigit():raise Unsupported('reference data declaration '+str(words[:3]))
        level=int(words[0]);name=words[1]
        if level==88:
            if last is None or words[2] not in ('VALUE','VALUES'):raise Unsupported('reference condition declaration')
            values=row[3:]
            if values and values[0].text in ('IS','ARE'):values=values[1:]
            last.conditions.append((name,values));continue
        if level==77:level=1
        if not 1<=level<=49:raise Unsupported('reference data level '+str(level))
        filler+=name=='FILLER';node=Declaration(level,name if name!='FILLER' else 'FILLER-'+str(filler),row[0].line,source)
        k=2
        while k<len(words):
            word=words[k];k+=1
            if word in ('PIC','PICTURE'):
                if k<len(words) and words[k]=='IS':k+=1
                parts=[]
                while k<len(words) and re.fullmatch(r'[+-]?[SX9AVZB0-9.]+|[().,+*/$-]',words[k]):parts.append(words[k]);k+=1
                node.picture=''.join(parts)
                if not node.picture:raise Unsupported('reference empty picture')
            elif word in ('USAGE','COMP','COMP-3','COMP-5','BINARY','DISPLAY'):
                if word=='USAGE':
                    if words[k]=='IS':k+=1
                    word=words[k];k+=1
                node.usage={'COMP':'BINARY','BINARY':'BINARY','COMP-3':'COMP-3','COMP-5':'COMP-5','DISPLAY':'DISPLAY'}.get(word,'')
                if not node.usage:raise Unsupported('reference usage')
            elif word=='REDEFINES':node.redefines=words[k];k+=1
            elif word=='OCCURS':
                node.occurs=int(words[k]);k+=1
                if not 1<=node.occurs<=32767:raise Unsupported('reference occurrence bound')
                if k<len(words) and words[k]=='TIMES':k+=1
            elif word=='ASCENDING':
                if words[k]=='KEY':k+=1
                if words[k]=='IS':k+=1
                k+=1  # SEARCH ALL validates equality through the interpreted predicate.
            elif word=='INDEXED':
                if words[k]!='BY':raise Unsupported('reference INDEXED clause')
                k+=1;node.indexes.append(words[k]);k+=1
            elif word in ('JUST','JUSTIFIED'):
                if words[k]=='RIGHT':k+=1
                else:raise Unsupported('reference justification')
                node.justified=True
            elif word=='SIGN':
                if words[k]=='IS':k+=1
                node.sign=words[k];k+=1
                if node.sign not in ('LEADING','TRAILING'):raise Unsupported('reference sign')
                if k<len(words) and words[k]=='SEPARATE':
                    node.separate=True;k+=1
                    if k<len(words) and words[k]=='CHARACTER':k+=1
            elif word=='VALUE':
                if words[k]=='IS':k+=1
                value=words[k];k+=1
                if value.startswith("'"):node.initial=value[1:-1].replace("''","'")
                elif value.startswith("X'"):node.initial=bytes.fromhex(value[2:-1]).decode('cp037')
                elif value in ('SPACE','SPACES','LOW-VALUES','LOW-VALUE','ZERO','ZEROS','ZEROES'):
                    node.initial=Figurative(' ' if value.startswith('SPACE') else '\0' if value.startswith('LOW') else '0')
                else:node.initial=Decimal(value)
            else:raise Unsupported('reference declaration clause '+word)
        while stack and stack[-1].level>=level:stack.pop()
        if level==1:roots.append(node)
        elif not stack:raise Unsupported('reference parent absent')
        else:stack[-1].children.append(node)
        stack.append(node);last=node
    return roots

def shape(node):
    if not re.fullmatch(r'S?(?:[X9AVZB+*/$.,-](?:\([0-9]+\))?)+',node.picture):raise Unsupported('reference picture '+node.picture)
    expanded=''.join(symbol*int(count or 1) for symbol,count in re.findall(r'([SX9AVZB+*/$.,-])(?:\(([0-9]+)\))?',node.picture))
    numeric=bool(re.fullmatch(r'S?9+(?:V9*)?',expanded));digits=expanded.count('9') if numeric else 0
    scale=len(expanded.split('V')[1]) if numeric and 'V' in expanded else 0
    if not numeric and node.usage!='DISPLAY':raise Unsupported('reference nonnumeric usage')
    length=(2 if digits<=4 else 4 if digits<=9 else 8) if node.usage in ('BINARY','COMP-5') else (digits+2)//2 if node.usage=='COMP-3' else len(expanded.replace('S','').replace('V',''))+int(node.separate)
    return dict(edited=not numeric and bool(re.fullmatch(r'[+-]?[Z9,]+(?:[.]9+)?',expanded)),expanded=expanded,picture=node.picture,usage=node.usage,digits=digits,scale=scale,signed=expanded.startswith('S'),sign=node.sign,separate=node.separate,justified=node.justified,length=length)

def layout(raw,source):
    roots=declarations(raw,source)
    def size(nodes):
        extent=0;prior={}
        for node in nodes:
            if node.picture:
                if node.children:raise Unsupported('reference elementary child')
                node.shape=shape(node);node.width=node.shape['length']
            else:node.width=size(node.children)
            if node.width<1:raise Unsupported('reference empty group')
            if node.redefines:
                if node.redefines not in prior:raise Unsupported('reference redefine target')
                node.offset=prior[node.redefines].offset
            else:node.offset=extent
            extent=max(extent,node.offset+node.width*node.occurs);prior[node.name]=node
        return extent
    length=size(roots)
    if not 0<length<=1000000:raise Unsupported('reference storage bound')
    fields=[];groups=[];initials=[];conditions={};indexes={}
    def emit(nodes,prefix='',base=0):
        for node in nodes:
            for index in node.indexes:indexes[index]=(prefix+node.name,node.occurs)
            for i in range(1,node.occurs+1):
                name=node.name+('['+str(i)+']' if node.occurs>1 else '');path=prefix+name;offset=base+node.offset+(i-1)*node.width
                if node.picture:fields.append(dict(node.shape,path=path,offset=offset,filler=node.name.startswith('FILLER-'),source=source,line=node.line))
                else:groups.append(dict(path=path,offset=offset,length=node.width));emit(node.children,path+'.',offset)
                if node.initial is not None:initials.append((path,node.initial))
                for condition,values in node.conditions:
                    conditions[path+'.'+condition]=(path,values)
                    conditions[condition]=None if condition in conditions else (path,values)
    emit(roots)
    return dict(record_length=length,fields=fields,groups=groups,initials=initials,conditions=conditions,indexes=indexes)