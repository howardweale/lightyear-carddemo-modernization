"""Compile authorization render statements from pinned source, retaining locations.

The orchestration uses generated COMMAREA/data layouts. These production ASTs
are deliberately not the independent reference or a screen-equivalence claim.
"""
import re
from .web_bindings import active
from .screen_edits import Parser, declarations, bind_fields
from .schema import copybook
from .update_edits import add_group_views


def paragraph(raw,source,name):
    code,lines=active(raw,source)
    begin=re.search(r'^'+re.escape(name)+r'\.\s*$',code,re.M)
    if not begin:raise ValueError('authorization paragraph absent: '+name)
    following=re.search(r'^[A-Z][A-Z0-9-]*\.\s*$',code[begin.end():],re.M)
    end=begin.end()+following.start() if following else len(code)
    return code[begin.end():end],lines[begin.end():end]


def build(raw,source,screen,date_copy,detail_copy,summary_copy,record_copies=()):
    code,locations=active(raw,source);fields,conditions=declarations(raw,source)
    for path,data in (date_copy,detail_copy,summary_copy,*record_copies):
        f,c=declarations(data,path);fields.update(f);conditions.update(c)
    dates,_=copybook(date_copy[1].decode(),date_copy[0]);storage=dates.manifest();add_group_views(storage,fields)
    for f in storage['fields']:
        name=f['path'].split('.')[-1]
        if name in fields:fields[name]['storage_bound']=True
    literals=[];physical=date_copy[1].decode().splitlines()
    for f in storage['fields']:
        m=re.search(r"VALUE\s+'([^']*)'",physical[f['line']-1])
        if m:literals.append(dict(offset=f['offset'],value=m[1].ljust(f['length'])[:f['length']]))
    virtual={}
    for f in screen['fields']:
        if not f['name']:continue
        for suffix,length,kind in [('I',f['length'],'text'),('O',f['length'],'text'),('A',12,'text'),('C',12,'text'),('L',4,'number')]:
            virtual[f['name']+suffix]=dict(type=kind,length=length,value=None,ancestors=[],body='',source=source,line=f.get('line',1),screen_field=f['name'],screen_part=suffix,input_overlay_output=True)
    for symbol in ('DFHBMPRO','DFHBMUNP','DFHRED','DFHGREEN'):
        virtual[symbol]=dict(type='text',length=len(symbol),value="'"+symbol+"'",ancestors=[],body='',source='CICS BMS ABI',line=1)
    for m in re.finditer(r'([A-Z][A-Z0-9-]*)\s+PIC\s+([-+][zZ9,.]+)[.]',code):
        virtual[m[1]]=dict(type='edited',length=len(m[2]),picture=m[2].upper(),value=None,ancestors=[],body='',source=source,line=locations[m.start()])
    fields.update(virtual);bodies={};extras={};lookups={}
    if 'POPULATE-AUTH-DETAILS.' in code:
        body,lines=paragraph(raw,source,'POPULATE-AUTH-DETAILS')
        search=re.search(r'SEARCH ALL (WS-DECLINE-REASON-TAB)\s+AT END\s+(.*?)\s+WHEN DECL-CODE\(WS-DECL-RSN-IDX\) = ([A-Z0-9-]+)\s+(.*?)\s+END-SEARCH',body,re.S)
        if not search:raise ValueError('decline lookup source grammar changed')
        entries=[]
        for m in re.finditer(r"10\s+PIC X\(20\) VALUE '([^']*)'",code):
            text=m[1].ljust(20);entries.append(dict(key=text[:4],description=text[4:],source=source,line=locations[m.start()]))
        count=re.search(r'WS-DECLINE-REASON-TAB REDEFINES WS-DECLINE-REASON-TABLE\s+OCCURS (\d+) TIMES',code)
        if not count or len(entries)!=int(count[1]) or len({e['key'] for e in entries})!=len(entries):raise ValueError('decline lookup incomplete')
        lookups[search[1]]=entries
        missing=Parser(search[2],[lines[search.start(2)]]*len(search[2]),source,'LOOKUP').parse()
        found_code=search[4].replace('DECL-DESC(WS-DECL-RSN-IDX)','DECL-DESC')
        found=Parser(found_code,[lines[search.start(4)]]*len(found_code),source,'LOOKUP').parse()
        extras['LOOKUP-DECLINE']=[dict(op='lookup',table=search[1],description_field='DECL-DESC',value=dict(op='field',name=search[3],source=source,line=lines[search.start()]),missing=missing,found=found,source=source,line=lines[search.start()])]
        replacement='PERFORM LOOKUP-DECLINE THRU LOOKUP-DECLINE-EXIT'
        lines=lines[:search.start()]+[lines[search.start()]]*len(replacement)+lines[search.end():]
        body=body[:search.start()]+replacement+body[search.end():]
        bodies['POPULATE-AUTH-DETAILS']=(body,lines)
    else:
        body,lines=paragraph(raw,source,'POPULATE-AUTH-LIST');at=body.index('EVALUATE WS-IDX')
        bodies['ROW-PREFIX']=(body[:at],lines[:at])
        for m in re.finditer(r'WHEN ([1-5])\s+(.*?)(?=WHEN |END-EVALUATE)',body[at:],re.S):
            start=at+m.start(2);part=m[2];origins=lines[start:start+len(part)]
            move=re.search(r'MOVE PA-AUTHORIZATION-KEY\s+TO CDEMO-CPVS-AUTH-KEYS\([1-5]\)',part)
            if not move:raise ValueError('row key binding missing')
            part=part[:move.start()]+part[move.end():];origins=origins[:move.start()]+origins[move.end():]
            bodies['ROW-'+m[1]]=(part,origins)
        if len([n for n in bodies if n.startswith('ROW-')])!=6:raise ValueError('five row projections required')
        body,lines=paragraph(raw,source,'GATHER-ACCOUNT-DETAILS')
        # READ/SCHD calls remain in the transaction adapter; every MOVE/STRING/IF remains compiled.
        cuts=list(re.finditer(r'PERFORM (?:GETCARDXREF-BYACCT|GETACCTDATA-BYACCT|GETCUSTDATA-BYCUST|GET-AUTH-SUMMARY)',body))
        for m in reversed(cuts):body=body[:m.start()]+body[m.end():];lines=lines[:m.start()]+lines[m.end():]
        bodies['GATHER-ACCOUNT-DETAILS']=(body,lines)
    paragraphs={**extras}
    for name,(body,lines) in bodies.items():paragraphs[name]=Parser(body,lines,source,name,set(bodies)|set(extras)).parse()
    flags=('ERR-FLG-OFF',) if extras else ('ERR-FLG-OFF','FOUND-PAUT-SMRY-SEG')
    bound,flags=bind_fields(paragraphs,fields,conditions,initial_flags=flags)
    for name,d in virtual.items():
        if name in bound:
            for key in ('screen_field','screen_part','picture','input_overlay_output'):
                if key in d:bound[name][key]=d[key]
    return dict(paragraphs=paragraphs,fields=bound,conditions=flags,storage=storage,storage_literals=literals,lookups=lookups,
        limitations=['Production rendering translation only; independent screen/database proof is required.'])
