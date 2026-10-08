"""Deterministic boundary/branch proposals and failure-preserving shrinking.

Cases remain proposals until executed with fresh resets. A shrink oracle must
return the exact original failure fingerprint, not merely any failure.
"""
from copy import deepcopy
from .native_evidence import canonical, sha

def boundaries(sql_type):
    import re
    from decimal import Decimal,localcontext
    kind=sql_type.lower().replace(' ','')
    integers={'tinyint':(0,255),'smallint':(-32768,32767),'int':(-2**31,2**31-1),'bigint':(-2**63,2**63-1)}
    if kind in integers:
        low,high=integers[kind];return [None,low,high,0,1]+([-1] if low<0 else [])
    if kind=='bit':return [None,False,True]
    m=re.fullmatch(r'(?:decimal|numeric)\((\d+),(\d+)\)',kind)
    if m or kind in ('money','smallmoney'):
        precision,scale=map(int,m.groups()) if m else (19,4) if kind=='money' else (10,4)
        if not 1<=precision<=38 or not 0<=scale<=precision:raise ValueError('casegen-decimal-contract')
        with localcontext() as ctx:
            ctx.prec=40;unit=Decimal(10)**-scale;maximum=Decimal(10)**(precision-scale)-unit
            minimum=-maximum
            if kind in ('money','smallmoney'):
                bits=63 if kind=='money' else 31
                minimum=-Decimal(2)**bits/10000;maximum=(Decimal(2)**bits-1)/10000
            return [None,'0',str(unit),str(-unit),str(maximum),str(minimum)]
    if kind in ('float','real') or kind.startswith('float('):return [None,0.0,1.0,-1.0,1e-20,1e20]
    if kind=='date':return [None,'0001-01-01','2000-02-29','9999-12-31']
    if kind.startswith('datetime') or kind=='smalldatetime':
        low,high=('1900-01-01','2079-06-06') if kind=='smalldatetime' else ('1753-01-01','9999-12-31') if kind=='datetime' else ('0001-01-01','9999-12-31')
        suffix='+00:00' if kind.startswith('datetimeoffset') else ''
        return [None,low+'T00:00:00'+suffix,'2000-02-29T12:00:00.001667'+suffix,high+'T23:59:00'+suffix]
    if kind.startswith('time'):return [None,'00:00:00','12:00:00.000001','23:59:59.999999']
    if kind=='uniqueidentifier':return [None,'00000000-0000-0000-0000-000000000000','ffffffff-ffff-ffff-ffff-ffffffffffff']
    m=re.fullmatch(r'(n?varchar|n?char|varbinary|binary)\((max|\d+)\)',kind)
    if m:
        size=min(256, int(m[2])) if m[2]!='max' else 256
        return [None,'','00','ff'*size] if 'binary' in m[1] else [None,'',' ','a','A','x'*size]
    if kind in ('text','ntext'):return [None,'',' ','a','A','x'*256]
    raise ValueError('unsupported-casegen-type:'+kind)


def generate(parameters, seeds, *, branch_values=None, trace_cases=()):
    from .invocation import parameter_value
    cases=[deepcopy(seeds)]
    for p in parameters:
        name=p['name'].lstrip('@');kind=p['type'];values=boundaries(kind)
        for v in values+list((branch_values or {}).get(name,[])):
            parameter_value(v,kind)
            c=deepcopy(seeds);c.pop('@'+name,None);c[name]=v;cases.append(c)
    cases.extend(deepcopy(list(trace_cases)))
    unique={canonical(c):c for c in cases}
    return [dict(id=sha(raw),parameters=c,source='proposed-not-executed') for raw,c in sorted(unique.items())]


def complexity(v):
    if v is None:return (0,0)
    if type(v) is bool:return (1,int(v))
    if isinstance(v,(int,float)):return (2,abs(v))
    if isinstance(v,str):return (3,len(v),v)
    return (4,len(canonical(v)))


def shrink(case, fingerprint, oracle, *, maximum_calls=100):
    current=deepcopy(case);calls=0;history=[]
    if not fingerprint:raise ValueError('failure-fingerprint-required')
    for key in sorted(current):
        old=current[key]
        candidates=([None,0,1,-1] if type(old) in (int,float) else [None,'',old[:len(old)//2]] if isinstance(old,str) else [None])
        for value in candidates:
            if calls>=maximum_calls:break
            if value==current[key] or complexity(value)>=complexity(current[key]):continue
            trial=deepcopy(current);trial[key]=value
            observed=oracle(trial);calls+=1
            history.append(dict(case_sha256=sha(canonical(trial)),same_failure=observed==fingerprint))
            if observed==fingerprint:current=trial
    return dict(case=current,minimal_case_sha256=sha(canonical(current)),oracle_calls=calls,
        history=history,minimality='bounded coordinate reduction; not global minimum')
