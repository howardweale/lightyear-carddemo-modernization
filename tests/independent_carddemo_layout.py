"""Independent, bounded public-layout readers; standard library only.

No CardDemo parser, schema, record codec or candidate/reference imports. These
readers intentionally refuse layouts outside the two work-order copybooks.
"""
from decimal import Decimal
import re


def bms_fields(raw):
    text='\n'.join(line for line in raw.decode('utf-8').splitlines()
                   if line.strip() and not line.lstrip().startswith('*'))
    text=re.sub(r'-[ \t]*\n[ \t]*','',text)
    macros=list(re.finditer(r'^[ \t]*(?:(\w+)[ \t]+)?(DFHMSD|DFHMDI|DFHMDF)[ \t]+([^\n]+)',text,re.M))
    maps=[];current=None
    token=re.compile(r"([A-Z]+)=('(?:[^']|'')*'|\([^)]*\)|[^,\s]+)")
    for macro in macros:
        name,kind,tail=macro.groups();options={};end=0
        for match in token.finditer(tail):
            if tail[end:match.start()].strip(', \t'):raise ValueError('independent-bms-operands')
            if match[1] in options:raise ValueError('independent-bms-duplicate')
            options[match[1]]=match[2];end=match.end()
        if tail[end:].strip(', \t'):raise ValueError('independent-bms-tail')
        if kind=='DFHMDI':
            rows,columns=map(int,options['SIZE'].strip('()').split(','))
            current=dict(name=name,rows=rows,columns=columns,fields=[]);maps.append(current)
        elif kind=='DFHMDF':
            if current is None:raise ValueError('independent-bms-no-map')
            position=options['POS']
            if position.startswith('('):row,column=map(int,position.strip('()').split(','))
            else:
                row,column=divmod(int(position),current['columns']);row+=1;column+=1
            length=int(options['LENGTH'])
            if row<1 or column<1 or column>current['columns'] or length<0:raise ValueError('independent-bms-range')
            current['fields'].append(dict(name=name,row=row,column=column,length=length,
                attributes=sorted(options.get('ATTRB','(NORM,PROT)').strip('()').split(',')),
                color=options.get('COLOR','NEUTRAL'),highlight=options.get('HILIGHT','OFF')))
    if not maps:raise ValueError('independent-bms-empty')
    return maps


def display_layout(raw):
    root=None;offset=0;fields=[]
    for line in raw.decode('utf-8').splitlines():
        if len(line)<7 or line[6]=='*':continue
        body=line[6:72].strip()
        if not body:continue
        group=re.fullmatch(r'01\s+([A-Z0-9-]+)\.',body)
        if group:
            if root is not None:raise ValueError('independent-layout-multiple-roots')
            root=group[1];continue
        field=re.fullmatch(r'05\s+([A-Z0-9-]+)\s+PIC\s+([SX9V0-9()]+)\.',body)
        if not field or root is None:raise ValueError('independent-layout-unsupported')
        name,picture=field.groups()
        expanded=re.sub(r'([X9])\((\d+)\)',lambda m:m[1]*int(m[2]),picture)
        if not re.fullmatch(r'X+|S?9+(?:V9+)?',expanded):raise ValueError('independent-picture')
        numeric='9' in expanded;signed=expanded.startswith('S')
        width=sum(c in 'X9' for c in expanded);scale=len(expanded.split('V')[1]) if 'V' in expanded else 0
        fields.append(dict(name=name,path=root+'.'+name,offset=offset,length=width,numeric=numeric,signed=signed,scale=scale))
        offset+=width
    if not fields:raise ValueError('independent-layout-empty')
    return fields,offset


def decode_display(raw,fields,length):
    if len(raw)!=length:raise ValueError('independent-record-length')
    values={}
    for f in fields:
        chunk=raw[f['offset']:f['offset']+f['length']]
        if f['name']=='FILLER':continue
        if not f['numeric']:value=chunk.decode('cp037')
        else:
            digits=[];negative=False
            for i,byte in enumerate(chunk):
                zone,digit=divmod(byte,16)
                if digit>9:raise ValueError('independent-display-digit')
                if f['signed'] and i==len(chunk)-1:
                    if zone not in (12,13,15):raise ValueError('independent-display-sign')
                    negative=zone==13
                elif zone!=15:raise ValueError('independent-display-zone')
                digits.append(str(digit))
            value=Decimal(('-' if negative else '')+''.join(digits)).scaleb(-f['scale'])
        values[f['path']]=value
    return values



def synthetic_records(originals,fields,length,count=950):
    """Labeled public-derived fixtures; no claim these are public source rows.

    Vary every numeric DISPLAY field, including sign zones and negative zero.
    Text/date/filler bytes come from the public templates. Primary IDs occupy a
    deterministic high range and collisions are refused by the caller.
    """
    if not originals or not fields[0]['numeric']:raise ValueError('independent-fixture-shape')
    for index in range(count):
        raw=bytearray(originals[index%len(originals)])
        for number,f in enumerate(fields):
            if not f['numeric']:continue
            width=f['length']
            value=(8*10**(width-1)+index) if number==0 else index*(number+1)%10**width
            digits=str(value).zfill(width)
            if len(digits)!=width:raise ValueError('independent-fixture-overflow')
            data=bytearray(0xf0+int(c) for c in digits)
            if f['signed']:data[-1]=(13,12,15)[index%3]*16+(data[-1]&15)
            raw[f['offset']:f['offset']+width]=data
        if len(raw)!=length:raise ValueError('independent-fixture-length')
        yield bytes(raw)
