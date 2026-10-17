"""Compile a bounded subset of COACTUP edit paragraphs, retaining every token.

This is a source compiler for Java edit execution, not the independent screen
reference. Unsupported syntax is an error, never an omitted validation.
"""
import re
from .web_bindings import active
from .screen_update import paragraph

PARAGRAPHS=('1215-EDIT-MANDATORY','1220-EDIT-YESNO','1225-EDIT-ALPHA-REQD',
    '1230-EDIT-ALPHANUM-REQD','1235-EDIT-ALPHA-OPT','1240-EDIT-ALPHANUM-OPT','1245-EDIT-NUM-REQD')
VERBS={'IF','SET','MOVE','INSPECT','STRING','GO','CONTINUE','EXIT','ELSE','END-IF','.'}
TOKEN=re.compile(r"\s+|,|'(?:[^']|'')*'|[A-Z][A-Z0-9-]*|[0-9]+|>=|<=|<>|[().:=<>]")

class Parser:
    def __init__(self,code,lines,source,name):
        self.tokens=[];at=0;self.source=source;self.name=name;self.pos=0
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
        if token.isdigit():return dict(op='number',value=token,**origin)
        if token in ('SPACE','SPACES','LOW-VALUE','LOW-VALUES','ZERO','ZEROS','ZEROES'):
            return dict(op='figurative',value=token,**origin)
        if token=='FUNCTION':
            name=self.take()
            if name not in ('LENGTH','TRIM','NUMVAL'):raise ValueError('unsupported edit intrinsic: '+name)
            self.take('(');operand=self.expr();self.take(')');return dict(op=name,operand=operand,**origin)
        if not re.fullmatch('[A-Z][A-Z0-9-]*',token) or token in VERBS:raise ValueError('unsupported edit expression: '+token)
        result=dict(op='field',name=token,**origin)
        if self.peek()=='(':
            self.take();start=self.expr();self.take(':');length=self.expr();self.take(')')
            result=dict(op='slice',operand=result,start=start,length=length,**origin)
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
        while self.peek() and self.peek() not in ('ELSE','END-IF','.'):
            origin=self.origin();verb=self.take()
            if verb=='IF':
                test=self.condition();yes=self.block();no=[]
                if self.peek()=='ELSE':self.take();no=self.block()
                if self.peek()=='END-IF':self.take()
                elif self.peek()!='.':raise ValueError('unterminated edit IF')
                node=dict(op='if',test=test,yes=yes,no=no)
            elif verb=='SET':
                target=self.take();self.take('TO');self.take('TRUE');node=dict(op='set',name=target)
            elif verb=='MOVE':
                value=self.expr();self.take('TO');targets=[]
                while self.peek() and self.peek() not in VERBS:targets.append(self.expr())
                if not targets:raise ValueError('edit MOVE has no target')
                node=dict(op='move',value=value,targets=targets)
            elif verb=='INSPECT':
                target=self.expr();self.take('CONVERTING');before=self.expr();self.take('TO');after=self.expr()
                node=dict(op='convert',target=target,before=before,after=after)
            elif verb=='STRING':
                pieces=[]
                while self.peek()!='DELIMITED':pieces.append(self.expr())
                self.take();self.take('BY');self.take('SIZE');self.take('INTO');target=self.expr()
                if self.peek()=='END-STRING':self.take()
                node=dict(op='string',pieces=pieces,target=target)
            elif verb=='GO':
                self.take('TO');label=self.take()
                if label!=self.name+'-EXIT':raise ValueError('unsupported edit transfer: '+label)
                node=dict(op='return')
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
    code,lines=active(raw,source);code=code[:code.index('PROCEDURE DIVISION')]
    entries=list(re.finditer(r'^\s*(\d\d)\s+([A-Z][A-Z0-9-]*)\b',code,re.M))
    fields={};conditions={};stack=[];parent=None
    for i,m in enumerate(entries):
        level=int(m[1]);name=m[2];end=entries[i+1].start() if i+1<len(entries) else len(code)
        body=code[m.end():end].split('.',1)[0];origin=dict(source=source,line=lines[m.start()+len(m[0])-len(name)])
        if level==88:
            values=re.search(r'\bVALUES?\s+(.+)',body,re.S)
            if values:conditions[name]=dict(parent=parent,text=values[1].strip(),**origin)
            continue
        if name=='FILLER':parent=None;continue
        parent=name
        while stack and stack[-1][0]>=level:stack.pop()
        ancestors=[n for _,n in stack];stack.append((level,name))
        pic=re.search(r'\bPIC\s+(S?9|X)(?:\((\d+)\))?(?![A-Z0-9V])',body)
        value=re.search(r"\bVALUE\s+('(?:[^']|'')*'|SPACES?|LOW-VALUES?|ZERO(?:S|ES)?|\d+)",body)
        fields[name]=dict(type=('number' if pic and '9' in pic[1] else 'text') if pic else 'group',
            length=int(pic[2] or 1) if pic else None,value=value[1] if value else None,
            ancestors=ancestors,body=body,**origin)
    return fields,conditions

def build(raw,source):
    paragraphs={}
    for name in PARAGRAPHS:
        code,lines=paragraph(raw,source,name);paragraphs[name]=Parser(code,lines,source,name).parse()
    fields,conditions=declarations(raw,source);needed=set();flags=set()
    def walk(value):
        if isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,dict):
            if value.get('op')=='field':needed.add(value['name'])
            if value.get('op') in ('condition','set'):flags.add(value['name'])
            for item in value.values():walk(item)
    for value in paragraphs.values():walk(value)
    # Caller initializes these source flags and supplies the edit operands.
    flags.update(('INPUT-OK','WS-RETURN-MSG-OFF'))
    bound_conditions={}
    for name in flags:
        c=conditions.get(name)
        if not c or not c['parent']:raise ValueError('edit condition absent: '+name)
        tokens=re.findall(r"'(?:[^']|'')*'|[A-Z][A-Z0-9-]*|\d+",c['text'])
        if not tokens or any(t not in ('SPACE','SPACES','LOW-VALUE','LOW-VALUES','ZERO','ZEROS','ZEROES') and not t.startswith("'") and not t.isdigit() for t in tokens):
            raise ValueError('unsupported edit condition values: '+name)
        needed.add(c['parent']);bound_conditions[name]=dict(parent=c['parent'],values=tokens,source=c['source'],line=c['line'])
    def initial(name):
        if name not in fields:raise ValueError('edit declaration absent: '+name)
        f=fields[name]
        if f['type']=='group':
            children=[n for n,v in fields.items() if v['type']!='group' and name in v['ancestors']]
            if not children:raise ValueError('empty edit constant group: '+name)
            value=''.join(initial(n)['initial'] for n in children);length=len(value)
        else:
            if 'REDEFINES' in f['body'] or 'OCCURS' in f['body']:raise ValueError('unsupported edit alias')
            length=f['length'];token=f['value'] or ('0' if f['type']=='number' else 'SPACES')
            if token.startswith("'"):value=token[1:-1].replace("''","'").ljust(length)[:length]
            elif token.startswith('LOW-VALUE'):value='\x00'*length
            elif token.startswith('SPACE'):value=' '*length
            else:value=token if f['type']=='number' else '0'*length
        return dict(type='text' if f['type']=='group' else f['type'],length=length,initial=value,source=f['source'],line=f['line'])
    return dict(paragraphs=paragraphs,fields={name:initial(name) for name in sorted(needed)},conditions=bound_conditions,
        limitations=['Only seven generic edit paragraphs are translated here. Date, money, phone, cross-field and screen control-flow proof remain pending.'])
