"""Opt-in cp037 physical key projection; logical records remain unchanged ASCII.

Every indexed record gets a private leading physical key (and optional alternate
key). Original FD data follows unchanged. Program/bridge use the same projection.
"""
import re
from .scenario_coverage import code

SPECS={
 'CBACT04C':{'TCATBAL-FILE':('FD-TRAN-CAT-BAL-RECORD',17,None),'XREF-FILE':('FD-XREFFILE-REC',16,(26,11)),'ACCOUNT-FILE':('FD-ACCTFILE-REC',11,None),'DISCGRP-FILE':('FD-DISCGRP-REC',16,None)},
 'CBTRN02C':{'TRANSACT-FILE':('FD-TRANFILE-REC',16,None),'XREF-FILE':('FD-XREFFILE-REC',16,None),'ACCOUNT-FILE':('FD-ACCTFILE-REC',11,None),'TCATBAL-FILE':('FD-TRAN-CAT-BAL-RECORD',17,None)}}


def helper():
    # GnuCOBOL alphanumeric ordinal is host byte+1. Only ASCII public inputs allowed.
    rows=['identification division.','program-id. LYKEY.','data division.','working-storage section.','01 i binary-long.','linkage section.','01 input-key pic x(32).','01 output-key pic x(32).','01 key-length binary-long.','procedure division using input-key output-key key-length.','perform varying i from 1 by 1 until i > key-length','evaluate function ord(input-key(i:1))']
    for n in range(128):rows.append(f'when {n+1} move x"{chr(n).encode("cp037").hex()}" to output-key(i:1)')
    rows += ['when other stop run returning 67','end-evaluate','end-perform','goback.']
    return '\n'.join(rows)+'\n'


def derive(text,program):
    specs=SPECS[program];lines=[code(x) for x in text.splitlines()];result=[];current=None;fd=None;in_fd=False;body=False;after={}
    # The original source is fixed format; derive a free-format translation with
    # full original sentences preserved and only storage/operation seams changed.
    for i,c in enumerate(lines):
        t=c.strip()
        m=re.match(r'SELECT ([A-Z0-9-]+)',t)
        if m:current=m[1]
        if current in specs and t.startswith('RECORD KEY'):c='RECORD KEY IS LY-'+current+'-KEY'
        if current in specs and t.startswith('ALTERNATE RECORD KEY'):c='ALTERNATE RECORD KEY IS LY-'+current+'-ALT'
        m=re.match(r'FD\s+([A-Z0-9-]+)\.',t)
        if m:fd=m[1];in_fd=fd in specs
        if t.startswith('WORKING-STORAGE'):in_fd=False
        if in_fd:
            m=re.match(r'(\d\d)\s+(.*)',t)
            if m:
                level=int(m[1]);rest=m[2]
                if level==1:
                    _,key,alt=specs[fd]
                    result += [f'01 LY-{fd}-RECORD.',f' 05 LY-{fd}-KEY PIC X({key}).']
                    if alt:result += [f' 05 LY-{fd}-ALT PIC X({alt[1]}).']
                c=f'{5 if level==1 else level+5:02d} {rest}'
        if t.startswith('PROCEDURE DIVISION'):body=True
        if body:
            parts=t.rstrip('.').split();verb=parts[0] if parts else ''
            file=parts[1] if len(parts)>1 else ''
            if verb in ('WRITE','REWRITE'):
                file=next((f for f,s in specs.items() if s[0]==file),file)
            if file in specs and verb in ('READ','WRITE','REWRITE'):
                logical,key,alt=specs[file];physical='LY-'+file+'-RECORD';keyname='LY-'+file+'-KEY'
                end=i
                for j in range(i+1,len(lines)):
                    if lines[j].strip().startswith('END-'+verb):end=j;break
                    if lines[j].strip().startswith(('IF ','MOVE ','PERFORM ','DISPLAY ')) and not any('INVALID KEY' in x for x in lines[i+1:j]):break
                if verb in ('WRITE','REWRITE'):
                    if ' FROM ' in ' '+t+' ':
                        src=t.rstrip('.').split(' FROM ')[1].strip()
                        result.append(f'MOVE {src} TO {logical}')
                    result.append(f'CALL "LYKEY" USING {logical}(1:{key}) {keyname} BY CONTENT {key}')
                    if alt:result.append(f'CALL "LYKEY" USING {logical}({alt[0]}:{alt[1]}) LY-{file}-ALT BY CONTENT {alt[1]}')
                    c=f'{verb} {physical}'+('.' if t.endswith('.') else '')
                else:
                    into=t.split(' INTO ')[1].rstrip('.') if ' INTO ' in t else None
                    # For random lookup project the current logical key, including alternate key.
                    selectedalt=any('KEY IS FD-XREF-ACCT-ID' in x for x in lines[i+1:end+1])
                    offset,length=alt if selectedalt else (1,key)
                    chosen='LY-'+file+('-ALT' if selectedalt else '-KEY')
                    result.append(f'CALL "LYKEY" USING {logical}({offset}:{length}) {chosen} BY CONTENT {length}')
                    c=f'READ {file}'
                    if selectedalt:c+=' KEY IS '+chosen
                    # Move logical data before original INVALID/NOT INVALID handler.
                    if into:
                        # INTO must copy logical only; execute after END-READ before predicates.
                        after.setdefault(end,[]).append(f'MOVE {logical} TO {into}')
                        for k in range(i+1,end):
                            if lines[k].strip().startswith('NOT INVALID KEY'):after.setdefault(k,[]).append(f'MOVE {logical} TO {into}')
                    if t.endswith('.'):c+='.'
            if t.startswith('KEY IS FD-XREF-ACCT-ID'):c=''
        # Put post-read moves before a sentence period, preserving scope.
        if i in after and c.rstrip().endswith('.'):
            result.append(c.rstrip()[:-1]);result.extend(after[i]);result.append('.')
        else:
            result.append(c)
            result.extend(after.get(i,[]))
    from .zos_bindings import ROOT
    expanded=[]
    for line in result:
        m=re.fullmatch(r'COPY ([A-Z0-9]+)\.',line.strip())
        if m:expanded.extend(code(x) for x in (ROOT/'spec/mainframe/copybooks'/f'{m[1]}.cpy').read_text().splitlines())
        else:expanded.append(line)
    return '\n'.join(expanded)+'\n'


def adapter(source,key,alternate=False):
    # Bridge keeps input/output flat images logical while the physical index has
    # a separate projected key. Alternate field remains at its original offset.
    source=source.replace('01 index-record.','01 physical-record.\n05 primary-key pic x('+str(key)+').'+ ('\n05 alternate-key pic x(11).' if alternate else '')+'\n05 index-record.')
    # Rewrite original logical child levels and avoid duplicate primary-key name.
    at=source.index('05 index-record.');prefix=source[:at];tail=source[at:]
    tail=tail.replace('05 primary-key','10 logical-primary').replace('05 filler','10 filler').replace('05 alt-key','10 alt-key')
    source=prefix+tail
    if alternate:source=source.replace('alternate record key is alt-key','alternate record key is alternate-key')
    source=source.replace('       write index-record','       call "LYKEY" using index-record(1:'+str(key)+') primary-key by content '+str(key)+ ('\n       call "LYKEY" using index-record(26:11) alternate-key by content 11' if alternate else '')+'\n       write physical-record')
    return source
