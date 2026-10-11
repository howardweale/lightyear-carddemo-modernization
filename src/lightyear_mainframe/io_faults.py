"""Declared engineering fault seam in a derived, instrumented COBOL copy.

The seam supplies a status and dispatches the original INVALID KEY arm; it
never claims a host or z/OS file system produced the injected status.
"""
from .scenario_coverage import code, instrument


def declarations(text, program):
    _, inv = instrument(text, program)
    rows=[]
    for op in inv['file_operations']:
        statuses={'OPEN':[('missing','35'),('permission','37')], 'READ':[('read-error','30'),('premature-eof','10')],
                  'WRITE':[('write-error','30')], 'REWRITE':[('rewrite-error','23')], 'CLOSE':[('close-error','30')]}[op['operation']]
        for kind,status in statuses:
            # EOF is meaningful only on the stream-driving sequential read.
            if kind=='premature-eof' and op['line'] not in (326,346):continue
            special=program=='CBTRN02C' and op['operation']=='REWRITE' and op['file']=='FD-ACCTFILE-REC'
            rows.append(dict(id=f"{op['line']}-{kind}",**op,kind=kind,expected_status=status,
               expected_returncode=4 if program=='CBTRN02C' and op['line'] in (383,395) else 0 if special or kind=='premature-eof' else 12,
               expected_display='LYF-REASON=0109' if special else 'TRANSACTIONS REJECTED' if program=='CBTRN02C' and op['line'] in (383,395) else None if kind=='premature-eof' else 'TWIN-CEE3ABD=',
               representation='injected engineering status; z/OS equivalence unknown',qualification_credit=False))
    return rows


def derive(text, program, fault):
    declared={r['id']:r for r in declarations(text,program)}
    if fault not in declared:raise ValueError('undeclared-engineering-fault')
    row=declared[fault]
    # Derive from traced source while preserving original source line identities.
    traced, inv=instrument(text,program)
    original=text.splitlines(); target=original[row['line']-1].rstrip()
    lines=traced.splitlines(); marker=next(i for i,x in enumerate(lines) if f"LYC|S|{row['line']}|" in x)
    hits=[i for i,x in enumerate(lines[:marker]) if code(x).strip().rstrip('.')==code(target).strip().rstrip('.')]
    hits=hits[-1:]
    if len(hits)!=1:raise ValueError('fault-source-anchor')
    start=hits[0]; end=start
    if row['operation'] in ('READ','REWRITE'):
        # Handler may include a KEY clause and an explicit END scope.
        j=start+1
        while j<len(lines):
            c=code(lines[j]).strip()
            if c.startswith(('END-READ','END-REWRITE')):end=j;break
            if c.startswith(('INVALID KEY','NOT INVALID KEY','KEY ')) or not c:j+=1;continue
            if c.startswith(('DISPLAY','IF','MOVE','PERFORM')):
                # A handler's DISPLAY is after INVALID KEY. Otherwise operation is simple.
                if any('INVALID KEY' in code(x) for x in lines[start+1:j]):j+=1;continue
                break
            j+=1
    body=lines[start:end+1]; invalid=[]
    if end>start:
        active=False
        for line in body[1:-1]:
            c=code(line).strip()
            if c.startswith('NOT INVALID KEY'):break
            if c.startswith('INVALID KEY'):active=True;continue
            if active:invalid.append(line)
    replacement=[f"           MOVE '{row['expected_status']}' TO {row['status']}"]
    replacement+=invalid
    replacement += [f"           DISPLAY 'LYF|{fault}|{row['expected_status']}'"]
    if row['expected_display']=='LYF-REASON=0109':replacement += ["           DISPLAY 'LYF-REASON=' WS-VALIDATION-FAIL-REASON"]
    if code(body[-1]).rstrip().endswith('.'):replacement[-1]+='.'
    lines[start:end+1]=replacement
    return '\n'.join(lines)+'\n',inv,row
