"""Compile a bounded subset of COACTUP edit paragraphs, retaining every token.

This is a source compiler for Java edit execution, not the independent screen
reference. Unsupported syntax is an error, never an omitted validation.
"""
import re
from .web_bindings import active
from .screen_update import paragraph

PARAGRAPHS=('1215-EDIT-MANDATORY','1220-EDIT-YESNO','1225-EDIT-ALPHA-REQD',
    '1230-EDIT-ALPHANUM-REQD','1235-EDIT-ALPHA-OPT','1240-EDIT-ALPHANUM-OPT','1245-EDIT-NUM-REQD')
VERBS={'IF','SET','MOVE','INSPECT','STRING','GO','CONTINUE','EXIT','PERFORM','COMPUTE','END-COMPUTE','DIVIDE','INITIALIZE','CALL','EVALUATE','WHEN','END-EVALUATE','ELSE','END-IF','.'}
TOKEN=re.compile(r"\s+|,|'(?:[^']|'')*'|[0-9]+-[A-Z][A-Z0-9-]*|[A-Z][A-Z0-9-]*|-?[0-9]+|>=|<=|<>|[().:=<>]")

class Parser:
    def __init__(self,code,lines,source,name,performs=PARAGRAPHS):
        self.tokens=[];at=0;self.source=source;self.name=name;self.pos=0;self.performs=set(performs)
        self.labels=set(re.findall(r'^\s*([A-Z][A-Z0-9-]*)\.\s*$',code,re.M))
        for m in TOKEN.finditer(code):
            if m.start()!=at:raise ValueError('unsupported edit token: '+code[at:m.start()])
            at=m.end()
            if not m[0].isspace() and m[0]!=',':self.tokens.append((m[0],lines[m.start()]))
        if code[at:].strip():raise ValueError('unsupported edit tail')
    def peek(self):return self.tokens[self.pos][0] if self.pos<len(self.tokens) else ''
    def take(self,expected=None):
        value=self.peek()
        if not value or expected is not None and value!=expected:raise ValueError(f'edit syntax expected {expected}, found {value}')
        self.pos+=1;return value
    def origin(self):return dict(source=self.source,line=self.tokens[self.pos][1])
    def expr(self):
        origin=self.origin();token=self.take()
        if token.startswith("'"):return dict(op='literal',value=token[1:-1].replace("''","'"),**origin)
        if re.fullmatch('-?[0-9]+',token):return dict(op='number',value=token,**origin)
        if token in ('SPACE','SPACES','LOW-VALUE','LOW-VALUES','ZERO','ZEROS','ZEROES'):
            return dict(op='figurative',value=token,**origin)
        if token=='FUNCTION':
            name=self.take()
            if name=='CURRENT-DATE':return dict(op=name,**origin)
            if name not in ('LENGTH','TRIM','NUMVAL','INTEGER-OF-DATE','TEST-NUMVAL','TEST-NUMVAL-C','NUMVAL-C','UPPER-CASE','LOWER-CASE'):raise ValueError('unsupported edit intrinsic: '+name)
            self.take('(');operand=self.expr();self.take(')');return dict(op=name,operand=operand,**origin)
        if not re.fullmatch('[A-Z][A-Z0-9-]*',token) or token in VERBS:raise ValueError('unsupported edit expression: '+token)
        result=dict(op='field',name=token,**origin)
        if self.peek()=='(':
            self.take();start=self.expr();self.take(':');remaining=self.peek()==')';length=None if remaining else self.expr();self.take(')')
            result=dict(op='slice',operand=result,start=start,length=length,remaining=remaining,**origin)
        if self.peek()=='OF':
            self.take();qualifier=self.take()
            if qualifier not in ('CACTUPAI','CACTUPAO','COPAU0AI','COPAU0AO','COPAU1AI','COPAU1AO'):raise ValueError('unsupported edit qualifier: '+qualifier)
            result['qualifier']=qualifier
        return result
    def condition(self):
        left=self.conjunction()
        while self.peek()=='OR':
            origin=self.origin();self.take();left=dict(op='or',left=left,right=self.conjunction(),**origin)
        return left
    def conjunction(self):
        left=self.predicate()
        while self.peek()=='AND':
            origin=self.origin();self.take();left=dict(op='and',left=left,right=self.predicate(),**origin)
        return left
    def predicate(self):
        origin=self.origin()
        if self.peek()=='NOT':self.take();return dict(op='not',operand=self.predicate(),**origin)
        if self.peek()=='(':
            self.take();value=self.condition();self.take(')');return value
        left=self.expr()
        if self.peek()=='IS':self.take()
        negate=self.peek()=='NOT'
        if negate:self.take()
        if self.peek()=='NUMERIC':
            self.take();result=dict(op='numeric',operand=left,**origin)
        elif self.peek() in ('EQUAL','=','<>','>','<','>=','<='):
            operator=self.take()
            if self.peek()=='TO':self.take()
            result=dict(op='compare',operator=operator,left=left,right=self.expr(),**origin)
        elif left['op']=='field':result=dict(op='condition',name=left['name'],**origin)
        else:raise ValueError('unsupported edit predicate')
        return dict(op='not',operand=result,**origin) if negate else result
    def block(self):
        result=[]
        while self.peek() and self.peek() not in ('ELSE','END-IF','WHEN','END-EVALUATE','.'):
            origin=self.origin();verb=self.take()
            if verb in self.labels and self.peek()=='.':node=dict(op='label',name=verb)
            elif verb=='IF':
                test=self.condition();yes=self.block();no=[]
                if self.peek()=='ELSE':self.take();no=self.block()
                if self.peek()=='END-IF':self.take()
                elif self.peek()!='.':raise ValueError('unterminated edit IF')
                node=dict(op='if',test=test,yes=yes,no=no)
            elif verb=='EVALUATE':
                self.take('TRUE');branches=[]
                while self.peek()=='WHEN':
                    tests=[];default=False
                    while self.peek()=='WHEN':
                        self.take()
                        if self.peek()=='OTHER':self.take();default=True
                        else:tests.append(self.condition())
                    actions=self.block()
                    branches.append(dict(tests=tests,default=default,actions=actions))
                    if default and self.peek()!='END-EVALUATE':raise ValueError('OTHER must be final EVALUATE branch')
                self.take('END-EVALUATE');node=dict(op='evaluate',branches=branches)
            elif verb=='SET':
                target=self.take();self.take('TO');self.take('TRUE');node=dict(op='set',name=target)
            elif verb=='MOVE':
                value=self.expr();self.take('TO');targets=[]
                while self.peek() and self.peek() not in VERBS:targets.append(self.expr())
                if not targets:raise ValueError('edit MOVE has no target')
                node=dict(op='move',value=value,targets=targets)
            elif verb=='COMPUTE':
                target=self.expr();self.take('=');value=self.expr()
                if self.peek()=='END-COMPUTE':self.take()
                node=dict(op='compute',target=target,value=value)
            elif verb=='DIVIDE':
                value=self.expr();self.take('BY');divisor=self.expr();self.take('GIVING');target=self.expr();self.take('REMAINDER');remainder=self.expr()
                node=dict(op='divide',value=value,divisor=divisor,target=target,remainder=remainder)
            elif verb=='INITIALIZE':
                targets=[]
                while self.peek() and self.peek() not in VERBS:targets.append(self.expr())
                if not targets:raise ValueError('edit INITIALIZE has no target')
                node=dict(op='initialize',targets=targets)
            elif verb=='CALL':
                service=self.take();self.take('USING');arguments=[]
                while self.peek() and self.peek() not in VERBS:arguments.append(self.expr())
                if service!="'CSUTLDTC'" or [a.get('name') for a in arguments]!=['WS-EDIT-DATE-CCYYMMDD','WS-DATE-FORMAT','WS-DATE-VALIDATION-RESULT']:
                    raise ValueError('unsupported date service ABI')
                node=dict(op='date-service',arguments=arguments)
            elif verb=='INSPECT':
                target=self.expr();self.take('CONVERTING');before=self.expr();self.take('TO');after=self.expr()
                node=dict(op='convert',target=target,before=before,after=after)
            elif verb=='STRING':
                pieces=[];pending=[]
                while self.peek()!='INTO':
                    if self.peek()=='DELIMITED':
                        self.take();self.take('BY');delimiter=self.take()
                        if delimiter=='SIZE':pieces.extend(pending)
                        elif delimiter in ('SPACE','SPACES') or delimiter.startswith("'"):
                            value=' ' if delimiter in ('SPACE','SPACES') else delimiter[1:-1].replace("''","'")
                            if not value:raise ValueError('empty STRING delimiter')
                            pieces.extend(dict(op='delimited',operand=e,delimiter=value,**origin) for e in pending)
                        else:raise ValueError('unsupported STRING delimiter')
                        pending=[]
                    else:pending.append(self.expr())
                if pending:raise ValueError('STRING operand has no delimiter')
                self.take('INTO');target=self.expr()
                if self.peek()=='END-STRING':self.take()
                node=dict(op='string',pieces=pieces,target=target)
            elif verb=='PERFORM':
                label=self.take();self.take('THRU');end=self.take()
                if label not in self.performs or end!=label+'-EXIT':raise ValueError('unsupported edit perform: '+label)
                node=dict(op='perform',paragraph=label)
            elif verb=='GO':
                self.take('TO');label=self.take()
                if label==self.name+'-EXIT':node=dict(op='return')
                elif label in self.labels:node=dict(op='jump',label=label)
                else:raise ValueError('unsupported edit transfer: '+label)
            elif verb in ('CONTINUE','EXIT'):node=dict(op='continue')
            else:raise ValueError('unsupported edit verb: '+verb)
            result.append(dict(**node,**origin))
        return result
    def parse(self):
        result=[]
        while self.peek():
            result+=self.block()
            if self.peek():self.take('.')
        return result

def declarations(raw,source):
    code,lines=active(raw,source);code=code.split('PROCEDURE DIVISION',1)[0]
    entries=list(re.finditer(r'^\s*(\d\d)\s+([A-Z][A-Z0-9-]*)\b',code,re.M))
    fields={};conditions={};stack=[];parent=None
    for i,m in enumerate(entries):
        level=int(m[1]);name=m[2];end=entries[i+1].start() if i+1<len(entries) else len(code)
        tail=code[m.end():end]
        terminators=[x for x in re.finditer(r"'(?:[^']|'')*'|[0-9]+[.][0-9]+|[.]",tail) if x[0]=='.']
        body=tail[:terminators[0].start()] if terminators else tail
        origin=dict(source=source,line=lines[m.start()+len(m[0])-len(name)])
        if level==88:
            values=re.search(r'\bVALUES?\s+(.+)',body,re.S)
            if values:conditions[name]=dict(parent=parent,text=values[1].strip(),**origin)
            continue
        if name=='FILLER':parent=None;continue
        parent=name
        while stack and stack[-1][0]>=level:stack.pop()
        ancestors=[n for _,n in stack];stack.append((level,name))
        pic=re.search(r'\bPIC\s+(S?9(?:\(\d+\)|9*)(?:V9(?:\(\d+\)|9*))?|X(?:\(\d+\)|X*))(?=\s|$)',body,re.I)
        def digits(part):
            repeat=re.search(r'\((\d+)\)',part)
            return int(repeat[1]) if repeat else len(part)
        parts=pic[1].upper().lstrip('S').split('V') if pic else []
        scale=digits(parts[1]) if len(parts)==2 else 0
        width=sum(digits(part) for part in parts) if pic else None
        value=re.search(r"\bVALUE\s+('(?:[^']|'')*'|SPACES?|LOW-VALUES?|ZERO(?:S|ES)?|\d+)",body)
        fields[name]=dict(type=('number' if pic and pic[1].upper().lstrip('S').startswith('9') else 'text') if pic else 'group',
            length=width,scale=scale,value=value[1] if value else None,
            ancestors=ancestors,body=body,**origin)
    return fields,conditions

def build(raw,source,lookup=None):
    paragraphs={}
    names=PARAGRAPHS+('1250-EDIT-SIGNED-9V2','1260-EDIT-US-PHONE-NUM','1265-EDIT-US-SSN','1270-EDIT-US-STATE-CD','1275-EDIT-FICO-SCORE','1280-EDIT-US-STATE-ZIP-CD') if lookup else PARAGRAPHS
    for name in names:
        code,lines=paragraph(raw,source,name);paragraphs[name]=Parser(code,lines,source,name).parse()
    fields,conditions=declarations(raw,source)
    if lookup:
        extra_fields,extra_conditions=declarations(lookup[1],lookup[0])
        if set(fields)&set(extra_fields) or set(conditions)&set(extra_conditions):
            raise ValueError('ambiguous edit lookup declaration')
        fields.update(extra_fields);conditions.update(extra_conditions)
    bound_fields,bound_conditions=bind_fields(paragraphs,fields,conditions,extra_fields=('WS-EDIT-US-PHONE-NUM','WS-EDIT-US-PHONE-NUM-FLGS') if lookup else ())
    storage=None
    if lookup:
        # Use the actual fixed-format group, including FILLER and REDEFINES.
        # Independent numeric variables would break the source phone flags and
        # numeric views. The existing copybook compiler supplies byte offsets.
        from .schema import copybook
        code,lines=active(raw,source)
        begin=re.search(r'\b05\s+WS-GENERIC-EDITS\.',code)
        end=re.search(r'\b05\s+',code[begin.end():])
        first=lines[begin.start()];last=lines[begin.end()+end.start()]
        physical=raw.decode().splitlines()[first-1:last-1]
        physical[0]=re.sub(r'\b05\b','01',physical[0],count=1)
        layout,_=copybook('\n'*(first-1)+'\n'.join(physical)+'\n',source)
        storage=layout.manifest()
        for name in bound_fields:
            if fields[name]['type']!='group' or 'WS-GENERIC-EDITS' not in fields[name]['ancestors']:continue
            prefix='WS-GENERIC-EDITS.'+name+'.'
            children=[f for f in storage['fields'] if f['path'].startswith(prefix)]
            if not children:raise ValueError('edit storage group absent: '+name)
            start=min(f['offset'] for f in children);finish=max(f['offset']+f['length'] for f in children)
            storage['fields'].append(dict(path='WS-GENERIC-EDITS.'+name,offset=start,length=finish-start,
                digits=0,scale=0,signed=False,usage='DISPLAY',sign='TRAILING',separate=False,line=fields[name]['line']))
    return dict(paragraphs=paragraphs,fields=bound_fields,conditions=bound_conditions,storage=storage,
        limitations=['Generic, monetary, phone, SSN and source state/ZIP/FICO edits; full screen control-flow proof remains pending.'])


def bind_fields(paragraphs,fields,conditions,initial_flags=('INPUT-OK','WS-RETURN-MSG-OFF'),extra_fields=()):
    needed=set(extra_fields);flags=set()
    def walk(value):
        if isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,dict):
            if value.get('op')=='field':needed.add(value['name'])
            if value.get('op')=='date-service':needed.update(('WS-SEVERITY-N','WS-MSG-NO-N'))
            if value.get('op') in ('condition','set'):flags.add(value['name'])
            for item in value.values():walk(item)
    for value in paragraphs.values():walk(value)
    # Caller initializes these source flags and supplies the edit operands.
    flags.update(initial_flags)
    # Flags copied by MOVE still expose their source 88 conditions. Their
    # storage is already referenced; no unseen state or new table is invented.
    flags.update(name for name,c in conditions.items() if c['parent'] in needed)
    bound_conditions={}
    for name in sorted(flags):
        c=conditions.get(name)
        if not c or not c['parent']:raise ValueError('edit condition absent: '+name)
        tokens=[];position=0
        for match in re.finditer(r"\s+|,|'(?:[^']|'')*'|[A-Z][A-Z0-9-]*|\d+",c['text']):
            if match.start()!=position:raise ValueError('unsupported edit condition values: '+name)
            position=match.end()
            if not match[0].isspace() and match[0]!=',':tokens.append(match[0])
        if position!=len(c['text']) or not tokens:raise ValueError('unsupported edit condition values: '+name)
        def valid(t):
            return t in ('SPACE','SPACES','LOW-VALUE','LOW-VALUES','ZERO','ZEROS','ZEROES') or t.startswith("'") or t.isdigit()
        values=[];ranges=[];index=0
        while index<len(tokens):
            lower=tokens[index];index+=1
            if not valid(lower):raise ValueError('unsupported edit condition values: '+name)
            if index<len(tokens) and tokens[index] in ('THRU','THROUGH'):
                index+=1
                if index>=len(tokens) or not valid(tokens[index]):raise ValueError('unsupported edit condition range: '+name)
                ranges.append(dict(lower=lower,upper=tokens[index]));index+=1
            else:values.append(lower)
        needed.add(c['parent']);bound_conditions[name]=dict(parent=c['parent'],values=values,ranges=ranges,source=c['source'],line=c['line'])
    def initial(name):
        if name not in fields:raise ValueError('edit declaration absent: '+name)
        f=fields[name]
        if f['type']=='group' and 'storage_length' in f:
            length=f['storage_length'];value=' '*length
        elif f['type']=='group':
            children=[n for n,v in fields.items() if v['type']!='group' and name in v['ancestors']]
            if not children:raise ValueError('empty edit constant group: '+name)
            value=''.join(initial(n)['initial'] for n in children);length=len(value)
        else:
            if 'OCCURS' in f['body']:raise ValueError('unsupported edit occurrence')
            alias=re.search(r'\bREDEFINES\s+([A-Z][A-Z0-9-]*)',f['body'])
            if alias and not f.get('storage_bound'):
                base=fields.get(alias[1])
                if not base or initial(alias[1])['type']!='text' or initial(alias[1])['length']!=f['length'] or f['type']!='number' or re.search(r'\bCOMP|\bPIC\s+[^. ]*V',f['body']):
                    raise ValueError('unsupported edit alias')
                return dict(type='number',length=f['length'],initial='0',alias_of=alias[1],source=f['source'],line=f['line'])
            length=f['length'];token=f['value'] or ('0' if f['type']=='number' else 'SPACES')
            if token.startswith("'"):value=token[1:-1].replace("''","'").ljust(length)[:length]
            elif token.startswith('LOW-VALUE'):value='\x00'*length
            elif token.startswith('SPACE'):value=' '*length
            else:value=token if f['type']=='number' else '0'*length
        return dict(type='text' if f['type']=='group' else f['type'],length=length,scale=f.get('scale',0),initial=value,explicit_initial=f.get('value') is not None,source=f['source'],line=f['line'])
    bound_fields={name:initial(name) for name in sorted(needed)}
    for item in list(bound_fields.values()):
        if 'alias_of' in item:
            name=item['alias_of'];bound_fields.setdefault(name,initial(name))
    return bound_fields,bound_conditions
