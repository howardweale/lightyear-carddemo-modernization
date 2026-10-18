"""Expressions and predicates for the independent raw-token reference VM."""
from datetime import datetime,date,timezone
from decimal import Decimal,InvalidOperation
import re
from .reference_control import Reader,Unsupported,Token,Figurative

FIGURES={'SPACE':' ','SPACES':' ','LOW-VALUE':'\0','LOW-VALUES':'\0','ZERO':'0','ZEROS':'0','ZEROES':'0'}

class Values:
    def __init__(self,memory,conditions=None,clock=None,external=None,call=None):
        self.memory=memory;self.conditions=conditions or {};self.clock=clock or datetime(2026,10,17,12,0,tzinfo=timezone.utc);self.external_port=external;self.call_port=call
    def value(self,items):
        r=Reader(items);value=self.expression(r)
        if r.peek():raise Unsupported('unconsumed reference expression: '+r.peek())
        return value
    def expression(self,r,minimum=0):
        value=self.atom(r)
        while r.peek() in ('+','-','*','/'):
            priority=2 if r.peek() in ('*','/') else 1
            if priority<minimum:break
            op=r.pop().text;right=self.expression(r,priority+1);a=Decimal(value);b=Decimal(right)
            value=a+b if op=='+' else a-b if op=='-' else a*b if op=='*' else a/b
        return value
    def reference(self,r):
        name=r.pop().text;start=None;length=None
        if r.peek()=='OF':r.pop();r.pop() # qualifiers are checked by unambiguous physical storage lookup
        if r.peek()=='(':
            r.pop();first=self.expression(r)
            if r.peek()==':':
                r.pop();start=int(first)-1
                if r.peek()!=')':length=int(self.expression(r))
            else:name+='['+str(int(first))+']'
            r.pop(')')
        if r.peek()=='OF':r.pop();r.pop()
        self.memory.descriptor(name)
        return name,start,length
    def atom(self,r):
        t=r.peek()
        if t in ('+','-'):
            r.pop();v=Decimal(self.atom(r));return v if t=='+' else -v
        if t=='(':
            r.pop();v=self.expression(r);r.pop(')');return v
        if t.startswith("'"):return r.pop().text[1:-1].replace("''","'")
        if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',t):return Decimal(r.pop().text)
        if t in FIGURES:return Figurative(FIGURES[r.pop().text])
        if t=='LENGTH':
            r.pop();r.pop('OF');name,start,length=self.reference(r);return Decimal(length or self.memory.descriptor(name)[1]['length'])
        if t=='DFHRESP':
            r.pop();r.pop('(');name=r.pop().text;r.pop(')')
            codes={'NORMAL':0,'NOTFND':13,'DUPREC':14,'NOTOPEN':19,'MAPFAIL':36}
            if name not in codes:raise Unsupported('unmapped CICS response')
            return Decimal(codes[name])
        if t=='FUNCTION':
            r.pop();name=r.pop().text
            if name=='CURRENT-DATE':return self.clock.strftime('%Y%m%d%H%M%S')+'00+0000'
            r.pop('(');v=self.expression(r);r.pop(')');text=str(v)
            if name=='UPPER-CASE':return text.upper()
            if name=='LOWER-CASE':return text.lower()
            if name=='TRIM':return text.strip(' ')
            if name=='LENGTH':return Decimal(len(text))
            if name=='INTEGER-OF-DATE':return Decimal((datetime.strptime(text,'%Y%m%d').date()-date(1600,12,31)).days)
            if name in ('NUMVAL','NUMVAL-C','TEST-NUMVAL','TEST-NUMVAL-C'):
                try:
                    candidate=text.strip(' ');currency=name.endswith('-C')
                    if currency:candidate=candidate.replace('$','').replace(',','').strip(' ')
                    if not re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]*)?',candidate):raise ValueError('number grammar')
                    result=Decimal(candidate)
                except (ValueError,InvalidOperation):
                    if name.startswith('TEST-'):return Decimal(1)
                    raise Unsupported('reference NUMVAL input')
                return Decimal(0) if name.startswith('TEST-') else result
            raise Unsupported('reference intrinsic '+name)
        name,start,length=self.reference(r);text=self.memory.display(name)
        if start is not None:
            if start<0 or start>=len(text) or length is not None and (length<1 or start+length>len(text)):raise Unsupported('reference slice bounds')
            return text[start:] if length is None else text[start:start+length]
        return text
    def operands(self,items):
        r=Reader(items);result=[]
        while r.peek():
            begin=r.at;self.atom(r);result.append(items[begin:r.at])
        return result
    def assign(self,items,value,string=False):
        r=Reader(items)
        while r.peek():
            name,start,length=self.reference(r)
            if start is not None:self.memory.write_slice(name,start,length,value)
            elif string:
                previous=self.memory.raw(name).decode('cp037');text=str(value);self.memory.write(name,text[:len(previous)]+previous[min(len(text),len(previous)):])
            else:self.memory.write(name,value)
    def set_condition(self,name):
        if name not in self.conditions:raise Unsupported('reference condition '+name)
        parent,values=self.conditions[name];self.memory.write(parent,self.value(values[:1]))
    def initialize(self,items):
        for operand in self.operands(items):
            r=Reader(operand);name,start,length=self.reference(r)
            if start is not None:raise Unsupported('INITIALIZE slice')
            self.memory.initialize(name)
    @staticmethod
    def compare(a,b):
        if isinstance(a,Figurative):a=str(a)*len(str(b))
        if isinstance(b,Figurative):b=str(b)*len(str(a))
        if isinstance(a,Decimal) or isinstance(b,Decimal):
            try:return (Decimal(a)>Decimal(b))-(Decimal(a)<Decimal(b))
            except InvalidOperation:pass
        a=str(a);b=str(b);n=max(len(a),len(b));a=a.ljust(n).encode('cp037');b=b.ljust(n).encode('cp037');return (a>b)-(a<b)
    def condition(self,name):
        if name not in self.conditions:raise Unsupported('reference condition '+name)
        parent,items=self.conditions[name];actual=self.memory.display(parent);r=Reader(items)
        while r.peek():
            lower=self.atom(r)
            if r.peek() in ('THRU','THROUGH'):
                r.pop();upper=self.atom(r)
                if self.compare(actual,lower)>=0 and self.compare(actual,upper)<=0:return True
            elif self.compare(actual,lower)==0:return True
        return False
    def predicate(self,items):
        r=Reader(items);last=[None]
        def comparison():
            if r.peek()=='NOT':r.pop();return not comparison()
            if r.peek()=='(':
                r.pop();answer=disjunction();r.pop(')');return answer
            begin=r.at
            if r.peek() in self.conditions:
                name=r.pop().text
                if r.peek() in ('','AND','OR',')'):return self.condition(name)
                r.at=begin
            left=self.expression(r)
            if r.peek()=='IS':r.pop()
            negate=r.peek()=='NOT'
            if negate:r.pop()
            if r.peek()=='NUMERIC':
                r.pop();answer=bool(re.fullmatch('[0-9]+',str(left)));return not answer if negate else answer
            op=r.peek()
            if op in ('EQUAL','=', '<>','>','<','>=','<='):
                r.pop()
                if r.peek()=='TO':r.pop()
                right=self.expression(r);last[0]=(left,op)
            elif last[0] is not None and not negate:
                right=left;left,op=last[0]
            else:raise Unsupported('reference predicate operator '+op)
            c=self.compare(left,right);answer={'EQUAL':c==0,'=':c==0,'<>':c!=0,'>':c>0,'<':c<0,'>=':c>=0,'<=':c<=0}[op]
            return not answer if negate else answer
        def conjunction():
            value=comparison()
            while r.peek()=='AND':r.pop();other=comparison();value=value and other
            return value
        def disjunction():
            value=conjunction()
            while r.peek()=='OR':r.pop();other=conjunction();value=value or other
            return value
        answer=disjunction()
        if r.peek():raise Unsupported('unconsumed reference predicate '+r.peek())
        return answer
    def external(self,items):
        if self.external_port is None:raise Unsupported('external adapter required')
        return self.external_port(items,self)
    def call(self,items):
        if self.call_port is None:raise Unsupported('CALL adapter required')
        return self.call_port(items,self)
