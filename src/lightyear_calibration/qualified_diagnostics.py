"""Closed structural feedback projection. Raw exceptions/rows are never returned."""
import re
from pathlib import Path
from .journey_repair import compile_diagnostics as legacy_compile, public_api_matches
from .qualified_contract import trace_diagnostics

VERSION='structural-feedback-v2'
IDENT=r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*(?:\[\])?'


def compiler(log, *, root=None, api=None):
    # Split by compiler-owned source location. Never search across locations for a
    # nearby diagnostic (the legacy parser could attribute the next error to it).
    anchor=re.compile(r'LightyearOperationsTest\.java:\[(\d+)(?:,(\d+))?\]')
    matches=list(anchor.finditer(log));output=[]
    for i,match in enumerate(matches):
        block=log[match.end():matches[i+1].start() if i+1<len(matches) else match.end()+1800]
        messages=[]
        for line in block.splitlines():
            text=line.removeprefix('[ERROR]').strip()
            if text:messages.append(text)
        loc={'category':'compile-error','file':'LightyearOperationsTest.java','line':int(match[1]),
             'column':int(match[2]) if match[2] else None}
        for text in messages:
            m=re.fullmatch(r'(?:Unhandled exception type |unreported exception )('+IDENT+r')(?:; must be caught or declared to be thrown)?',text)
            if m:
                output.append({**loc,'code':'unhandled-checked-exception','exception_type':m[1]});break
            m=re.fullmatch(r'The import ('+IDENT+r') cannot be resolved',text)
            if m:
                output.append({**loc,'code':'unresolved-import','symbol':m[1]});break
            m=re.fullmatch(r'Type mismatch: cannot convert from ('+IDENT+r') to ('+IDENT+r')',text)
            if m:
                output.append({**loc,'code':'incompatible-types','source_type':m[1],'required_type':m[2]});break
            # Existing typed parser receives one isolated compiler diagnostic only.
            parsed=legacy_compile('LightyearPartialInvoiceTest.java:['+match[1]+'] '+text)
            if parsed:
                output.append({**parsed[0],**loc});break
    unique=[]
    for item in output:
        if item.get('symbol') and root is not None and api is not None:
            evidence=public_api_matches(Path(root),item['symbol'],api)
            if evidence:item['available_public_overloads']=evidence
        if item not in unique:unique.append(item)
    return unique


def export(run, declaration, *, root=None, api=None):
    """No arbitrary gate error or native value is part of the output schema."""
    output=[]
    for lane in ('oracle','postgresql'):
        where=Path(run)/'cases/operations/1/execution'/lane
        log=where/'maven.log'
        if log.exists():output.extend(compiler(log.read_text(encoding='utf-8',errors='replace'),root=root,api=api))
        if (where/'journey.xml').exists():output.extend(trace_diagnostics(where/'journey.xml',declaration))
    unique=[]
    for value in output:
        if value not in unique:unique.append(value)
    return [{'id':'structural-'+str(i+1),**value} for i,value in enumerate(unique)]
