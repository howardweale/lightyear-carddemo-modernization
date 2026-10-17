"""Compile bounded source expressions for COACTUP's two different comparisons.

No-change comparison trims selected fields; concurrency comparison generally
does not. Keeping their source expressions separate avoids weakening conflicts.
"""
import re
from .web_bindings import active


def expression(text):
    text=text.strip()
    call=re.fullmatch(r'FUNCTION\s+(UPPER-CASE|LOWER-CASE|TRIM)\s*\((.*)\)',text,re.S)
    if call:return dict(operation=call[1],operand=expression(call[2]))
    field=re.fullmatch(r'([A-Z][A-Z0-9-]*)(?:\s*\(\s*(\d+)\s*:\s*(\d+)\s*\))?',text)
    if not field:raise ValueError('unsupported change-detection expression: '+text)
    result=dict(operation='field',name=field[1])
    if field[2]:result.update(offset=int(field[2])-1,length=int(field[3]))
    return result


def comparisons(raw,source,paragraph):
    text,lines=active(raw,source)
    start=re.search(r'^\s*'+re.escape(paragraph)+r'\.\s*$',text,re.M)
    end=re.search(r'^\s*'+re.escape(paragraph)+r'-EXIT\.\s*$',text,re.M)
    if not start or not end:raise ValueError('comparison paragraph absent')
    code=text[start.end():end.start()];result=[]
    for block in re.finditer(r'\bIF\s+(.*?)(?=\bCONTINUE\b|\bSET\b)',code,re.S):
        for part in re.finditer(r'(?:^|\bAND\b)\s*(.*?)(?=\bAND\b|$)',block[1],re.S):
            sides=re.split(r'\bEQUAL\b|=',part[1])
            if len(sides)!=2:raise ValueError('comparison equality required')
            result.append(dict(left=expression(sides[0]),right=expression(sides[1]),source=source,
                line=lines[start.end()+block.start(1)+part.start()]))
    if not result:raise ValueError('empty comparison')
    return result
