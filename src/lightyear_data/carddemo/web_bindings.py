"""Source-derived six-screen service inputs, not proof of translated behavior.

This module inventories executable source with physical locations, emits BMS
models, and derives the linked fraud table from its DDL. It never substitutes an
unimplemented handler or a static preview for a successful screen interaction.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from .schema import pinned, copybook
from .screens import parse, PIN


def active(raw, source):
    text=''; lines=[]
    for number, line in enumerate(raw.decode('utf-8').splitlines(),1):
        if len(line)<7 or line[6] in '*/':continue
        code=line[7:72].rstrip()
        if line[6]=='-':
            # These programs use no continued quoted literal in the declarations
            # consumed here. Refuse instead of silently altering its contents.
            raise ValueError(f'unsupported fixed continuation: {source}:{number}')
        text+=code+'\n';lines.extend([number]*(len(code)+1))
    return text,lines


def literal_constants(text):
    return {m[1]:m[2].replace("''", "'") for m in re.finditer(
        r"\b(?:0[1-9]|[1-4][0-9])\s+([A-Z][A-Z0-9-]*)\s+PIC\s+X(?:\(\d+\))?\s+VALUE\s+'((?:[^']|'')*)'",text)}


def program(raw, source):
    text,lines=active(raw,source);constants=literal_constants(text)
    identity=re.search(r'\bPROGRAM-ID\.\s+([A-Z0-9-]+)\.',text)
    if not identity:raise ValueError('program identity absent')
    def origin(m):return {'source':source,'line':lines[m.start()]}
    calls=[]
    for m in re.finditer(r'\bEXEC\s+(CICS|DLI|SQL)\s+(.*?)\s+END-EXEC',text,re.S):
        body=' '.join(m[2].split())
        operands={}
        for item in re.finditer(r"\b(DATASET|FILE|PROGRAM|TRANSID|COMMAREA|MAPSET|MAP|SEGMENT|SEGMENTLENGTH|INTO|FROM|RIDFLD|KEYLENGTH)\s*\(\s*('(?:[^']|'')*'|[A-Z0-9-]+)\s*\)",body):
            name=item[2];value=name[1:-1] if name.startswith("'") else constants.get(name)
            operands.setdefault(item[1],[]).append({'expression':name,'literal':value.rstrip() if value is not None else None})
        calls.append(dict(kind=m[1],operation=body.split()[0],code=body,operands=operands,**origin(m)))
    transactions={v['literal'] for c in calls if c['kind']=='CICS' and c['operation']=='RETURN'
                  for v in c['operands'].get('TRANSID',[]) if v['literal'] is not None}
    if len(transactions)>1:raise ValueError('ambiguous transaction')
    aids=[]
    for m in re.finditer(r'\b(?:DFH(?:ENTER|PF\d+)|CCARD-AID-(?:ENTER|PFK\d+))\b',text):
        label=m[0]
        aid='ENTER' if label.endswith('ENTER') else 'PF'+str(int(re.search(r'(\d+)$',label)[1]))
        aids.append(dict(aid=aid,symbol=label,**origin(m)))
    headers=[]
    for m in re.finditer(r'\bMOVE\s+(CCDA-TITLE[0-9]+|WS-CURDATE-MM-DD-YY|WS-CURTIME-HH-MM-SS|LIT-THISPGM|WS-PGMNAME|WS-CICS-TRANID|LIT-THISTRANID|WS-TRANID)\s+TO\s+([A-Z0-9]+)O\b',text):
        headers.append(dict(expression=m[1],target=m[2],**origin(m)))
    paragraphs=[dict(name=m[1],**origin(m)) for m in re.finditer(r'^\s{0,4}([A-Z0-9][A-Z0-9-]*)\.\s*$',text,re.M)]
    literals=[dict(value=m[1].replace("''", "'"),**origin(m)) for m in re.finditer(r"'((?:[^']|'')*)'",text)]
    return dict(program=identity[1],source=source,sha256=sha256(raw).hexdigest(),
        transaction=next(iter(transactions),None),constants=constants,calls=calls,
        aids=aids,headers=headers,paragraphs=paragraphs,literals=literals,
        behavior_verified=False)


def menu(raw, source, allowed):
    text,lines=active(raw,source)
    count=re.search(r'CDEMO-MENU-OPT-COUNT\s+PIC\s+9\(0?2\)\s+VALUE\s+(\d+)',text)
    pattern=(r"10\s+FILLER\s+PIC\s+9\(0?2\)\s+VALUE\s+(\d+)\.\s*"
             r"10\s+FILLER\s+PIC\s+X\(35\)\s+VALUE\s+'([^']*)'\.\s*"
             r"10\s+FILLER\s+PIC\s+X\(0?8\)\s+VALUE\s+'([^']*)'\.\s*"
             r"10\s+FILLER\s+PIC\s+X\(0?1\)\s+VALUE\s+'([^']*)'\.")
    rows=[dict(number=int(m[1]),label=m[2],program=m[3].rstrip(),role=m[4],
               in_slice=m[3].rstrip() in allowed,source=source,line=lines[m.start()])
          for m in re.finditer(pattern,text)]
    if not count or len(rows)!=int(count[1]) or [r['number'] for r in rows]!=list(range(1,len(rows)+1)):
        raise ValueError('menu declarations are not fully accounted for')
    return rows


def fraud_schema(raw, source):
    """Translate the public CREATE TABLE's bounded SQL type grammar, all columns.

    Host-variable and timestamp conversions belong to the translated action;
    this function does not claim DB2 runtime equivalence.
    """
    text=raw.decode('utf-8')
    table=re.fullmatch(r'\s*CREATE TABLE ([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\s*\((.*)\);\s*',text,re.S)
    if not table:raise ValueError('unsupported fraud table DDL')
    fields=[];primary=None
    for physical,line in enumerate(text.splitlines(),1):
        s=line.strip()
        if s.startswith('CREATE TABLE'):continue
        s=s.removeprefix('(')
        key=re.fullmatch(r'PRIMARY KEY\(([^)]+)\)\s*\);',s)
        if key:primary=[v.strip().lower() for v in key[1].split(',')];continue
        m=re.fullmatch(r'([A-Z][A-Z0-9_]*)\s+(CHAR\(\d+\)|VARCHAR\(\d+\)|DECIMAL\(\d+(?:,\d+)?\)|TIMESTAMP|DATE|SMALLINT)\s*(NOT NULL)?\s*,?',s)
        if not m:raise ValueError(f'unsupported fraud column: {source}:{physical}')
        fields.append(dict(name=m[1].lower(),sql_type=m[2].lower(),nullable=m[3] is None,source=source,line=physical))
    names=[f['name'] for f in fields]
    if len(names)!=len(set(names)) or not primary or any(k not in names for k in primary):raise ValueError('invalid fraud keys')
    ddl='CREATE TABLE "'+table[2].lower()+'" (\n'+',\n'.join(
        '  "'+f['name']+'" '+f['sql_type']+('' if f['nullable'] else ' NOT NULL') for f in fields)
    ddl+=',\n  PRIMARY KEY ('+', '.join('"'+k+'"' for k in primary)+')\n);\n'
    return dict(table=table[2].lower(),fields=fields,primary_key=primary,source=source,sha256=sha256(raw).hexdigest(),postgres_ddl=ddl)


def build(root):
    root=Path(root);proof=pinned(root)
    scope=json.loads((root/'slice-1.json').read_bytes())
    if proof['commit']!=PIN or scope['upstream_commit']!=PIN:raise ValueError('slice source pin mismatch')
    expected={'COSGN00','COMEN01','COACTVW','COACTUP','COPAU00','COPAU01'}
    if {s['mapset'] for s in scope['screens']}!=expected or len(scope['screens'])!=6:raise ValueError('six-screen scope required')
    def locate(name,suffix):
        paths=[p for p in proof['files'] if Path(p).stem==name and Path(p).suffix.lower()==suffix]
        if len(paths)!=1:raise ValueError('source absent or ambiguous: '+name)
        p=paths[0];return p,(root/'upstream'/p).read_bytes()
    programs={};screens=[]
    for item in scope['screens']:
        p,raw=locate(item['program'],'.cbl');model=program(raw,p)
        if model['program']!=item['program'] or not model['transaction']:raise ValueError('transaction not source-resolved')
        programs[item['program']]=model
        p,raw=locate(item['mapset'],'.bms');screen=parse(raw,p)
        screens.append(dict(mapset=item['mapset'],program=item['program'],transaction=model['transaction'],model=screen))
    for name in scope['linked_actions']:
        p,raw=locate(name,'.cbl');programs[name]=program(raw,p)
    p,raw=locate('COMEN02Y','.cpy');options=menu(raw,p,programs)
    p,raw=locate('COMEN01C','.cbl');menu_code,_=active(raw,p)
    width=re.search(r'WS-OPTION-X\s+PIC\s+X\((\d+)\)\s+JUST RIGHT',menu_code)
    if not width:raise ValueError('menu input justification changed')
    outputs={m[1]:m[2] for m in re.finditer(r'WHEN\s+(\d+)\s+MOVE\s+WS-MENU-OPT-TXT\s+TO\s+([A-Z0-9]+)O',menu_code)}
    if any(str(o['number']) not in outputs for o in options):raise ValueError('menu output not mapped from source')
    common={}
    for member in ('COTTL01Y','CSMSG01Y'):
        p,raw=locate(member,'.cpy');common.update(literal_constants(active(raw,p)[0]))
    p,raw=locate('COCOM01Y','.cpy');layout,_=copybook(raw.decode('utf-8'),p)
    commarea=dict(source=p,**layout.manifest())
    from .screen_commarea import program_layout
    base_raw=raw;commareas={}
    for screen in screens:
        source_path,program_raw=locate(screen['program'],'.cbl')
        commareas[screen['program']]=program_layout(program_raw,source_path,commarea,base_raw)
    p,raw=locate('AUTHFRDS','.ddl');fraud=fraud_schema(raw,p)
    from .screen_projection import projection
    p,raw=locate('COACTVWC','.cbl')
    account_screen=next(s for s in screens if s['program']=='COACTVWC')['model']['maps'][0]
    account_projection=projection(raw,p,'1200-SETUP-SCREEN-VARS',account_screen)
    from .screen_rules import comparisons
    p,raw=locate('COACTUPC','.cbl')
    changes=dict(no_change=comparisons(raw,p,'1205-COMPARE-OLD-NEW'),
        concurrency=comparisons(raw,p,'9700-CHECK-CHANGE-IN-REC'))
    from .screen_update import build as update_bindings
    account_update=update_bindings(raw,p)
    dependencies=[]
    for name,model in programs.items():
        for call in model['calls']:
            if call['kind'] in ('DLI','SQL') or any(k in call['operands'] for k in ('DATASET','FILE')):
                dependencies.append(dict(program=name,**call))
    return dict(schema='carddemo-web-bindings/1',upstream_commit=PIN,
        scope_sha256=sha256((root/'slice-1.json').read_bytes()).hexdigest(),
        screens=screens,programs=programs,menu=options,menu_outputs=outputs,menu_option_width=int(width[1]),
        common_constants=common,commarea=commarea,program_commareas=commareas,fraud=fraud,
        account_view_projection=account_projection,account_update_comparisons=changes,account_update=account_update,
        data_uses=dependencies,outside_endpoint=scope['outside_endpoint'],
        quirks=[dict(kind='menu-outside-slice',**r) for r in options if not r['in_slice']],
        limitations=['Source inventory and generated models do not prove screen-handler equivalence.',
            'COPAUS1C PF5 calls COPAUS2C and writes AUTHFRDS as well as IMS detail.',
            'CICS intrinsics require explicit translation; no real CICS region is present.'],
        release_authorized=False,screen_equivalence_verified=False)


def export(result,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'bindings.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (out/'authfrds.sql').write_text(result['fraud']['postgres_ddl'],encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',default='spec/modernization/carddemo-screens');p.add_argument('--out',required=True)
    a=p.parse_args();export(build(a.source),a.out)
