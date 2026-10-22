"""Derive COPAUS2C SQL columns and source operands; no hand-written mappings."""
import re
from .web_bindings import active


def split_sql(text):
    result=[];start=0;depth=0;quoted=False;i=0
    while i<len(text):
        c=text[i]
        if c=="'":
            if quoted and i+1<len(text) and text[i+1]=="'":i+=2;continue
            quoted=not quoted
        elif not quoted:
            if c=='(':depth+=1
            elif c==')':depth-=1
            elif c==',' and depth==0:result.append(text[start:i].strip());start=i+1
        i+=1
    if depth or quoted:raise ValueError('unbalanced SQL expression')
    result.append(text[start:].strip());return result


def build(raw,source,ddl):
    code,lines=active(raw,source)
    insert=re.search(r'INSERT INTO CARDDEMO.AUTHFRDS\s*\((.*?)\)\s*VALUES\s*\((.*?)\)\s*END-EXEC',code,re.S)
    # Bound the expression at its first END-EXEC, not a later UPDATE.
    if not insert:raise ValueError('fraud insert absent')
    value_text=insert[2].split('END-EXEC',1)[0]
    if 'EXEC SQL' in value_text:raise ValueError('fraud insert boundary ambiguous')
    columns=[v.lower() for v in split_sql(insert[1])];values=split_sql(value_text)
    if columns!=[f['name'] for f in ddl['fields']] or len(columns)!=len(values):raise ValueError('fraud insert/DDL column mismatch')
    moves={}
    for m in re.finditer(r'\bMOVE\s+((?:PA|WS)-[A-Z0-9-]+)\s+TO\s+([A-Z][A-Z0-9-]*)',code):
        moves[m[2]]=dict(field=m[1],source=source,line=lines[m.start()])
    date=re.search(r'MOVE\s+(PA-[A-Z0-9-]+)\(1:2\)\s+TO\s+WS-AUTH-YY',code)
    clock=re.search(r'COMPUTE WS-AUTH-TIME = (\d+) - (PA-[A-Z0-9-]+)',code)
    if not date or not clock:raise ValueError('source authorization timestamp changed')
    bindings=[]
    for column,value in zip(columns,values):
        origin=dict(source=source,line=lines[insert.start()])
        if value=='CURRENT DATE':expression=dict(kind='current-date',**origin)
        elif value.startswith('TIMESTAMP_FORMAT'):
            match=re.fullmatch(r"TIMESTAMP_FORMAT\s*\(\s*:AUTH-TS,\s*'([^']*)'\s*\)",value)
            if not match or match[1]!='YY-MM-DD HH24.MI.SSNNNNNN':raise ValueError('unsupported timestamp grammar')
            expression=dict(kind='authorization-time',date_field=date[1],time_field=clock[2],complement=int(clock[1]),format=match[1],**origin)
        else:
            match=re.fullmatch(r':([A-Z][A-Z0-9-]*)',value)
            if not match:raise ValueError('unmapped SQL value')
            host=match[1]
            # VARCHAR's length/text group is declared in AUTHFRDS; SQL consumes its text payload.
            binding=moves.get(host) or moves.get(host+'-TEXT')
            if not binding:raise ValueError('unmapped SQL host: '+host)
            expression=dict(kind='field',**binding)
        bindings.append(dict(column=column,expression=expression))
    update=re.search(r'UPDATE CARDDEMO.AUTHFRDS\s+SET\s+(.*?)\s+WHERE',code,re.S)
    if not update:raise ValueError('fraud update absent')
    update_columns=[item.split('=')[0].strip().lower() for item in split_sql(update[1])]
    if any(c not in columns for c in update_columns):raise ValueError('unmapped fraud update')
    return dict(bindings=bindings,update_columns=update_columns,source=source,
        limitations=['Two-digit authorization years use the public-reference 2000–2099 window; native DB2 year-window evidence is absent.'])
