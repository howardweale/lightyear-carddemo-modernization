"""Compile the complete account edit decision sequence and its shared storage.

Separate from the independent reference: this is the production translation.
Every PERFORM target must be compiled; no call inventory counts as execution.
"""
import copy
import re
from .screen_edits import Parser, declarations, bind_fields
from .screen_update import paragraph, buffer_layout


def add_group_views(layout, fields):
    for name,decl in fields.items():
        if decl['type']!='group':continue
        paths={f['path'].rsplit('.',1)[0] for f in layout['fields'] if '.' in f['path']}
        candidates={p for p in paths if p.split('.')[-1]==name}
        # Include ancestors of nested groups too.
        for f in layout['fields']:
            parts=f['path'].split('.')
            candidates.update('.'.join(parts[:i+1]) for i,p in enumerate(parts[:-1]) if p==name)
        if len(candidates)>1:raise ValueError('ambiguous shared edit group: '+name)
        if not candidates:continue
        path=candidates.pop();children=[f for f in layout['fields'] if f['path'].startswith(path+'.')]
        start=min(f['offset'] for f in children);end=max(f['offset']+f['length'] for f in children)
        decl['storage_length']=end-start
        if any(f['path']==path for f in layout['fields']):continue
        layout['fields'].append(dict(path=path,offset=start,length=end-start,digits=0,scale=0,
            signed=False,usage='DISPLAY',sign='TRAILING',separate=False,line=decl['line']))


def build(raw,source,generic,dates,commarea,lookup,date_work,common,card_work,screen,attribute_copy):
    paragraphs={**generic['paragraphs'],**dates['paragraphs']}
    extra=('1100-RECEIVE-MAP','1200-EDIT-MAP-INPUTS','1205-COMPARE-OLD-NEW','1210-EDIT-ACCOUNT')
    allowed=set(paragraphs)|set(extra)
    for name in extra:
        code,lines=paragraph(raw,source,name)
        if name=='1100-RECEIVE-MAP':
            receive=re.match(r'\s*EXEC CICS RECEIVE MAP\(LIT-THISMAP\).*?END-EXEC',code,re.S)
            if not receive:raise ValueError('account input RECEIVE ABI absent')
            code=code[receive.end():];lines=lines[receive.end():]
        paragraphs[name]=Parser(code,lines,source,name,allowed).parse()
    fields,conditions=declarations(raw,source)
    for path,data in (lookup,date_work,common,card_work):
        f,c=declarations(data,path);fields.update(f);conditions.update(c)
    # These independent roots contain every overlaid edit operand. Other scalar
    # working fields remain scalar; no manually assigned source offsets exist.
    stores=[copy.deepcopy(generic['storage']),copy.deepcopy(dates['storage']),
            copy.deepcopy(commarea),buffer_layout(raw,source,'WS-NON-KEY-FLAGS')]
    storage=dict(record_length=0,fields=[]);area_offset=None
    for index,layout in enumerate(stores):
        add_group_views(layout,fields)
        offset=storage['record_length']
        if index==2:area_offset=offset
        for f in layout['fields']:
            f['offset']+=offset;storage['fields'].append(f)
        storage['record_length']+=layout['record_length']
    # The CC input identifier is an overlaid byte view declared in CVCRD01Y.
    # Include that original root so CC-ACCT-ID and CC-ACCT-ID-N cannot diverge.
    from .schema import copybook
    cc,_=copybook(card_work[1].decode(),card_work[0]);cc=cc.manifest();offset=storage['record_length']
    add_group_views(cc,fields)
    for f in cc['fields']:f['offset']+=offset;storage['fields'].append(f)
    storage['record_length']+=cc['record_length']
    from .render_edits import build as compile_render
    rendering,render_fields=compile_render(raw,source,screen,attribute_copy,paragraphs)
    paragraphs.update(rendering);fields.update(render_fields)
    for item in storage['fields']:
        name=item['path'].split('.')[-1]
        if name in fields:fields[name]['storage_bound']=True
    # The Java READ-miss path sets this source 88 outside compiled edit paragraphs.
    # Retain its declaration and parent storage even though those paragraphs do
    # not reference the NOT-OK sibling (COACTUPC 189, 3768 and 3787).
    bound,flags=bind_fields(paragraphs,fields,conditions,
        initial_flags=('INPUT-OK','WS-RETURN-MSG-OFF','FLG-CUSTFILTER-NOT-OK'))
    for name,definition in render_fields.items():
        if name in bound:
            for key in ('screen_field','screen_part','picture'):
                if key in definition:bound[name][key]=definition[key]

    # Bind the original layout/flags first, then retire these statement bodies
    # from the production validation model. generic_edits remains a CI oracle.
    native_paragraphs = {name: 'AccountInputRules' for name in
                         ('1215-EDIT-MANDATORY', '1220-EDIT-YESNO')}
    for name in native_paragraphs:
        del paragraphs[name]
    return dict(paragraphs=paragraphs,native_paragraphs=native_paragraphs,
        fields=bound,conditions=flags,storage=storage,
        service=dates['service'],area_offset=area_offset,area_length=commarea['record_length'],
        limitations=dates['limitations']+['Invalid unsigned DISPLAY bytes are retained for source NUMERIC checks and compared in EBCDIC byte order; this deterministic reference assumption needs a native baseline.', 'Source validation control flow; screen/database/browser equivalence is a separate gate.'])
