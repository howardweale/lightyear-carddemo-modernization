"""Versioned, explicit representation rules; no lossy value coercion."""
from decimal import Decimal
import re
from .native_evidence import canonical

RESULT_TYPES = {
    'sqlserver': {'167':'text','175':'text','231':'text','239':'text',
        '48':'integer','52':'integer','56':'integer','127':'integer','38':'integer',
        '104':'boolean','50':'boolean','106':'decimal','108':'decimal',
        '60':'decimal','122':'decimal','40':'date','41':'time','42':'timestamp',
        '61':'timestamp','58':'timestamp','43':'timestamptz','36':'uuid',
        '165':'binary','173':'binary'},
    'postgresql': {'25':'text','1042':'text','1043':'text','20':'integer',
        '21':'integer','23':'integer','16':'boolean','1700':'decimal',
        '1082':'date','1083':'time','1114':'timestamp','1184':'timestamptz',
        '2950':'uuid','17':'binary'},
}


def value(v, kind):
    # Decimal scale is representation; its exact numeric value remains intact.
    if isinstance(v,dict) and v.get('type')=='decimal':
        number=Decimal(v['value'])
        if not number.is_finite():raise ValueError('nonfinite-decimal')
        text=format(number,'f')
        if '.' in text:text=text.rstrip('0').rstrip('.')
        if number==0:text='0'
        return dict(v,value=text)
    return v


def result_sets(obs, engine):
    out=[]
    for rs in obs['result_sets']:
        cols=[]
        for c in rs['columns']:
            kind=RESULT_TYPES[engine].get(str(c['type_code']))
            if kind is None:raise ValueError('unmapped-result-type:'+str(c['type_code']))
            cols.append({'name':c['name'],'type':kind})
        if any(len(row)!=len(cols) for row in rs['rows']):raise ValueError('result-row-width')
        out.append({'columns':cols,'rows':[[value(v,c['type']) for v,c in zip(row,cols)] for row in rs['rows']]})
    return out


def table_contract(state):
    """Closed schema map; domains, computed columns and unknown types refuse."""
    from .policy import table_contract as legacy
    try:return legacy(state)
    except ValueError:pass
    simple={'tinyint':'smallint','smallint':'smallint','int':'integer','bigint':'bigint',
            'bit':'boolean','date':'date','uniqueidentifier':'uuid'}
    out={}
    for name,t in state['tables'].items():
        cols=[]
        for c in t['columns']:
            if state['engine']=='sqlserver':
                typ=c[1].lower();kind=simple.get(typ)
                if typ in ('decimal','numeric'):kind=f'numeric({c[3]},{c[4]})'
                if typ in ('money','smallmoney'):kind='numeric(19,4)' if typ=='money' else 'numeric(10,4)'
                if typ in ('varchar','nvarchar','char','nchar'):
                    size=c[2]//2 if typ.startswith('n') and c[2]>0 else c[2]
                    kind='text' if size==-1 else ('character varying' if 'var' in typ else 'character')+f'({size})'
                if typ in ('binary','varbinary'):kind='bytea'
                if typ in ('time','datetime2','datetimeoffset'):
                    kind=('time' if typ=='time' else 'timestamp')+f'({c[4]}) '+('with time zone' if typ=='datetimeoffset' else 'without time zone')
                nullable=c[5]
                if kind is None:raise ValueError('unmapped-table-type:'+typ)
            else:
                kind=c[1];nullable=not c[2]
                allowed=r'(smallint|integer|bigint|boolean|date|uuid|bytea|text|numeric\([0-9]+,[0-9]+\)|character(?: varying)?\([0-9]+\)|(?:time|timestamp)\([0-9]+\) (?:with|without) time zone)'
                if c[3] or not re.fullmatch(allowed,kind):raise ValueError('unmapped-table-type:'+kind)
            cols.append(dict(name=c[0],type=kind,nullable=nullable))
        out[name]=dict(columns=cols,primary_key=t['primary_key'])
    return out


# 547 is shared by CHECK and FK: only an explicit bound constraint kind may
# disambiguate it. P0001 cannot identify a particular user error number.
ERRORS = {2601:'23505',2627:'23505',515:'23502',8134:'22012',
          245:'22P02',8114:'22P02',241:'22007',242:'22008'}


def error_equivalent(a,b,contract):
    number=a.get('number');state=b.get('sqlstate')
    if number in ERRORS:return ERRORS[number]==state
    if number==547:
        expected={'foreign-key':'23503','check':'23514'}.get(contract.get('constraint_kind'))
        return expected==state if expected else None
    if isinstance(number,int) and number>=50000:
        mapping=contract.get('user_errors',{})
        expected=mapping.get(str(number))
        return expected==state if expected and expected!='P0001' else None
    return None
