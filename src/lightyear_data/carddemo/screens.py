"""Pinned BMS layout model and bounded field rendering, not a CICS emulator."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

PIN='59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e'


def split_options(value):
    parts=[];start=0;depth=0;quoted=False;i=0
    while i<len(value):
        c=value[i]
        if c=="'":
            if quoted and i+1<len(value) and value[i+1]=="'":i+=2;continue
            quoted=not quoted
        if not quoted:
            if c=='(':depth+=1
            if c==')':depth-=1
            if c==',' and depth==0:parts.append(value[start:i]);start=i+1
        i+=1
    if quoted or depth:raise ValueError('bms-unclosed-operand')
    parts.append(value[start:]);result={}
    for part in parts:
        key,sep,val=part.partition('=')
        key=key.strip()
        if not sep or not key or key in result:raise ValueError('bms-invalid-operand')
        result[key]=val.strip()
    return result


def statements(text):
    body='';first=0
    for number,line in enumerate(text.splitlines(),1):
        if not line.strip() or line.startswith('*'):continue
        if not body:first=number
        continued=line.rstrip().endswith('-')
        fragment=line.rstrip()[:-1].rstrip() if continued else line.rstrip()
        body+=fragment.lstrip() if body else fragment
        if continued:continue
        if body.strip()!='END':yield first,body
        body=''
    if body:raise ValueError('bms-incomplete-continuation')


def parse(raw,path):
    maps=[];current=None;mapset=None
    for line,text in statements(raw.decode('utf-8')):
        match=re.fullmatch(r'\s*(?:(\w+)\s+)?(DFHMSD|DFHMDI|DFHMDF)\s+(.+)',text)
        if not match:raise ValueError(f'bms-unsupported-statement:{path}:{line}')
        label,kind,tail=match.groups();options=split_options(tail)
        if kind=='DFHMSD':
            if options.get('TYPE')=='FINAL':continue
            if not label:raise ValueError('bms-mapset-name')
            mapset=label
        elif kind=='DFHMDI':
            if not label or not mapset:raise ValueError('bms-map-name')
            if set(options)-{'COLUMN','LINE','SIZE','CTRL','TIOAPFX','MAPATTS','DSATTS'}:raise ValueError('bms-unsupported-map-operand')
            size=re.fullmatch(r'\((\d+),(\d+)\)',options.get('SIZE',''))
            if not size:raise ValueError('bms-map-size')
            current=dict(name=label,mapset=mapset,rows=int(size[1]),columns=int(size[2]),
                origin_row=int(options.get('LINE',1)),origin_column=int(options.get('COLUMN',1)),source_line=line,fields=[])
            maps.append(current)
        else:
            if current is None:raise ValueError('bms-field-without-map')
            if set(options)-{'ATTRB','COLOR','HILIGHT','LENGTH','POS','INITIAL','PICIN','PICOUT'}:raise ValueError('bms-unsupported-field-operand')
            if 'PICIN' in options or 'PICOUT' in options:raise ValueError('bms-picture-formatting-not-implemented')
            pos=options.get('POS','');pair=re.fullmatch(r'\((\d+),(\d+)\)',pos)
            offset=(int(pair[1])-1)*current['columns']+int(pair[2])-1 if pair else int(pos)
            length=int(options['LENGTH'])
            if offset<0 or offset+length>=current['rows']*current['columns'] or length<0 or length>256:raise ValueError('bms-field-outside-map')
            attributes=options.get('ATTRB','(NORM,PROT)').strip('()').split(',')
            if set(attributes)-{'ASKIP','PROT','UNPROT','FSET','IC','NUM','NORM','BRT','DRK'}:raise ValueError('bms-unsupported-attribute')
            initial=options.get('INITIAL',"''")
            if not (initial.startswith("'") and initial.endswith("'")):raise ValueError('bms-initial-literal')
            initial=initial[1:-1].replace("''", "'")
            if len(initial.encode('cp037'))>length:raise ValueError('bms-initial-too-long')
            if label and (not length or any(f['name']==label for f in current['fields'])):raise ValueError('bms-field-name')
            current['fields'].append(dict(name=label,source_line=line,attribute_offset=offset,data_offset=offset+1,
                length=length,attributes=attributes,protected='UNPROT' not in attributes,
                hidden='DRK' in attributes,color=options.get('COLOR','NEUTRAL'),highlight=options.get('HILIGHT','OFF'),initial=initial))
    if not maps:raise ValueError('bms-empty-map')
    return dict(schema='carddemo-bms-model/1',source=path,source_sha256=sha256(raw).hexdigest(),maps=maps,
        semantics='POS identifies the attribute byte; data starts in the next cell. LENGTH excludes the attribute byte.',
        reference='https://www.ibm.com/docs/en/cics-ts/6.x?topic=macros-dfhmdf')


def receive(model, values):
    """Validate explicit input only; never infer NUM business validation or uppercase."""
    fields={f['name']:f for f in model['fields'] if f['name']}
    result={}
    for name,value in values.items():
        if name not in fields or fields[name]['protected']:raise ValueError('screen-protected-or-unknown-field')
        if not isinstance(value,str):raise ValueError('screen-input-type')
        raw=value.encode('cp037')
        if len(raw)>fields[name]['length']:raise ValueError('screen-input-too-long')
        result[name]=raw.ljust(fields[name]['length'],b'\x40')
    return result


COLORS={'BLUE':'#6daaff','RED':'#ff7373','GREEN':'#74e59a','YELLOW':'#ffe382','TURQUOISE':'#69dbdf','PINK':'#ed9fe6','NEUTRAL':'#eeeeee'}


def render(model, values=None):
    values=values or {};fields=[]
    for f in model['fields']:
        value=str(values.get(f['name'],f['initial']))
        if len(value.encode('cp037'))>f['length']:raise ValueError('screen-output-too-long')
        color=f['color']
        if color=='DEFAULT':color=('NEUTRAL' if 'BRT' in f['attributes'] else 'BLUE') if f['protected'] else ('RED' if 'BRT' in f['attributes'] else 'GREEN')
        if color not in COLORS or f['highlight'] not in ('OFF','UNDERLINE','REVERSE','BLINK'):raise ValueError('screen-unsupported-style')
        offset=f['data_offset'];row,col=divmod(offset,model['columns'])
        style=f"left:{col}ch;top:{row*1.25}em;width:{f['length']}ch;color:{COLORS[color]};"
        if f['highlight']=='UNDERLINE':style+='text-decoration:underline;'
        if f['highlight']=='REVERSE':style+='background:#eee;color:#111;'
        if 'BRT' in f['attributes']:style+='font-weight:bold;'
        if f['highlight']=='BLINK':style+='text-decoration:underline;' # no flashing; disclosed below
        if not f['protected'] and f['name']:
            fields.append('<input aria-label="'+escape(f['name'])+'" name="'+escape(f['name'])+'" maxlength="'+str(f['length'])+'" style="'+style+'" type="'+('password' if f['hidden'] else 'text')+'" value="'+escape(value,quote=True)+'"'+(' autofocus' if 'IC' in f['attributes'] else '')+'>')
        elif not f['hidden']:
            # Split wrapped protected fields at the map edge, retaining cell coordinates.
            text=value.ljust(f['length']);position=offset
            while text:
                r,c=divmod(position,model['columns']);part=text[:model['columns']-c];text=text[len(part):]
                fields.append('<span style="'+style+f'left:{c}ch;top:{r*1.25}em;width:{len(part)}ch;">'+escape(part)+'</span>');position+=len(part)
    return '<!doctype html><meta charset="utf-8"><title>'+escape(model['name'])+'</title><style>body{background:#111;color:#eee;font:16px monospace}form{position:relative;margin:2em auto}span,input{position:absolute;white-space:pre;font:inherit;line-height:1.25em;box-sizing:content-box}input{background:#111;border:0;padding:0;outline:1px solid #444}footer{font:14px sans-serif;text-align:center}</style><form autocomplete="off" onsubmit="return false" style="width:'+str(model['columns'])+'ch;height:'+str(model['rows']*1.25)+'em">'+''.join(fields)+'</form><footer>Source-bound BMS layout preview. No server or authentication. BLINK rendered as underline; no CICS datastream or session equivalence claimed.</footer>'


def build(root,out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=True)
    provenance=json.loads((root/'provenance.json').read_bytes())
    if provenance['commit']!=PIN:raise ValueError('bms-upstream-pin')
    result=[]
    for path,binding in provenance['files'].items():
        raw=(root/'upstream'/path).read_bytes()
        if len(raw)!=binding['bytes'] or sha256(raw).hexdigest()!=binding['sha256']:raise ValueError('bms-source-hash')
        if not path.endswith('.bms'):continue
        model=parse(raw,path);name=Path(path).stem
        (out/(name+'.json')).write_text(json.dumps(model,indent=2)+'\n',encoding='utf-8')
        for screen in model['maps']:(out/(screen['name']+'.html')).write_text(render(screen),encoding='utf-8')
        result.append(dict(path=path,source_sha256=model['source_sha256'],maps=[s['name'] for s in model['maps']],fields=sum(len(s['fields']) for s in model['maps'])))
    (out/'index.json').write_text(json.dumps(dict(schema='carddemo-screen-model-index/1',upstream_commit=PIN,sources=result,release_authorized=False),indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();build('spec/modernization/carddemo-screens',a.out)
