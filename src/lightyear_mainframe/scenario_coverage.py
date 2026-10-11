"""Pinned-source COBOL probes and observed adequacy; no inferred execution."""
from collections import Counter, defaultdict
import hashlib
import re

from lightyear_business_rules.coverage import decisions


PROGRAMS = {'CBACT04C', 'CBTRN02C'}
VERBS = {'IF','PERFORM','MOVE','DISPLAY','ADD','SUBTRACT','COMPUTE','CONTINUE',
         'OPEN','CLOSE','READ','WRITE','REWRITE','GOBACK','EXIT','CALL',
         'INITIALIZE','ACCEPT','STOP','STRING','UNSTRING','EVALUATE'}


def code(raw):
    if len(raw)<7 or raw[6] in '*/':
        return ''
    return raw[7:72].rstrip()


def inventory(text, program):
    if program not in PROGRAMS:
        raise ValueError('coverage-program-not-pinned')
    points = decisions(text,program,f'spec/mainframe/public-source/{program}.cbl')
    paragraphs = []
    active = False
    for n,line in enumerate(text.splitlines(),1):
        c=code(line).strip()
        if c.startswith('PROCEDURE DIVISION'):active=True
        if active and re.fullmatch(r'[0-9A-Z][0-9A-Z-]*\.',c) and c[:-1] not in VERBS and not c.startswith('END-'):
            paragraphs.append(dict(line=n,name=c[:-1]))
    for p in points:
        if p['construct'] not in ('IF','PERFORM UNTIL','INVALID KEY'):
            raise ValueError('unsupported-coverage-construct:'+p['construct'])
        p['outcomes']=['true','false']
    return dict(schema='twin-decision-inventory/1',program=program,
                source_sha256=hashlib.sha256(text.encode()).hexdigest(),
                points=points,paragraphs=paragraphs,
                denominator_semantics='source decisions and their outcomes; not rule-anchor overlap')


def instrument(text, program):
    """Add probes to a derived copy only; unsupported syntax refuses compilation.

    Pure IF/UNTIL predicates are evaluated at the same state before the original
    decision. Paired execution must establish unchanged outputs/return codes.
    KEY handlers use real COBOL dispatch, never a guessed status-code predicate.
    """
    inv=inventory(text,program); raw=text.splitlines(); lines=[code(x) for x in raw]
    before=defaultdict(list); after=defaultdict(list)
    def display(kind,n,value):return f"DISPLAY 'LYC|{kind}|{n}|{value}'"
    def emit(items):
        if any(len(x)>65 for x in items):raise ValueError('coverage-fixed-line-overflow')
        return ['       '+x for x in items]
    def predicate(start, prefix):
        expr=[lines[start].strip()[len(prefix):].strip()]; end=start+1
        while end<len(lines):
            c=lines[end].strip()
            if not c:end+=1;continue
            if c.split()[0] in VERBS or c.startswith(('END-','ELSE','INVALID','NOT INVALID')):break
            expr.append(c);end+=1
        if any('FUNCTION' in x or '.' in x or ';' in x for x in expr):
            raise ValueError('coverage-impure-or-unsupported-condition')
        return expr
    def probe(point,expr):
        n=point['line_start']
        return ['IF '+expr[0],*expr[1:],display('D',n,'true'),'ELSE',display('D',n,'false'),'END-IF']
    point_by_line={p['line_start']-1:p for p in inv['points']}
    for i,p in point_by_line.items():
        if p['construct']=='IF':before[i]+=probe(p,predicate(i,'IF'))
        if p['construct']=='PERFORM UNTIL':
            expr=predicate(i,'PERFORM UNTIL');before[i]+=probe(p,expr)
            ends=[j for j in range(i+1,len(lines)) if lines[j].strip().startswith('END-PERFORM')]
            if len(ends)!=1:raise ValueError('coverage-loop-shape')
            before[ends[0]]+=probe(p,expr)
    # Exact handler pairs: emit both the taken arm and the complement, including
    # an explicit NOT INVALID arm when the original had only INVALID KEY.
    handled=set()
    for i,p in point_by_line.items():
        if p['construct']!='INVALID KEY' or i in handled:continue
        start=max(j for j in range(i) if re.match(r'\s*(READ|REWRITE)\b',lines[j]))
        end=next(j for j in range(i+1,len(lines)) if lines[j].strip().startswith(('END-READ','END-REWRITE')))
        group=[j for j in point_by_line if start<j<end and point_by_line[j]['construct']=='INVALID KEY']
        if len(group) not in (1,2):raise ValueError('coverage-key-shape')
        for j in group:
            after[j]+=[display('D',k+1,'true' if j==k else 'false') for k in group]
        if len(group)==1:
            before[end]+=['NOT INVALID KEY',display('D',i+1,'false')]
        handled.update(group)
    for p in inv['paragraphs']:after[p['line']-1].append(display('P',p['line'],'entered'))
    # Capture each I/O operation's live file status immediately after completion.
    status_by_file={'TCATBAL-FILE':'TCATBALF-STATUS','XREF-FILE':'XREFFILE-STATUS',
                    'DISCGRP-FILE':'DISCGRP-STATUS','ACCOUNT-FILE':'ACCTFILE-STATUS',
                    'TRANSACT-FILE':'TRANFILE-STATUS','DALYTRAN-FILE':'DALYTRAN-STATUS',
                    'DALYREJS-FILE':'DALYREJS-STATUS','FD-ACCTFILE-REC':'ACCTFILE-STATUS',
                    'FD-TRANFILE-REC':'TRANFILE-STATUS','FD-REJS-RECORD':'DALYREJS-STATUS',
                    'FD-TRAN-CAT-BAL-RECORD':'TCATBALF-STATUS'}
    active=False; io=[]
    for i,c in enumerate(lines):
        c=c.strip()
        if c.startswith('PROCEDURE DIVISION'):active=True
        if not active or not re.match(r'^(OPEN|CLOSE|READ|WRITE|REWRITE)\b',c):continue
        parts=c.rstrip('.').split(); verb=parts[0]; file=parts[2] if verb=='OPEN' else parts[1]
        if file not in status_by_file:raise ValueError('coverage-unknown-file:'+file)
        end=i
        if verb in ('READ','REWRITE') and not c.endswith('.'):
            j=i+1
            while j<len(lines):
                t=lines[j].strip()
                if t.startswith(('INVALID KEY','NOT INVALID KEY','END-READ','END-REWRITE')):
                    end=next(k for k in range(j,len(lines)) if lines[k].strip().startswith(('END-READ','END-REWRITE')));break
                if t and t.split()[0] in VERBS:break
                j+=1
        after[end]+=[f"DISPLAY 'LYC|S|{i+1}|{status_by_file[file]}|'",status_by_file[file]]
        io.append(dict(line=i+1,operation=verb,file=file,status=status_by_file[file]))
    result=[]
    for i,line in enumerate(raw):
        result+=emit(before[i])
        # Preserve sentence scope when a probe follows a terminating period.
        c=lines[i]
        if after[i] and c.rstrip().endswith('.') and i not in {p['line']-1 for p in inv['paragraphs']}:
            result.append('       '+c.rstrip()[:-1]);result+=emit(after[i]);result.append('           .')
        else:
            result.append(line);result+=emit(after[i])
    inv['file_operations']=io
    return '\n'.join(result)+'\n',inv


def observe(inv, stdout):
    points={str(p['line_start']):p for p in inv['points']}
    paragraphs={str(p['line']):p for p in inv['paragraphs']}
    operations={str(p['line']):p for p in inv['file_operations']}
    outcomes=set(); entered=set(); statuses=Counter()
    for line in stdout.splitlines():
        if not line.startswith('LYC|'):continue
        bits=line.split('|')
        if len(bits)==4 and bits[1]=='D' and bits[2] in points and bits[3] in ('true','false'):
            outcomes.add((bits[2],bits[3]))
        elif len(bits)==4 and bits[1]=='P' and bits[2] in paragraphs and bits[3]=='entered':entered.add(bits[2])
        elif len(bits)==5 and bits[1]=='S' and bits[2] in operations and bits[3]==operations[bits[2]]['status'] and len(bits[4])==2:
            statuses[(bits[2],bits[3],bits[4])]+=1
        else:raise ValueError('coverage-trace-not-in-inventory')
    uncovered=[dict(id=p['id'],line=p['line_start'],outcome=o,reason='not-observed; no unreachability claim')
               for p in inv['points'] for o in p['outcomes'] if (str(p['line_start']),o) not in outcomes]
    return dict(schema='scenario-adequacy/1',instrumented=True,program=inv['program'],
                source_sha256=inv['source_sha256'],paragraphs=f'{len(entered)}/{len(paragraphs)}',
                decision_points=f'{len({n for n,o in outcomes})}/{len(points)}',
                decision_outcomes=f'{len(outcomes)}/{2*len(points)}',
                observed_outcomes=[dict(line=int(n),outcome=o) for n,o in sorted(outcomes)],
                entered_paragraph_lines=sorted(map(int,entered)),uncovered=uncovered,
                file_statuses=[dict(line=int(n),field=f,status=s,count=c) for (n,f,s),c in sorted(statuses.items())],
                legacy_mutants_killed=None,distinct_values_per_output_field={},
                threshold_status='not-approved',releasable=False)
