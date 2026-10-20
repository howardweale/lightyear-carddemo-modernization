"""COACTUP data transfers compiled from source, not a field-name dictionary.

These transfers do not interpret surrounding control flow. The caller must honor
the source conditions; validation call inventories are not completed validators.
"""
import re
from .schema import copybook
from .screen_rules import expression
from .web_bindings import active


def paragraph(raw, source, name):
    text, lines = active(raw, source)
    start = re.search(r'^\s*'+re.escape(name)+r'\.\s*$', text, re.M)
    end = re.search(r'^\s*'+re.escape(name)+r'-EXIT\.\s*$', text, re.M)
    if not start or not end or end.start() <= start.end():
        raise ValueError('update paragraph missing: '+name)
    return text[start.end():end.start()], lines[start.end():end.start()]


def transfers(raw, source, name, destination_prefixes):
    code, lines = paragraph(raw, source, name)
    result = []
    prefix = '(?:'+'|'.join(re.escape(x) for x in destination_prefixes)+')'
    target = prefix+r'[A-Z0-9-]+'
    # The source STRING statements use implicit scope termination too.
    string_ranges = []
    for m in re.finditer(r'\bSTRING\s+(.*?)\s+DELIMITED\s+BY\s+SIZE\s+INTO\s+('+target+r')\b', code, re.S):
        pieces = []; position = 0
        for token in re.finditer(r"\s*,?\s*(?:'([^']*)'|([A-Z][A-Z0-9-]*(?:\(\d+:\d+\))?))", m[1]):
            if m[1][position:token.start()].strip(' ,\n'):raise ValueError('unparsed update STRING')
            pieces.append(dict(operation='literal',value=token[1]) if token[1] is not None else expression(token[2]))
            position=token.end()
        if m[1][position:].strip(' ,\n') or not pieces:raise ValueError('unparsed update STRING')
        result.append(dict(operation='string',pieces=pieces,target=m[2],source=source,line=lines[m.start()]))
        string_ranges.append((m.start(),m.end()))
    for m in re.finditer(r'\bMOVE\s+([A-Z][A-Z0-9-]*(?:\(\d+:\d+\))?)\s+TO\s+('+target+r')\b',code):
        result.append(dict(operation='move',expression=expression(m[1]),target=m[2],source=source,line=lines[m.start()]))
    # Every assignment to the selected buffers must have been parsed.
    expected=list(re.finditer(r'\b(?:TO|INTO)\s+('+target+r')\b',code))
    if len(expected)!=len(result):raise ValueError('unaccounted update buffer assignment')
    if not result:raise ValueError('empty update transfers')
    return sorted(result,key=lambda x:x['line'])


def buffer_layout(raw, source, name):
    text, lines=active(raw,source)
    begin=re.search(r'\b05\s+'+re.escape(name)+r'\.',text)
    if not begin:raise ValueError('update buffer absent')
    end=re.search(r'\b05\s+',text[begin.end():])
    if not end:raise ValueError('update buffer boundary absent')
    first=lines[begin.start()];last=lines[begin.end()+end.start()]
    physical=raw.decode().splitlines()[first-1:last-1]
    physical[0]=re.sub(r'\b05\b','01',physical[0],count=1)
    layout,_=copybook('\n'*(first-1)+'\n'.join(physical)+'\n',source)
    return dict(source=source,**layout.manifest())


def inputs(raw, source):
    code, lines=paragraph(raw,source,'1100-RECEIVE-MAP');result=[]
    for m in re.finditer(r'\bMOVE\s+([A-Z0-9]+)I\s+OF\s+CACTUPAI\s+TO\s+((?:[A-Z0-9-]+\s+)*?)(?=\b(?:END-IF|ELSE|IF|MOVE|COMPUTE|CONTINUE|GO)\b)',code):
        targets=re.findall(r'\bACUP-NEW-[A-Z0-9-]+\b',m[2])
        if not targets:raise ValueError('input MOVE has no new-value target')
        result.append(dict(field=m[1],targets=targets,source=source,line=lines[m.start()]))
    expected=len(re.findall(r'\bMOVE\s+[A-Z0-9]+I\s+OF\s+CACTUPAI\s+TO\b',code))
    if len(result)!=expected or not result:raise ValueError('unaccounted map input MOVE')
    numeric=[]
    for m in re.finditer(r'\bCOMPUTE\s+(ACUP-NEW-[A-Z0-9-]+)\s*=\s*FUNCTION\s+NUMVAL-C\(([^)]+)\)',code):
        numeric.append(dict(target=m[1],operand=m[2].strip(),source=source,line=lines[m.start()]))
    return dict(moves=result,numeric_conversions=numeric)


def validations(raw,source):
    code,lines=paragraph(raw,source,'1200-EDIT-MAP-INPUTS')
    labels=list(re.finditer(r"MOVE\s+'([^']*)'\s+TO\s+WS-EDIT-VARIABLE-NAME",code));result=[]
    for index,label in enumerate(labels):
        end=labels[index+1].start() if index+1<len(labels) else len(code)
        body=code[label.end():end]
        calls=[dict(paragraph=m[1],source=source,line=lines[label.end()+m.start()])
               for m in re.finditer(r'\bPERFORM\s+([A-Z0-9][A-Z0-9-]+)',body)]
        fields=list(dict.fromkeys(re.findall(r'\bACUP-NEW-[A-Z0-9-]+\b',body)))
        # Keep the source's IF predicates visible; an inventory is not execution proof.
        result.append(dict(label=label[1],fields=fields,calls=calls,source=source,line=lines[label.start()],control_flow_translated=False))
    if not result or any(not v['calls'] for v in result):raise ValueError('validation callsite missing')
    return result


def build(raw,source):
    return dict(inputs=inputs(raw,source),validations=validations(raw,source),
        fetched=transfers(raw,source,'9500-STORE-FETCHED-DATA',('CDEMO-','ACUP-OLD-')),
        writes=transfers(raw,source,'9600-WRITE-PROCESSING',('ACCT-UPDATE-','CUST-UPDATE-')),
        buffers={name:buffer_layout(raw,source,name) for name in ('ACCT-UPDATE-RECORD','CUST-UPDATE-RECORD')})
