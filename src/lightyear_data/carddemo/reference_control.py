"""Independent, bounded control-flow interpreter for raw fixed-format COBOL.

This module does not import the production edit compiler or execute its AST.
Storage and CICS/SQL adapters are explicit ports. Unsupported statements fail
closed. A control-flow test is not a complete six-screen equivalence receipt.
"""
from dataclasses import dataclass, field
from decimal import Decimal
import re

class Unsupported(ValueError):pass

class Figurative(str):
    """A COBOL figurative constant repeats to the receiving/comparison width."""
    pass

@dataclass(frozen=True)
class Token:
    text:str
    source:str
    line:int

LEX=re.compile(r"\s+|,|'(?:[^']|'')*'|[0-9]+(?:\.[0-9]+)?(?![A-Z0-9-])|[A-Z0-9][A-Z0-9_-]*|>=|<=|<>|[().:+*/=<>-]",re.I)

def tokens(raw,source):
    result=[]
    for line_number,line in enumerate(raw.decode().splitlines(),1):
        if len(line)<7 or line[6] in '*/':continue
        if line[6]=='-':raise Unsupported(f'{source}:{line_number}: continuation requires expansion')
        code=line[7:72];position=0
        for match in LEX.finditer(code):
            if match.start()!=position:raise Unsupported(f'{source}:{line_number}: token {code[position:match.start()]}')
            position=match.end();text=match[0]
            if not text.isspace() and text!=',':result.append(Token(text if text.startswith("'") else text.upper(),source,line_number))
        if code[position:].strip():raise Unsupported(f'{source}:{line_number}: trailing syntax')
    return result

VERBS={'MOVE','SET','IF','EVALUATE','PERFORM','GO','CONTINUE','EXIT','EXEC','CALL','INITIALIZE','INSPECT','STRING','COMPUTE','ADD','SUBTRACT','DIVIDE','SEARCH','DISPLAY'}
STOPS={'AT','ELSE','END-IF','WHEN','END-EVALUATE','END-PERFORM','END-SEARCH','.'}

@dataclass
class Statement:
    verb:str
    operands:list
    origin:Token
    children:list=field(default_factory=list)

class Reader:
    def __init__(self,items):self.items=items;self.at=0
    def peek(self):return self.items[self.at].text if self.at<len(self.items) else ''
    def pop(self,expected=None):
        if not self.peek() or expected is not None and self.peek()!=expected:raise Unsupported(f'expected {expected}, found {self.peek()}')
        token=self.items[self.at];self.at+=1;return token
    def until(self,stops,verbs=False):
        start=self.at;depth=0
        while self.peek():
            t=self.peek()
            if depth==0 and (t in stops or verbs and t in VERBS):break
            self.at+=1
            if t=='(':depth+=1
            elif t==')':depth-=1
            if depth<0:raise Unsupported('unbalanced expression')
        if depth:raise Unsupported('unterminated expression')
        return self.items[start:self.at]
    def block(self):
        statements=[]
        while self.peek() and self.peek() not in STOPS:
            origin=self.pop();verb=origin.text
            if verb not in VERBS:raise Unsupported(f'{origin.source}:{origin.line}: statement {verb}')
            if verb=='IF':
                condition=self.until(STOPS,True);yes=self.block();no=[]
                if self.peek()=='ELSE':self.pop();no=self.block()
                if self.peek()=='END-IF':self.pop()
                elif self.peek()!='.':raise Unsupported('unclosed IF')
                statements.append(Statement(verb,condition,origin,[yes,no]))
            elif verb=='EVALUATE':
                subject=self.until({'WHEN'});branches=[]
                while self.peek()=='WHEN':
                    choices=[]
                    while self.peek()=='WHEN':self.pop();choices.append(self.until(STOPS,True))
                    branches.append((choices,self.block()))
                self.pop('END-EVALUATE');statements.append(Statement(verb,subject,origin,branches))
            elif verb=='PERFORM':
                header=self.until(STOPS,True)
                if header and header[0].text in ('VARYING','UNTIL','WITH') or any(t.text=='TIMES' for t in header):
                    body=self.block();self.pop('END-PERFORM');statements.append(Statement('LOOP',header,origin,[body]))
                else:statements.append(Statement(verb,header,origin))
            elif verb=='EXEC':
                operands=self.until({'END-EXEC'});self.pop('END-EXEC');statements.append(Statement(verb,operands,origin))
            elif verb=='STRING':
                operands=self.until(STOPS|{'END-STRING'},True)
                if self.peek()=='END-STRING':self.pop()
                statements.append(Statement(verb,operands,origin))
            elif verb=='SEARCH':
                header=self.until({'AT','WHEN'});otherwise=[]
                if self.peek()=='AT':self.pop();self.pop('END');otherwise=self.block()
                self.pop('WHEN');condition=self.until(STOPS,True);body=self.block();self.pop('END-SEARCH')
                statements.append(Statement(verb,header,origin,[condition,body,otherwise]))
            else:
                operands=self.until(STOPS|{'END-COMPUTE','END-CALL','END-ADD','END-SUBTRACT'},True)
                if self.peek() in ('END-COMPUTE','END-CALL','END-ADD','END-SUBTRACT'):self.pop()
                statements.append(Statement(verb,operands,origin))
        return statements

class Program:
    def __init__(self,raw,source,items=None):
        items=tokens(raw,source) if items is None else items
        start=next((i+3 for i in range(len(items)-2) if [x.text for x in items[i:i+3]]==['PROCEDURE','DIVISION','.']),None)
        if start is None:raise Unsupported('PROCEDURE DIVISION absent')
        items=items[start:];self.paragraphs={};self.order=[];reader=Reader(items)
        while reader.peek():
            label=reader.pop();reader.pop('.')
            duplicate=label.text in self.paragraphs
            body=[]
            while reader.peek():
                # Paragraph labels begin a physical line and are followed by a period.
                if reader.at+1<len(items) and items[reader.at+1].text=='.' and reader.peek() not in VERBS:break
                body+=reader.block()
                if reader.peek()=='.':reader.pop()
                elif reader.peek():raise Unsupported('unconsumed paragraph scope')
            if duplicate:
                # The pinned COACTVWC repeats one adjacent EXIT-only paragraph.
                previous=self.paragraphs[label.text]
                if self.order[-1]!=label.text or any(s.verb!='EXIT' or s.operands for s in previous+body):raise Unsupported('duplicate executable paragraph')
                continue
            self.paragraphs[label.text]=body;self.order.append(label.text)

class Transfer(Exception):
    def __init__(self,target):self.target=target

class Machine:
    """State port supplies raw-source storage semantics and external operations.

    Required methods: value(tokens), assign(tokens,value,string=False),
    predicate(tokens), set_condition(name), initialize(tokens), external(tokens).
    Adapters must not use the candidate service or its generated edit AST.
    """
    def __init__(self,program,state,limit=100000):self.program=program;self.state=state;self.limit=limit;self.steps=0;self.trace=[]
    @staticmethod
    def split(items,separator):
        depth=0
        for i,t in enumerate(items):
            if t.text=='(':depth+=1
            elif t.text==')':depth-=1
            elif depth==0 and t.text==separator:return items[:i],items[i+1:]
        raise Unsupported('missing '+separator)
    def run(self,name,through=None):
        start=self.program.order.index(name);end=self.program.order.index(through or name)
        if end<start:raise Unsupported('backward performed range')
        index=start
        while index<=end:
            try:self.execute(self.program.paragraphs[self.program.order[index]])
            except Transfer as jump:
                if jump.target not in self.program.paragraphs:raise Unsupported('unknown GO TO')
                target=self.program.order.index(jump.target)
                if not start<=target<=end:raise
                index=target;continue
            index+=1
    def execute(self,statements):
        for stmt in statements:
            self.steps+=1
            if self.steps>self.limit:raise Unsupported('reference step bound')
            self.trace.append((stmt.origin.source,stmt.origin.line));args=stmt.operands;verb=stmt.verb
            if verb=='IF':self.execute(stmt.children[0 if self.state.predicate(args) else 1])
            elif verb=='EVALUATE':
                true=len(args)==1 and args[0].text=='TRUE';subject=None if true else self.state.value(args)
                for choices,body in stmt.children:
                    if any(len(c)==1 and c[0].text=='OTHER' or (self.state.predicate(c) if true else (self.state.compare(self.state.value(c),subject)==0 if hasattr(self.state,'compare') else self.state.value(c)==subject)) for c in choices):self.execute(body);break
            elif verb=='MOVE':
                value,targets=self.split(args,'TO');self.state.assign(targets,self.state.value(value))
            elif verb=='COMPUTE':
                target,value=self.split(args,'=');self.state.assign(target,self.state.value(value))
            elif verb=='SET':
                names,value=self.split(args,'TO')
                if [t.text for t in value]!=['TRUE']:raise Unsupported('SET requires TRUE')
                for name in names:self.state.set_condition(name.text)
            elif verb=='PERFORM':
                texts=[t.text for t in args]
                if len(texts)==1:self.run(texts[0])
                elif len(texts)==3 and texts[1] in ('THRU','THROUGH'):self.run(texts[0],texts[2])
                else:raise Unsupported('PERFORM range syntax')
            elif verb=='GO':
                if len(args)!=2 or args[0].text!='TO':raise Unsupported('GO syntax')
                raise Transfer(args[1].text)
            elif verb=='INSPECT':
                if any(t.text=='CONVERTING' for t in args):
                    target,tail=self.split(args,'CONVERTING');before,after=self.split(tail,'TO')
                    before=str(self.state.value(before));after=str(self.state.value(after))
                    if len(before)!=len(after) or len(set(before))!=len(before):raise Unsupported('reference conversion alphabet')
                    value=str(self.state.value(target)).translate(str.maketrans(before,after))
                else:
                    target,tail=self.split(args,'REPLACING')
                    if not tail or tail[0].text!='ALL':raise Unsupported('reference INSPECT mode')
                    before,after=self.split(tail[1:],'BY');before=str(self.state.value(before));after=str(self.state.value(after))
                    if not before or len(before)!=len(after):raise Unsupported('reference replacement width')
                    value=str(self.state.value(target)).replace(before,after)
                self.state.assign(target,value)
            elif verb=='DIVIDE':
                numerator,tail=self.split(args,'BY');divisor,tail=self.split(tail,'GIVING');target,remainder=self.split(tail,'REMAINDER')
                a=Decimal(self.state.value(numerator));b=Decimal(self.state.value(divisor));quotient=int(a/b)
                self.state.assign(target,Decimal(quotient));self.state.assign(remainder,a-Decimal(quotient)*b)
            elif verb=='SEARCH':
                names=[t.text for t in args]
                if len(names)!=2 or names[0]!='ALL':raise Unsupported('reference SEARCH mode')
                candidates=[(index,count) for index,(table,count) in self.state.memory.indexes.items() if table.split('.')[-1]==names[1]]
                if len(candidates)!=1:raise Unsupported('reference SEARCH index')
                index,count=candidates[0]
                for position in range(1,count+1):
                    self.state.memory.index_values[index]=position
                    if self.state.predicate(stmt.children[0]):self.execute(stmt.children[1]);break
                else:self.execute(stmt.children[2])
            elif verb=='DISPLAY':
                self.state.operands(args)  # Evaluate source diagnostics without emitting fixture data.
            elif verb=='INITIALIZE':self.state.initialize(args)
            elif verb=='EXEC':self.state.external(args)
            elif verb=='CALL':self.state.call(args)
            elif verb=='STRING':
                before,target=self.split(args,'INTO');parts=[]
                while before:
                    operands,tail=self.split(before,'DELIMITED')
                    if len(tail)<2 or tail[0].text!='BY':raise Unsupported('STRING delimiter')
                    delimiter=tail[1];pieces=self.state.operands(operands)
                    for piece in pieces:
                        value=str(self.state.value(piece))
                        if delimiter.text!='SIZE':value=value.split(str(self.state.value([delimiter])),1)[0]
                        parts.append(value)
                    before=tail[2:]
                self.state.assign(target,''.join(parts),string=True)
            elif verb in ('CONTINUE','EXIT'):
                if args:raise Unsupported('EXIT operands')
            elif verb=='LOOP':self.loop(stmt)
            elif verb in ('ADD','SUBTRACT'):
                before,target=self.split(args,'TO' if verb=='ADD' else 'FROM')
                amount=Decimal(self.state.value(before));old=Decimal(self.state.value(target));self.state.assign(target,old+amount if verb=='ADD' else old-amount)
            else:raise Unsupported(f'{stmt.origin.source}:{stmt.origin.line}: runtime {verb}')
    def loop(self,stmt):
        header=stmt.operands
        if not header:raise Unsupported('empty loop')
        if header[0].text=='VARYING':
            target,tail=self.split(header[1:],'FROM');initial,tail=self.split(tail,'BY');increment,condition=self.split(tail,'UNTIL')
            self.state.assign(target,self.state.value(initial))
            while not self.state.predicate(condition):
                self.execute(stmt.children[0]);self.steps+=1
                if self.steps>self.limit:raise Unsupported('reference loop bound')
                self.state.assign(target,Decimal(self.state.value(target))+Decimal(self.state.value(increment)))
        elif header[0].text=='UNTIL':
            while not self.state.predicate(header[1:]):
                self.execute(stmt.children[0]);self.steps+=1
                if self.steps>self.limit:raise Unsupported('reference loop bound')
        elif header[-1].text=='TIMES':
            count=int(self.state.value(header[:-1]))
            if not 0<=count<=self.limit:raise Unsupported('reference TIMES bound')
            for _ in range(count):self.execute(stmt.children[0])
        else:raise Unsupported('reference loop header')
