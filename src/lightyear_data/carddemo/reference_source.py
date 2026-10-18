"""Textual COPY expansion for independent procedure interpretation.

Replacement is applied to raw copy text, before tokenization, with each token
retaining the copybook's physical source line. Candidate edit/render compilers
are deliberately not imported.
"""
from pathlib import Path
import re
from .reference_control import Token,Unsupported,LEX


def logical(raw,source):
    for number,line in enumerate(raw.decode().splitlines(),1):
        if len(line)<7 or line[6] in '*/':continue
        if line[6]=='-':raise Unsupported('reference continued source: '+source+':'+str(number))
        yield line[7:72],source,number


def expand(lines,root,stack=()):
    if len(stack)>16:raise Unsupported('reference COPY nesting bound')
    rows=list(lines);out=[];i=0
    while i<len(rows):
        text,source,number=rows[i];i+=1
        if not re.match(r'\s*COPY\b',text,re.I):out.append((text,source,number));continue
        while not text.rstrip().endswith('.'):
            if i==len(rows):raise Unsupported('unterminated reference COPY')
            text+=' '+rows[i][0];i+=1
        match=re.fullmatch(r"\s*COPY\s+('?)([A-Z0-9-]+)\1\s*(.*?)\.\s*",text,re.I|re.S)
        if not match:raise Unsupported('reference COPY grammar')
        name,tail=match[2].upper(),match[3].strip()
        if name in stack:raise Unsupported('recursive reference COPY')
        found=[p for p in Path(root).rglob('*') if p.stem.upper()==name and p.suffix.lower()=='.cpy']
        if len(found)!=1:raise Unsupported('reference COPY source absent/ambiguous: '+name)
        included=list(logical(found[0].read_bytes(),str(found[0])));replacements=[]
        if tail:
            if not tail.upper().startswith('REPLACING '):raise Unsupported('reference COPY clause')
            tail=tail[len('REPLACING '):];position=0
            for pair in re.finditer(r'==(.+?)==\s+BY\s+==(.+?)==',tail,re.I|re.S):
                if tail[position:pair.start()].strip():raise Unsupported('reference replacement gap')
                replacements.append((pair[1],pair[2]));position=pair.end()
            if not replacements or tail[position:].strip():raise Unsupported('reference replacement grammar')
        for old,new in replacements:
            if not any(old in code for code,_,_ in included):raise Unsupported('unused reference replacement')
            included=[(code.replace(old,new),path,line) for code,path,line in included]
        out+=expand(included,root,stack+(name,))
    if len(out)>50000:raise Unsupported('reference source bound')
    return out


def procedure_tokens(raw,source,root):
    rows=list(logical(raw,source));start=next((i for i,(code,_,_) in enumerate(rows) if re.fullmatch(r'\s*PROCEDURE DIVISION\.\s*',code)),None)
    if start is None:raise Unsupported('reference procedure absent')
    result=[]
    for code,path,line in expand(rows[start:],root):
        position=0
        for match in LEX.finditer(code):
            if code[position:match.start()].strip():raise Unsupported('reference expanded token '+code[position:match.start()])
            position=match.end();text=match[0]
            if not text.isspace() and text!=',':result.append(Token(text if text.startswith("'") else text.upper(),path,line))
        if code[position:].strip():raise Unsupported('reference expanded trailing token')
    return result