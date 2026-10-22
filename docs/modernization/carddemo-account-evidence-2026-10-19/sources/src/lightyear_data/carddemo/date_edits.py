"""Compile the pinned date COPY's fall-through paragraphs and storage overlays.

The emitted sequence retains intermediate EXIT paragraphs: a performed range
falls through them. They are not early returns from the whole range.
"""
import re
from hashlib import sha256
from .screen_edits import Parser, declarations, bind_fields
from .screen_update import paragraph
from .schema import copybook
from .web_bindings import active


def build(program_raw, program_source, working, procedures, service):
    ws_path,ws_raw=working;code_path,code_raw=procedures;service_path,service_raw=service
    names=('EDIT-DATE-CCYYMMDD','EDIT-DATE-OF-BIRTH')
    paragraphs={}
    for name in names:
        code,lines=paragraph(code_raw,code_path,name)
        paragraphs[name]=Parser(code,lines,code_path,name).parse()
    # Prefix one synthetic root, then restore every original physical line.
    layout,_=copybook('       01 DATE-EDIT-STORAGE.\n'+ws_raw.decode(),ws_path)
    storage=layout.manifest()
    for field in storage['fields']:field['line']-=1
    fields,conditions=declarations(program_raw,program_source)
    date_fields,date_conditions=declarations(ws_raw,ws_path)
    fields.update(date_fields);conditions.update(date_conditions)
    for name,f in date_fields.items():
        if f['type']!='group':continue
        prefix='DATE-EDIT-STORAGE.'+'.'.join(f['ancestors']+[name])+'.'
        # COPY has level-10 roots, so ancestors are relative to the synthetic 01.
        children=[item for item in storage['fields'] if item['path'].startswith(prefix)]
        if not children:raise ValueError('date storage group absent: '+name)
        start=min(c['offset'] for c in children);finish=max(c['offset']+c['length'] for c in children)
        fields[name]['storage_length']=finish-start
        storage['fields'].append(dict(path=prefix[:-1],offset=start,length=finish-start,digits=0,scale=0,
            signed=False,usage='DISPLAY',sign='TRAILING',separate=False,line=f['line']))
    bound,flags=bind_fields(paragraphs,fields,conditions)
    # Numeric aliases of groups use their actual overlaid width, not a sum of aliases.
    source,lines=active(service_raw,service_path)
    feedback={m[1]:dict(severity=int(m[2][:4],16),message=int(m[2][4:8],16),source=service_path,line=lines[m.start()])
              for m in re.finditer(r"88\s+(FC-[A-Z-]+)\s+VALUE\s+X'([0-9A-F]{16})'",source)}
    if 'CALL "CEEDAYS" USING' not in source or not {'FC-INVALID-DATE','FC-BAD-DATE-VALUE','FC-INVALID-MONTH'}<=feedback.keys():
        raise ValueError('date service ABI changed')
    return dict(paragraphs=paragraphs,fields=bound,conditions=flags,storage=storage,
        service=dict(source=service_path,sha256=sha256(service_raw).hexdigest(),feedback=feedback),
        limitations=['CEEDAYS calendar adapter is a declared reference assumption pending real CICS/LE evidence.'])
