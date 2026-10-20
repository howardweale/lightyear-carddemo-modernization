"""Bounded source-to-screen projections; no hand-maintained field map.

Only the requested paragraph is compiled. Conditions remain the Java handler's
responsibility, and every emitted expression retains its physical origin.
"""
import re
from .web_bindings import active


def projection(raw, source, paragraph, screen):
    text,lines=active(raw,source)
    begin=re.search(r'^\s*'+re.escape(paragraph)+r'\.\s*$',text,re.M)
    end=re.search(r'^\s*'+re.escape(paragraph)+r'-EXIT\.\s*$',text,re.M)
    if not begin or not end or end.start()<=begin.end():raise ValueError('projection paragraph absent')
    code=text[begin.end():end.start()];fields={f['name'] for f in screen['fields'] if f['name']}
    result=[]
    def location(m):return dict(source=source,line=lines[begin.end()+m.start()])
    for m in re.finditer(r'\bMOVE\s+((?:ACCT|CUST)-[A-Z0-9-]+)\s+TO\s+([A-Z0-9]+)O\b',code):
        if m[2] not in fields:raise ValueError('projection screen field absent')
        result.append(dict(target=m[2],operation='move',field=m[1],**location(m)))
    for m in re.finditer(r'\bSTRING\s+(.*?)\s+DELIMITED BY SIZE\s+INTO\s+([A-Z0-9]+)O\b.*?END-STRING',code,re.S):
        if m[2] not in fields:raise ValueError('projection string target absent')
        pieces=[];position=0;body=m[1]
        pattern=r"\s*(?:((?:ACCT|CUST)-[A-Z0-9-]+)\((\d+):(\d+)\)|'([^']*)')"
        for part in re.finditer(pattern,body):
            if body[position:part.start()].strip():raise ValueError('unsupported projection expression')
            pieces.append(dict(field=part[1],offset=int(part[2])-1,length=int(part[3])) if part[1] else dict(literal=part[4]))
            position=part.end()
        if body[position:].strip() or not pieces:raise ValueError('unsupported projection string')
        result.append(dict(target=m[2],operation='string',pieces=pieces,**location(m)))
    if len({r['target'] for r in result})!=len(result) or not result:raise ValueError('ambiguous/empty projection')
    return sorted(result,key=lambda r:r['line'])
