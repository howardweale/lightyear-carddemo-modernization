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
        '165':'binary','173':'binary','189':'binary','35':'text','99':'text','59':'float','62':'float'},
    'postgresql': {'25':'text','1042':'text','1043':'text','20':'integer',
        '21':'integer','23':'integer','16':'boolean','1700':'decimal',
        '1082':'date','1083':'time','1114':'timestamp','1184':'timestamptz',
        '2950':'uuid','17':'binary','700':'float','701':'float'},
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
                if typ in ('text','ntext'):kind='text'
                if typ in ('float','real'):kind='double precision' if typ=='float' and c[3]>24 else 'real'
                if typ in ('datetime','smalldatetime'):kind='timestamp without time zone'
                if typ in ('binary','varbinary','timestamp','rowversion'):kind='bytea'
                if typ in ('time','datetime2','datetimeoffset'):
                    kind=('time' if typ=='time' else 'timestamp')+f'({c[4]}) '+('with time zone' if typ=='datetimeoffset' else 'without time zone')
                nullable=c[5]
                if kind is None:raise ValueError('unmapped-table-type:'+typ)
            else:
                kind=c[1];nullable=not c[2]
                allowed=r'(smallint|integer|bigint|boolean|date|uuid|bytea|text|real|double precision|timestamp without time zone|numeric\([0-9]+,[0-9]+\)|character(?: varying)?\([0-9]+\)|(?:time|timestamp)\([0-9]+\) (?:with|without) time zone)'
                if c[3] or not re.fullmatch(allowed,kind):raise ValueError('unmapped-table-type:'+kind)
            cols.append(dict(name=c[0],type=kind,nullable=nullable))
        out[name]=dict(columns=cols,primary_key=t['primary_key'])
    return out


# 547 is disambiguated from the native source message, never the mapping.
# P0001 user errors require exact native source/target message equality.
ERRORS = {2601:'23505',2627:'23505',515:'23502',8134:'22012',
          245:'22P02',8114:'22P02',241:'22007',242:'22008',8152:'22001',2628:'22001',8115:'22003',1205:'40P01'}


def error_equivalent(a,b,contract):
    number=a.get('number');state=b.get('sqlstate')
    if number in ERRORS:return ERRORS[number]==state
    if number==547:
        message=a.get('message','').upper()
        kind='foreign-key' if 'FOREIGN KEY' in message or 'REFERENCE CONSTRAINT' in message else 'check' if 'CHECK CONSTRAINT' in message else None
        expected={'foreign-key':'23503','check':'23514'}.get(kind)
        return expected==state if expected else None
    if isinstance(number,int) and number>=50000:
        mapping=contract.get('user_errors',{})
        expected=mapping.get(str(number))
        if state=='P0001':
            return a['message']==b.get('message') if a.get('message') else None
        return expected==state if expected else None
    return None


def datetime_value(value,source_type):
    """Map both lanes to SQL Server's declared storage resolution, not strings.

    The rounding is explicit in representation v3. datetime2 remains exact.
    A naive SQL datetime may not silently lose an offset on the target.
    """
    from datetime import datetime
    if value is None:return None
    if source_type not in ('datetime','smalldatetime'):return value
    if not isinstance(value,dict) or value.get('type')!='datetime':raise ValueError('datetime-tag-required')
    dt=datetime.fromisoformat(value['value'])
    if dt.tzinfo is not None:raise ValueError('naive-datetime-required')
    micros=((dt.toordinal()*86400+dt.hour*3600+dt.minute*60+dt.second)*1000000+dt.microsecond)
    ticks=(micros*300+500000)//1000000 if source_type=='datetime' else (micros+30000000)//60000000
    # Preserve the captured value as well as its SQL storage tick. A target
    # .001 must not become source .000 merely because both round to one tick.
    return dict(type=source_type+'-storage-ticks',value=ticks,observed=dt.isoformat())


def normalize_result_dates(left,right,source_observation):
    if len(left)!=len(right):return
    for a,b,raw in zip(left,right,source_observation['result_sets']):
        if len(a['columns'])!=len(b['columns']):continue
        for i,column in enumerate(raw['columns']):
            if str(column['type_code'])=='189':
                for result in (a,b):
                    for row in result['rows']:row[i]={'engine_generated':'rowversion'}
                continue
            kind={'61':'datetime','58':'smalldatetime'}.get(str(column['type_code']))
            if kind:
                for result in (a,b):
                    for row in result['rows']:row[i]=datetime_value(row[i],kind)


def normalized_tables(source,target):
    """Schema equality is checked separately; normalize only corresponding values."""
    from copy import deepcopy
    output=[]
    for state in (source,target):
        tables={}
        for name,t in state['tables'].items():
            rows=deepcopy(t['rows']);cols=t['columns']
            original=source['tables'].get(name)
            if original and [c[0] for c in cols]==[c[0] for c in original['columns']]:
                for row in rows:
                    for i,c in enumerate(original['columns']):
                        key=c[0] if isinstance(row,dict) else i
                        if c[1].lower() in ('rowversion','timestamp'):
                            row[key]={'engine_generated':'rowversion'}
                            continue
                        row[key]=datetime_value(value(row[key],c[1]),c[1].lower())
            tables[name]=dict(columns=[c[0] for c in cols],primary_key=t['primary_key'],rows=sorted(rows,key=canonical))
        output.append(tables)
    return output
