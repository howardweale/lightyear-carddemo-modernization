"""Inventory quoted/unquoted COPY and literal CALL dependencies in slice sources."""
from pathlib import Path
import re
from .web_bindings import active

def build(root,proof,scope):
    root=Path(root);paths=proof['files'];result=[];visited=set()
    external=set(scope['external_intrinsics'])
    def resolve(name,kind):
        suffixes=('.cbl',) if kind=='CALL' else ('.cpy','.dcl')
        candidates=[p for p in paths if Path(p).stem.upper()==name.upper() and Path(p).suffix.lower() in suffixes]
        if len(candidates)!=1:raise ValueError('source dependency absent or ambiguous: '+kind+' '+name)
        return candidates[0]
    queue=[resolve(s['program'],'CALL') for s in scope['screens']]
    queue.extend(resolve(p,'CALL') for p in scope['linked_actions'])
    pattern=re.compile(r"\b(COPY|CALL|INCLUDE)\s+(?:'([^']+)'|\"([^\"]+)\"|([A-Z][A-Z0-9-]*))")
    while queue:
        source=queue.pop(0)
        if source in visited:continue
        visited.add(source);text,lines=active((root/'upstream'/source).read_bytes(),source)
        for m in pattern.finditer(text):
            kind=m[1];name=m[2] or m[3] or m[4]
            if kind=='CALL' and not(m[2] or m[3]):raise ValueError('dynamic source CALL requires explicit translation')
            row=dict(source=source,line=lines[m.start()],operation=kind,name=name)
            if name in external:row.update(resolution='external-intrinsic',translation_verified=False)
            else:
                target=resolve(name,kind);row.update(resolution='pinned-source',target=target,sha256=paths[target]['sha256']);queue.append(target)
            result.append(row)
    return dict(files=sorted(visited),dependencies=result,
        note='Complete source dependency inventory is not proof of translated runtime behavior; vendor intrinsics remain explicit.')
