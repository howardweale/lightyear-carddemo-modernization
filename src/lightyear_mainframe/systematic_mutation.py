"""Systematic source-site mutation, immutable operands and honest kill taxonomy."""
import re
from hashlib import sha256
from .scenario_coverage import code, VERBS

OPERATORS=('relational','arithmetic','constant','rounded','receiving-scale','receiving-size','delete-MOVE','delete-ADD','delete-COMPUTE','delete-WRITE','delete-REWRITE','negate-condition','skip-PERFORM')
TOKEN=re.compile(r"'[^']*'|\"[^\"]*\"|[0-9]+-[A-Z][A-Z0-9-]*|[A-Z][A-Z0-9-]*|[0-9]+(?:\.[0-9]+)?|>=|<=|<>|[=><+*/-]|[^\s]",re.I)


def _source_sites(text,program):
    raw=text.splitlines(); lines=[code(x) for x in raw]; rows=[]; active=False; statement=None
    def add(i,operator,new,end=None):
        end=i if end is None else end
        old='\n'.join(raw[i:end+1]); replacement='\n'.join('       '+s for s in new.split('\n'))
        if old==replacement:return
        rows.append(dict(id=f'{program}-{operator}-{i+1}-{len(rows)+1}',operator=operator,line=i+1,end_line=end+1,
            original=old,replacement=replacement,source_sha256=sha256(text.encode()).hexdigest()))
    for i,c in enumerate(lines):
        t=c.strip()
        if t.startswith('PROCEDURE DIVISION'):active=True;continue
        if not active:
            m=re.search(r'PIC\s+(S?)(9(?:\(\d+\)|9*))(?:V(9(?:\(\d+\)|9*)))?',t)
            if m:
                def digits(part):return int(part[2:-1]) if '(' in part else len(part)
                n=digits(m[2]);scale=digits(m[3]) if m[3] else 0
                smaller='9('+str(n-1 if n>1 else 2)+')'
                add(i,'receiving-size',t[:m.start(2)]+smaller+t[m.end(2):])
                fraction='V9('+str(scale+1)+')'
                suffix=m.end(3) if m[3] else m.end(2)
                add(i,'receiving-scale',t[:m.end(2)]+fraction+t[suffix:])
            continue
        if not t or t.endswith('.') and len(t.split())==1:continue
        matches=list(TOKEN.finditer(t)); verb=matches[0][0] if matches else ''
        if verb in VERBS or verb.startswith('END-') or verb in ('ELSE','INVALID','NOT'):statement=verb
        # Token spans exclude literals and hyphens embedded in identifiers.
        for m in matches:
            tok=m[0]
            if tok in ('=','>','<','>=','<=','<>') and statement!='COMPUTE':
                add(i,'relational',t[:m.start()]+{'=':'<>','<>':'=','>':'<=','<':'>=','>=':'<','<=':'>'}[tok]+t[m.end():])
            if tok in ('+','-','*','/') and statement=='COMPUTE':
                add(i,'arithmetic',t[:m.start()]+{'+':'-','-':'+','*':'/','/':'*'}[tok]+t[m.end():])
            if tok.isdigit():
                for delta in (-1,1):add(i,'constant',t[:m.start()]+str(int(tok)+delta)+t[m.end():])
        if verb=='IF':
            # Negate the complete predicate, including continuation OR/AND
            # lines, rather than accidentally changing only its first operand.
            end=i;expr=[t[2:].strip()]
            while end+1<len(lines):
                nxt=lines[end+1].strip()
                if not nxt:break
                first=nxt.split()[0]
                if first in VERBS or first.startswith('END-') or first in ('ELSE','INVALID','NOT'):break
                expr.append(nxt);end+=1
            expr[0]='IF NOT ('+expr[0];expr[-1]+=')'
            add(i,'negate-condition','\n'.join(expr),end)
        if verb=='COMPUTE':
            parts=t.split();at=parts.index('ROUNDED') if 'ROUNDED' in parts else None
            if at is None:parts.insert(2,'ROUNDED')
            else:parts.pop(at)
            add(i,'rounded',' '.join(parts))
        if verb in ('MOVE','ADD','COMPUTE','WRITE','REWRITE','PERFORM') and not t.startswith('PERFORM UNTIL'):
            end=i
            while end+1<len(lines):
                nxt=lines[end+1].strip()
                if not nxt:end+=1;continue
                first=nxt.split()[0]
                if first in VERBS or first.startswith('END-') or first in ('ELSE','INVALID','NOT') or nxt.endswith('.') and len(nxt.split())==1:break
                end+=1
                if nxt.endswith('.'):break
            # REWRITE handlers remain attached only for the original; delete entire scope.
            if verb=='REWRITE':
                stops=[j for j in range(i+1,min(i+15,len(lines))) if lines[j].strip().startswith('END-REWRITE')]
                if stops:end=stops[0]
            period=any(x.rstrip().endswith('.') for x in lines[i:end+1])
            add(i,'skip-PERFORM' if verb=='PERFORM' else 'delete-'+verb,'CONTINUE'+('.' if period else ''),end)
    return rows


def apply(text,mutant):
    if sha256(text.encode()).hexdigest()!=mutant['source_sha256']:raise ValueError('mutant-source-changed')
    lines=text.splitlines();a,b=mutant['line']-1,mutant['end_line']
    if '\n'.join(lines[a:b])!=mutant['original']:raise ValueError('mutant-site-changed')
    lines[a:b]=mutant['replacement'].splitlines()
    return '\n'.join(lines)+'\n'


def outcome(baseline,changed):
    if changed.get('status')=='not-compiled':return 'not-compiled'
    if changed.get('status')!='executed':return 'killed-failure'
    if changed.get('returncode')!=baseline.get('returncode'):return 'killed-failure'
    if changed.get('outputs')!=baseline.get('outputs') or changed.get('stdout_sha256')!=baseline.get('stdout_sha256') or changed.get('stderr_sha256')!=baseline.get('stderr_sha256'):return 'killed-divergent'
    return 'survived'


def generate(text,program):
    """All pinned program sites plus every receiving PIC in included copybooks."""
    from .zos_bindings import ROOT
    rows=_source_sites(text,program)
    for book in sorted(set(re.findall(r'^\s*COPY ([A-Z0-9]+)\.', '\n'.join(code(x) for x in text.splitlines()), re.M))):
        path=ROOT/'spec/mainframe/copybooks'/f'{book}.cpy'
        for row in _source_sites(path.read_text(),program+'-'+book):
            row['source_path']=f'{book}.cpy';rows.append(row)
    return rows


def apply_derived(original, derived, mutant):
    """One-line source-bound changes in a fault copy; never mutate the seam.

    Instrumented predicate probes describe the original, so this mode is only
    for output/RC mutation comparison, never for claimed changed-code coverage.
    Removed operation/handler lines or multi-line statements are incompatible.
    """
    apply(original, mutant)  # Validate exact source and operand first.
    if mutant.get('source_path') or mutant['line'] != mutant['end_line']:
        raise ValueError('fault-mutant-incompatible-site')
    lines=derived.splitlines();marker=f"      *LY-ORIGINAL-LINE={mutant['line']}"
    if lines.count(marker)!=1:raise ValueError('fault-mutant-site-removed')
    at=lines.index(marker)+1;before=code(mutant['original']).strip();actual=code(lines[at]).strip()
    if actual.rstrip('.')!=before.rstrip('.'):raise ValueError('fault-mutant-operand-changed')
    replacement=mutant['replacement']
    if before.endswith('.') and not actual.endswith('.'):replacement=replacement.rstrip().removesuffix('.')
    lines[at]=replacement
    return '\n'.join(lines)+'\n'
