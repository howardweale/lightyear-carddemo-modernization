"""Generic scenario step 1: bound, typed, conservative COBOL translation.

No solver, execution, scenario generation or proof. Unsupported source is retained
as located issues. Data-flow is a may-dependency graph, never reaching-definition proof.
"""
from dataclasses import dataclass, asdict
from decimal import Decimal
import hashlib
import re
from .source import tokenize, SourceError
from .records import compile_copybook, LayoutError


@dataclass(frozen=True)
class BoundSource:
    path: str
    text: str
    sha256: str

    def tokens(self):
        if hashlib.sha256(self.text.encode('utf-8')).hexdigest() != self.sha256:
            raise ValueError('source-hash-mismatch:' + self.path)
        return tokenize(self.text, self.path)


@dataclass(frozen=True)
class Expression:
    kind: str
    type: str
    value: str = ''
    operands: tuple = ()


class Unsupported(ValueError):
    pass


class Expressions:
    def __init__(self, tokens, symbols):
        self.tokens = tokens; self.symbols = symbols; self.i = 0

    def take(self):
        if self.i == len(self.tokens): raise Unsupported('incomplete-expression')
        t = self.tokens[self.i]; self.i += 1; return t

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def parse(self, minimum=0):
        token = self.take()
        if token == '(':
            left = self.parse()
            if self.take() != ')': raise Unsupported('unbalanced-expression')
        elif token in ('-', '+', 'NOT'):
            child = self.parse(7 if token != 'NOT' else 3)
            expected = 'boolean' if token == 'NOT' else 'decimal'
            if child.type != expected: raise Unsupported('unary-type')
            left = Expression('unary', expected, token, (child,))
        elif re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', token):
            left = Expression('literal', 'decimal', token)
        elif token.startswith(("'", '"')):
            left = Expression('literal', 'text', token[1:-1])
        elif token in self.symbols:
            typ = self.symbols[token]
            if typ is None: raise Unsupported('ambiguous-reference:' + token)
            left = Expression('reference', typ, token)
        else: raise Unsupported('unbound-or-unsupported-expression:' + token)
        priorities = {'OR':1, 'AND':2, '=':3, '<':3, '>':3, '<=':3, '>=':3, '<>':3, '+':4, '-':4, '*':5, '/':5}
        while self.peek() in priorities and priorities[self.peek()] >= minimum:
            op = self.take(); right = self.parse(priorities[op]+1)
            if op in ('AND', 'OR'):
                if left.type != 'boolean' or right.type != 'boolean': raise Unsupported('boolean-type')
                typ='boolean'
            elif op in ('=', '<', '>', '<=', '>=', '<>'):
                if left.type != right.type: raise Unsupported('comparison-type')
                if left.type != 'decimal': raise Unsupported('string-collation-not-translated')
                typ='boolean'
            else:
                if left.type != 'decimal' or right.type != 'decimal': raise Unsupported('arithmetic-type')
                typ='decimal'
            left=Expression('binary',typ,op,(left,right))
        return left


def expression(tokens, symbols):
    # Lexical compound relation operators retain fixed-format source handling.
    joined=[]; i=0
    while i<len(tokens):
        if i+1<len(tokens) and tokens[i]+tokens[i+1] in ('<=','>=','<>'):
            joined.append(tokens[i]+tokens[i+1]);i+=2
        else:joined.append(tokens[i]);i+=1
    parser=Expressions(joined,symbols); value=parser.parse()
    if parser.i!=len(joined):raise Unsupported('trailing-expression:'+str(joined[parser.i:]))
    return value


def references(expr):
    return ({expr.value} if expr.kind=='reference' else set()).union(*(references(x) for x in expr.operands))


def translate(program, copybooks, *, datasets=(), decisions=()):
    """Translate only explicitly hash-bound text; copybooks are an explicit map.

    Fixed record layout compiler supplies PIC/USAGE/offsets. REDEFINES, variable
    OCCURS, qualified/aliased refs, CALL, strings and I/O produce explicit issues.
    No program names or held-out fixtures are used for translation choices.
    """
    issues=[]; bindings={program.path:program.sha256}
    def issue(token, reason):issues.append(dict(**token.location(),reason=reason))
    def expand(source, ancestors=()):
        if source.path in ancestors:raise ValueError('recursive-copy')
        tokens=source.tokens();out=[];i=0
        while i<len(tokens):
            t=tokens[i]
            if t.text!='COPY':out.append(t);i+=1;continue
            end=next((j for j in range(i+1,len(tokens)) if tokens[j].text=='.'),len(tokens))
            if end!=i+2:issue(t,'COPY qualifiers/replacements not supported in step1');i=end+1;continue
            name=tokens[i+1].text.strip("'\"")
            if name not in copybooks:issue(t,'unbound-copybook:'+name);i=end+1;continue
            child=copybooks[name];bindings[child.path]=child.sha256
            out.extend(expand(child,ancestors+(source.path,)));i=end+1
        return out
    tokens=expand(program)
    proc=next((i for i in range(len(tokens)-1) if [tokens[i].text,tokens[i+1].text]==['PROCEDURE','DIVISION']),None)
    if proc is None:raise ValueError('missing-procedure-division')
    fields=[];symbols={}; layouts=[];group=[]
    def flush():
        if not group:return
        # One token per fixed-format line prevents column72 truncation.
        text='\n'.join('       '+t.text for t in group)
        try:
            layout=compile_copybook(text)
            if layout.variable or layout.overlays:
                raise Unsupported('variable-layout-or-alias-requires-separate-translation')
            layouts.append(dict(record=layout.name,length=layout.record_length))
            for f in layout.fields:
                leaf=f.path.split('.')[-1]
                loc=next(t for t in group if t.text==leaf)
                typ='decimal' if f.digits else 'text'
                symbols[leaf]=typ if leaf not in symbols else None
                bounds=None
                if f.digits:
                    unit=Decimal(1).scaleb(-f.scale);hi=(Decimal(10)**f.digits-1)*unit
                    bounds=dict(minimum=str(-hi if f.signed else Decimal(0)),maximum=str(hi),unit=str(unit))
                fields.append(dict(**asdict(f),location=loc.location(),type=typ,domain=bounds))
        except (LayoutError,SourceError,Unsupported) as e:issue(group[0],'layout:'+str(e))
        group.clear()
    # Data clauses are period-terminated, with one independent 01 layout per group.
    clauses=[];part=[]
    for t in tokens[:proc]:
        part.append(t)
        if t.text=='.':clauses.append(part);part=[]
    for clause in clauses:
        words=[t.text for t in clause]
        if len(words)>1 and re.fullmatch(r'[0-9]{2}',words[0]):
            if words[0]=='01':flush()
            if group or words[0]=='01':group.extend(clause)
            else:issue(clause[0],'data-level-outside-record')
        else:flush()
    flush()
    verbs={'MOVE','COMPUTE','ADD','SUBTRACT','MULTIPLY','DIVIDE','IF','ELSE','END-IF','CONTINUE','STOP','GOBACK','CALL','PERFORM','READ','WRITE','REWRITE','OPEN','CLOSE','ACCEPT','DISPLAY','EVALUATE','WHEN','END-EVALUATE','STRING','UNSTRING','GO','INITIALIZE','SET','EXEC'}
    statements=[];edges=[];guards=[];i=proc+2
    while i<len(tokens):
        t=tokens[i];verb=t.text
        if verb=='.':guards.clear();i+=1;continue
        if i+1<len(tokens) and tokens[i+1].text=='.' and verb not in verbs:i+=2;continue # paragraph label
        if verb in ('ELSE','END-IF'):
            if not guards:issue(t,'unmatched-'+verb)
            elif verb=='END-IF':guards.pop()
            else:guards[-1]=dict(guards[-1],outcome=False)
            i+=1;continue
        end=i+1
        while end<len(tokens) and tokens[end].text not in verbs|{'.'}:end+=1
        body=[x.text for x in tokens[i+1:end]];i=end
        try:
            if verb=='IF':
                if body and body[-1]=='THEN':body.pop()
                expr=expression(body,symbols)
                if expr.type!='boolean':raise Unsupported('IF-requires-boolean')
                sid=len(statements);statements.append(dict(kind='condition',location=t.location(),expression=asdict(expr),guards=list(guards)))
                guards.append(dict(statement=sid,outcome=True));continue
            if verb=='CONTINUE':continue
            if verb in ('STOP','GOBACK'):
                if (verb=='STOP' and body!=['RUN']) or (verb=='GOBACK' and body):raise Unsupported('termination-form')
                statements.append(dict(kind='termination',location=t.location(),guards=list(guards)));continue
            if verb=='COMPUTE':
                if len(body)<3 or body[1]!='=':raise Unsupported('COMPUTE-form')
                target=body[0];expr=expression(body[2:],symbols)
            elif verb in ('MOVE','ADD','SUBTRACT','MULTIPLY','DIVIDE'):
                marker={'MOVE':'TO','ADD':'TO','SUBTRACT':'FROM','MULTIPLY':'BY','DIVIDE':'INTO'}[verb]
                k=body.index(marker)
                if k+2!=len(body):raise Unsupported('multiple-target-or-GIVING')
                target=body[-1];expr=expression(body[:k],symbols)
                if verb!='MOVE':
                    old=expression([target],symbols);op={'ADD':'+','SUBTRACT':'-','MULTIPLY':'*','DIVIDE':'/'}[verb]
                    if old.type!='decimal' or expr.type!='decimal':raise Unsupported('arithmetic-type')
                    expr=Expression('binary','decimal',op,(old,expr))
            else:raise Unsupported('unsupported-verb:'+verb)
            if target not in symbols or symbols[target] is None:raise Unsupported('unknown-or-ambiguous-target:'+target)
            if symbols[target]!=expr.type:raise Unsupported('implicit-conversion-not-translated')
            sid=len(statements)
            statements.append(dict(kind='assignment',verb=verb,target=target,expression=asdict(expr),location=t.location(),guards=list(guards),receiving_conversion='PIC truncation/overflow must be modeled in solver step'))
            for ref in sorted(references(expr)):edges.append(dict(source=ref,target=target,statement=sid,kind='may-data-dependency'))
        except (Unsupported,ValueError) as e:issue(t,str(e))
    if guards:issue(tokens[-1],'unterminated-IF')
    for d in datasets:
        if not isinstance(d,dict) or set(d)!={'dataset','record','keys'}:raise ValueError('dataset-binding-shape')
        if d['record'] not in {l['record'] for l in layouts}:raise ValueError('dataset-record-unbound')
        known={f['path'] for f in fields}
        if not all(k in known for k in d['keys']):raise ValueError('dataset-key-unbound')
    return dict(schema='generic-scenario-ir/1',stage=1,sources=bindings,fields=fields,layouts=layouts,
                statements=statements,data_flow=edges,issues=issues,datasets=list(datasets),decisions=list(decisions),
                translation_complete=not issues,flow_semantics='conservative may-dependencies; no reaching-definition/solver proof',
                solver_calls=0,model_calls=0,executions=0,releasable=False)
