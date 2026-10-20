"""Compile transmitted COMMAREA layouts from each program's actual declarations."""
import copy
import re
from hashlib import sha256
from .schema import copybook
from .web_bindings import active


def program_layout(raw, source, base, base_raw):
    text,locations=active(raw,source)
    result=copy.deepcopy(base);result['program_source']=source;result['program_sha256']=sha256(raw).hexdigest()
    declared=re.search(r'\b01\s+WS-THIS-PROGCOMMAREA\.',text)
    extended=re.search(r'\bCOPY\s+COCOM01Y\.\s+(05\s+CDEMO-CPV[SD]-INFO\.)',text)
    if declared:
        end=re.search(r'\b01\s+',text[declared.end():])
        if not end:raise ValueError('program commarea boundary absent')
        body=text[declared.start():declared.end()+end.start()]
        # Keep physical origins after reconstructing only the declaration area.
        start_line=locations[declared.start()]
        end_line=locations[declared.end()+end.start()]
        generated='\n'*(start_line-1)+'\n'.join(raw.decode('utf-8').splitlines()[start_line-1:end_line-1])+'\n'
        extension,_=copybook(generated,source);extension=extension.manifest()
        offset=result['record_length']
        for f in extension['fields']:f['offset']+=offset;f['source']=source
        result['fields']+=extension['fields']
        for o in extension.get('overlays',[]):o['offset']+=offset
        result.setdefault('overlays',[]).extend(extension.get('overlays',[]))
        size=re.search(r'\b01\s+WS-COMMAREA\s+PIC\s+X\((\d+)\)',text)
        if not size or offset+extension['record_length']>int(size[1]):raise ValueError('transmitted commarea too short')
        result['record_length']=int(size[1]);result['used_length']=offset+extension['record_length']
    elif extended:
        tail=text[extended.start(1):];end=re.search(r'\bCOPY\s+',tail)
        if not end:raise ValueError('inline commarea boundary absent')
        # The source COPY adds fields under the base level-01, without a new root.
        start_line=locations[extended.start(1)];end_line=locations[extended.start(1)+end.start()]
        body='\n'.join(raw.decode('utf-8').splitlines()[start_line-1:end_line-1])
        combined=base_raw.decode('utf-8')+'\n'+body+'\n'
        layout,_=copybook(combined,source);result.update(layout.manifest())
        original_line=locations[extended.start(1)]
        base_lines=len(base_raw.decode('utf-8').splitlines())+1
        for f in result['fields']:
            if f['line']>base_lines:f['line']=f['line']-base_lines+original_line-1;f['source']=source
            else:f['source']=base['source']
        result['used_length']=result['record_length']
    else:result['used_length']=result['record_length']
    for f in result['fields']:f.setdefault('source',base['source'])
    result['schema_version']='1.1'
    return result
