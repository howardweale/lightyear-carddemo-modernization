"""Inventory-bound RPC and parameter contracts. No SQL text interpolation of values."""
import re
from decimal import Decimal
from datetime import date, datetime, time
from uuid import UUID
from .capture import identifier

def parameter_value(value, sql_type):
    kind=sql_type.lower().replace(' ','')
    if value is None:return None
    if kind in ('tinyint','smallint','int','bigint'):
        if type(value) is not int:raise ValueError('argument-integer-type')
        low,high={'tinyint':(0,255),'smallint':(-32768,32767),'int':(-2**31,2**31-1),'bigint':(-2**63,2**63-1)}[kind]
        if not low<=value<=high:raise ValueError('argument-integer-range')
        return value
    if kind=='bit':
        if type(value) is not bool:raise ValueError('argument-boolean-type')
        return value
    if re.fullmatch(r'(?:n?varchar|n?char)\((?:max|[1-9][0-9]*)\)',kind):
        if not isinstance(value,str):raise ValueError('argument-text-type')
        size=kind.partition('(')[2][:-1]
        if size!='max' and len(value)>int(size):raise ValueError('argument-text-length')
        return value
    if re.fullmatch(r'(?:numeric|decimal)\([0-9]+,[0-9]+\)',kind) or kind in ('money','smallmoney'):
        if isinstance(value,(float,bool)):raise ValueError('argument-exact-decimal-required')
        result=Decimal(str(value))
        if not result.is_finite():raise ValueError('argument-nonfinite')
        if '(' in kind:
            precision,scale=map(int,kind.split('(')[1][:-1].split(','))
            if not 1<=precision<=38 or not 0<=scale<=precision:raise ValueError('argument-decimal-contract')
            digits=result.as_tuple();fraction=max(0,-digits.exponent)
            if fraction>scale or result.adjusted()+1>precision-scale:raise ValueError('argument-decimal-range-or-scale')
        return result
    if kind in ('float','real') or re.fullmatch(r'float\([0-9]+\)',kind):
        import math
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('argument-float')
        return float(value)
    if kind in ('text','ntext'):
        if not isinstance(value,str):raise ValueError('argument-text-type')
        return value
    if kind=='date':return date.fromisoformat(value)
    if kind.startswith('datetime') or kind=='smalldatetime':return datetime.fromisoformat(value)
    if kind.startswith('time'):return time.fromisoformat(value)
    if kind=='uniqueidentifier':return UUID(value)
    if re.fullmatch(r'(?:varbinary|binary)\((?:max|[1-9][0-9]*)\)',kind):
        raw=bytes.fromhex(value);size=kind.partition('(')[2][:-1]
        if size!='max' and len(raw)>int(size):raise ValueError('argument-binary-length')
        return raw
    raise ValueError('unsupported-argument-type:'+kind)

def bind(item):
    inv=item.get('procedure_contract')
    if not inv or set(inv)!={'schema','name','parameters'}:raise ValueError('inventory-procedure-contract-required')
    args=item['cases'][0]['parameters']
    if not isinstance(args,dict):raise ValueError('named-arguments-required')
    normalized={('@'+k.lstrip('@')):v for k,v in args.items()}
    if len(normalized)!=len(args):raise ValueError('duplicate-normalized-argument')
    args=normalized
    spec={p['name']:p for p in inv['parameters']}
    if len(spec)!=len(inv['parameters']) or set(args)-set(spec):raise ValueError('argument-name-mismatch')
    bound=[]
    for name,p in spec.items():
        if name not in args and not p['output'] and not p['has_default']:raise ValueError('argument-missing:'+name)
        if name in args or p['output']:
            bound.append(dict(name=name,type=p['type'],output=p['output'],value=parameter_value(args.get(name),p['type'])))
    qualified='.'.join(identifier(inv[k],'sqlserver') for k in ('schema','name'))
    return qualified,bound


def driver_type(sql_type):
    """ScriptDom pretty-print spacing is not part of a TDS type identifier."""
    value=re.sub(r'\s+','',sql_type).lower()
    if not re.fullmatch(r'[a-z][a-z0-9]*(?:\((?:max|[0-9]+(?:,[0-9]+)?)\))?',value):raise ValueError('driver-type-declaration')
    return value


def validate_target_arguments(convention,arguments):
    bindings=convention.get('target_parameters',[])
    outputs=set(convention.get('output_mapping',{}))
    extra=set(arguments)-set(bindings)
    if (len(bindings)!=len(set(bindings)) or set(bindings)-set(arguments) or extra-outputs
        or any(arguments[k] is not None for k in extra)):
        raise ValueError('target-argument-contract-required')
    return bindings
