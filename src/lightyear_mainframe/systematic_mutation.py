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
    if baseline.get('status')!='executed':return 'baseline-evidence-gap'
    if changed.get('status')!='executed':return 'mutant-evidence-gap'
    if changed.get('returncode')!=baseline.get('returncode'):return 'killed-failure'
    if changed.get('outputs')!=baseline.get('outputs') or changed.get('stdout_sha256')!=baseline.get('stdout_sha256') or changed.get('stderr_sha256')!=baseline.get('stderr_sha256'):return 'killed-divergent'
    return 'survived'


def candidates(text,program):
    """All pinned program sites plus every receiving PIC in included copybooks."""
    from .zos_bindings import ROOT
    rows=_source_sites(text,program)
    for book in sorted(set(re.findall(r'^\s*COPY ([A-Z0-9]+)\.', '\n'.join(code(x) for x in text.splitlines()), re.M))):
        path=ROOT/'spec/mainframe/copybooks'/f'{book}.cpy'
        for row in _source_sites(path.read_text(),program+'-'+book):
            row['source_path']=f'{book}.cpy';rows.append(row)
    return rows



def _display_lengths(text):
    """Prove only simple, local DISPLAY layouts; unknown usages stay unknown."""
    nodes=[];stack=[]
    for raw in text.splitlines():
        line=code(raw).strip()
        if line.startswith('PROCEDURE DIVISION'):break
        m=re.match(r'(\d{2})\s+([A-Z0-9-]+)\b(.*)',line)
        if not m:
            if line and stack:stack[-1]['unknown']=True
            continue
        level=int(m[1])
        if level==88:continue
        while stack and stack[-1]['level']>=level:stack.pop()
        tail=m[3];pic=re.search(r'\bPIC\s+([SX9V0-9()]+)(?=\s|\.|$)',tail)
        node=dict(name=m[2],level=level,children=[],size=None,unknown=False)
        node['unknown']=bool(re.search(r'\b(?:REDEFINES|OCCURS|COMP|BINARY|PACKED|SIGN|SYNC|USAGE)\b',tail))
        if pic:
            picture=pic[1]
            atoms=list(re.finditer(r'([SX9V])(?:\((\d+)\))?',picture))
            if ''.join(a[0] for a in atoms)!=picture:node['unknown']=True
            node['size']=sum(int(a[2] or 1) for a in atoms if a[1] not in 'SV')
        elif 'PIC' in tail:node['unknown']=True
        if stack:stack[-1]['children'].append(node)
        nodes.append(node);stack.append(node)
    def size(n):
        if n['unknown']:return None
        if n['size'] is not None:return n['size']
        children=[size(c) for c in n['children']]
        return sum(children) if children and all(x is not None for x in children) else None
    result={}
    for n in nodes:
        # Ambiguous names need qualification analysis; do not guess.
        result.setdefault(n['name'],[]).append(size(n))
    return {name:values[0] for name,values in result.items() if len(values)==1 and values[0] is not None}


def _invalid_literal_references(text,lengths):
    errors=set()
    for line,raw in enumerate(text.splitlines(),1):
        source=re.sub(r"'[^']*'|\"[^\"]*\"",'',code(raw))
        for m in re.finditer(r'([A-Z][A-Z0-9-]*)\s*\(\s*(-?\d+)\s*:\s*(-?\d+)\s*\)',source):
            start,length=int(m[2]),int(m[3]);size=lengths.get(m[1])
            if start<1 or length<1 or (size is not None and start+length-1>size):
                errors.add((line,m[1],start,length,size))
    return errors


def generation_inventory(text,program):
    """Preserve candidate IDs; separately list statically invalid sites avoided.

    This is not a compiler. Dynamic bounds and unknown storage layouts remain
    candidates and actual compiler refusals must still be reported separately.
    """
    retained=[];avoided=[];lengths=_display_lengths(text)
    original_errors=_invalid_literal_references(text,lengths)
    for row in candidates(text,program):
        if row.get('source_path'):
            # COPY layouts require whole-program expansion; defer to compiler.
            retained.append(row);continue
        if row['operator'] not in ('constant','receiving-size','receiving-scale'):
            retained.append(row);continue
        changed=apply(text,row)
        bound=_display_lengths(changed) if row['operator'].startswith('receiving-') else lengths
        errors=_invalid_literal_references(changed,bound)-original_errors
        if errors:
            avoided.append(dict(mutant=row,reason='statically-invalid-literal-reference-modification',
                                violations=[dict(line=e[0],field=e[1],offset=e[2],length=e[3],proven_size=e[4]) for e in sorted(errors)]))
        else:retained.append(row)
    return dict(candidates=retained,avoided=avoided,
                generated_site_count=len(retained)+len(avoided),avoided_count=len(avoided))


def generate(text,program):
    return generation_inventory(text,program)['candidates']


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
