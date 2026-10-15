"""Exact local arithmetic proof with independent twin validation per statement.

No path assumptions are required: proofs cover the entire PIC domain, including
old receiving state. Aliases, partial writes, divisions, variable arithmetic
precision and size-error handlers are refused rather than approximated.
"""
from decimal import Decimal
from fractions import Fraction
import json
import random
import re
import subprocess
from pathlib import Path

from .equivalence_automation import digest, sealed, refs
from .generic_scenario_ir import expression
from .source import tokenize
from .legacy_twin import execute, clean_env
from .equivalence_compiler import require_ci

VERSION = '4.15.3.0'


class Unsupported(ValueError): pass


def symbols(ir):
    result = {}
    for field in ir['fields']:
        name = field['path'].split('.')[-1]
        if name in result: result[name] = None
        else: result[name] = field
    return result


def statement(text, ir):
    """One complete statement, all numeric targets, no implicit conversion."""
    tokens = [t.text for t in tokenize(text, 'statement.cbl')]
    if tokens[-1:] == ['.']: tokens.pop()
    fields = symbols(ir)
    types = {k: v['type'] if v else None for k, v in fields.items()}
    if not tokens: raise Unsupported('empty-statement')
    verb = tokens.pop(0)
    rounded = False
    if verb == 'CONTINUE' and not tokens: return dict(kind='noop', fields={})
    if any(t in tokens for t in ('ON', 'SIZE', 'ERROR', 'GIVING', 'REMAINDER')):
        raise Unsupported('size-error-or-multiple-written-state-not-encoded')
    if verb == 'COMPUTE':
        target = tokens.pop(0)
        if tokens[:1] == ['ROUNDED']: rounded = True; tokens.pop(0)
        if not tokens or tokens.pop(0) != '=': raise Unsupported('compute-form')
        expr = expression(tokens, types)
    elif verb in ('MOVE', 'ADD', 'SUBTRACT', 'MULTIPLY'):
        marker = {'MOVE': 'TO', 'ADD': 'TO', 'SUBTRACT': 'FROM', 'MULTIPLY': 'BY'}[verb]
        if marker not in tokens: raise Unsupported('assignment-form')
        k = tokens.index(marker)
        if len(tokens) != k+2: raise Unsupported('multiple-or-partial-target')
        target = tokens[-1]; expr = expression(tokens[:k], types)
        if verb != 'MOVE':
            from .generic_scenario_ir import Expression
            expr = Expression('binary', 'decimal', {'ADD': '+', 'SUBTRACT': '-', 'MULTIPLY': '*'}[verb],
                              (expression([target], types), expr))
    else: raise Unsupported('statement-shape:' + verb)
    from dataclasses import asdict
    expr = asdict(expr)
    names = refs(expr) | {target}
    selected = {name: fields.get(name) for name in names}
    for name, field in selected.items():
        if not field or field['type'] != 'decimal' or field['digits'] > 18 or field['separate'] or field['filler']:
            raise Unsupported('unsupported-field:' + name)
        if field['usage'] not in ('DISPLAY', 'COMP-3', 'BINARY'): raise Unsupported('usage:' + field['usage'])
    def check(e):
        if e['kind'] == 'binary' and e['value'] not in ('+', '-', '*'): raise Unsupported('non-polynomial-expression')
        for child in e.get('operands', ()): check(child)
    check(expr)
    return dict(kind='assignment', verb=verb, target=target, expression=expr, rounded=rounded, fields=selected)


def pair(text, mutant, ir):
    """Find full enclosing statement; a changed continuation is never isolated."""
    if mutant.get('source_path') or mutant['operator'].startswith('receiving-'):
        raise Unsupported('layout-mutation-requires-whole-program-proof')
    from .systematic_mutation import apply
    changed = apply(text, mutant)
    from .scenario_coverage import code, VERBS
    lines = text.splitlines(); start = mutant['line'] - 1
    while start >= 0:
        words = code(lines[start]).split()
        if words and words[0] in VERBS: break
        if words and words[-1].endswith('.'): raise Unsupported('statement-boundary')
        start -= 1
    if start < 0: raise Unsupported('statement-start')
    end = max(mutant['end_line'], start+1)
    while end < len(lines):
        words = code(lines[end]).split()
        if not words: end += 1; continue
        if words[0] in VERBS or words[0].startswith('END-') or words[0] in ('ELSE', 'INVALID', 'NOT') or (len(words) == 1 and words[0].endswith('.')): break
        end += 1
        if words[-1].endswith('.'): break
    original = '\n'.join(lines[start:end])
    delta = len(mutant['replacement'].splitlines()) - (mutant['end_line']-mutant['line']+1)
    replacement = '\n'.join(changed.splitlines()[start:end+delta])
    a, b = statement(original, ir), statement(replacement, ir)
    target = a.get('target') or b.get('target')
    if not target or a.get('target', target) != b.get('target', target): raise Unsupported('different-written-state')
    fields = {**a['fields'], **b['fields']}
    return dict(original=a, mutant=b, fields=fields, target=target,
                original_source=original, mutant_source=replacement,
                local_scope='entire PIC domain; no inferred dominating guards; complete receiving bytes plus size-error flag',
                path_masking=False)


def trunc(value):
    return int(value)  # Fraction/int truncates toward zero.


def eval_expr(expr, values):
    if expr['kind'] == 'literal': return Fraction(expr['value'])
    if expr['kind'] == 'reference': return values[expr['value']]
    args = [eval_expr(x, values) for x in expr['operands']]
    if expr['kind'] == 'unary': return -args[0] if expr['value'] == '-' else args[0]
    return {'+': lambda: args[0]+args[1], '-': lambda: args[0]-args[1], '*': lambda: args[0]*args[1]}[expr['value']]()


def receive(value, field, rounded, binary_truncate=True):
    scaled = value * 10**field['scale']
    n = trunc(abs(scaled) + Fraction(1, 2) if rounded else abs(scaled))
    error = n >= 10**field['digits']
    limit = 10**field['digits']
    if field['usage'] == 'BINARY' and not binary_truncate: limit = 2**(field['length']*8)
    n %= limit
    if field['signed'] and scaled < 0: n = -n
    if field['usage'] == 'BINARY' and not binary_truncate:
        n %= limit
        if field['signed'] and n >= limit//2: n -= limit
    return n, error


def stored_bytes(n, field, byteorder='big'):
    if field['usage'] == 'BINARY': return n.to_bytes(field['length'], byteorder, signed=field['signed'])
    digits = str(abs(n)).zfill(field['digits'])
    if field['usage'] == 'COMP-3':
        sign = 'd' if n < 0 else 'c' if field['signed'] else 'f'
        return bytes.fromhex((digits+sign).zfill(field['length']*2))
    if field['signed']:
        table = '}JKLMNOPQR' if n < 0 else '{ABCDEFGHI'
        digits = digits[:-1] + table[int(digits[-1])]
    return digits.encode('ascii')


def expected(stmt, values, target, field, binary_truncate):
    if stmt['kind'] == 'noop': return int(values[target]*10**field['scale']), False
    return receive(eval_expr(stmt['expression'], values), field, stmt['rounded'], binary_truncate)


def expression_z3(expr, variables, z3):
    if expr['kind'] == 'reference': return variables[expr['value']]
    if expr['kind'] == 'literal': return z3.RealVal(expr['value'])
    args = [expression_z3(x, variables, z3) for x in expr['operands']]
    if expr['kind'] == 'unary': return -args[0] if expr['value'] == '-' else args[0]
    return {'+': lambda: args[0]+args[1], '-': lambda: args[0]-args[1], '*': lambda: args[0]*args[1]}[expr['value']]()


def query(pair, binary_truncate=True):
    import z3
    # Every input is a scaled integer. No binary floating-point approximation.
    integers = {n: z3.Int(n) for n in sorted(pair['fields'])}
    values = {n: z3.ToReal(v)/10**pair['fields'][n]['scale'] for n, v in integers.items()}
    solver = z3.Solver(); solver.set(timeout=30000, random_seed=0)
    for name, field in pair['fields'].items():
        hi = 10**field['digits']-1
        solver.add(integers[name] >= (-hi if field['signed'] else 0), integers[name] <= hi)
    field = pair['fields'][pair['target']]
    def state(stmt):
        if stmt['kind'] == 'noop': return integers[pair['target']], z3.BoolVal(False)
        value = expression_z3(stmt['expression'], values, z3)*10**field['scale']
        magnitude = z3.If(value < 0, -value, value)
        n = z3.ToInt(magnitude + (z3.RealVal('0.5') if stmt['rounded'] else 0))
        error = n >= 10**field['digits']
        limit = 10**field['digits'] if binary_truncate or field['usage'] != 'BINARY' else 2**(field['length']*8)
        n = n % limit
        n = z3.If(value < 0, -n, n) if field['signed'] else n
        if field['usage'] == 'BINARY' and not binary_truncate:
            n = n % limit
            if field['signed']: n = z3.If(n >= limit//2, n-limit, n)
        return n, error
    a, ae = state(pair['original']); b, be = state(pair['mutant'])
    solver.add(z3.Or(a != b, ae != be))
    return solver, integers


def validate_pair(pair, folder, binary_truncate=True, byteorder='big', count=10000):
    """Batch random PIC-domain inputs through actual COBOL and independent encoder.

    Both value and every receiving byte are checked. A disagreement disables
    this exact statement/PIC shape; it cannot be made harmless by a proof result.
    """
    require_ci()
    if count < 10000: raise ValueError('encoder-validation-minimum')
    folder.mkdir(parents=True)
    rng = random.Random(digest(pair)); names = sorted(pair['fields']); target = pair['target']; field = pair['fields'][target]
    vectors = []
    for i in range(count):
        values = {}
        for name in names:
            f = pair['fields'][name]; hi = 10**f['digits']-1; lo = -hi if f['signed'] else 0
            n = (lo, hi, 0, 1, -1 if f['signed'] else hi)[i] if i < 5 else rng.randint(lo, hi)
            values[name] = Fraction(n, 10**f['scale'])
        vectors.append(values)
    def decimal_string(v):
        # Domain denominators are powers of ten; Decimal is exact at <=18 digits.
        return str(Decimal(v.numerator)/Decimal(v.denominator))
    input_bytes = ('\n'.join(decimal_string(v[n]) for v in vectors for n in names)+'\n').encode()
    (folder/'inputs.txt').write_bytes(input_bytes)
    reports = []
    for label in ('original', 'mutant'):
        declarations = []
        for name in names:
            f = pair['fields'][name]
            declarations.append(f"01 {name} PIC {f['picture']} {f['usage']}.")
            if name == target: declarations.append(f"01 LY-RAW REDEFINES {name} PIC X({f['length']}).")
        # Statement has only names declared above. Remove fixed-format comments.
        from .scenario_coverage import code
        body = ' '.join(code(line).strip() for line in pair[label+'_source'].splitlines()).rstrip('.')
        source = '\n'.join(['identification division.', 'program-id. probe.', 'data division.', 'working-storage section.',
                            *declarations, '01 LY-I binary-long.', '01 LY-J binary-long.', '01 LY-BYTE PIC 999.',
                            'procedure division.', f'perform {count} times',
                            *['accept '+name for name in names], body,
                            f'perform varying LY-J from 1 by 1 until LY-J > {field["length"]}',
                            'compute LY-BYTE = function ord(LY-RAW(LY-J:1)) - 1',
                            'display LY-BYTE with no advancing', 'end-perform', 'display "|"',
                            'end-perform', 'stop run.'])+'\n'
        path = folder/(label+'.cob'); path.write_text(source)
        execute(['cobc','-x','-free','-std=ibm','-fsign=EBCDIC','-O2', path.name,'-o',label],folder,folder/(label+'-compile'))
        run = subprocess.run([str((folder/label).resolve())], input=input_bytes, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=clean_env(), timeout=120)
        (folder/(label+'.stdout')).write_bytes(run.stdout); (folder/(label+'.stderr')).write_bytes(run.stderr)
        observed = run.stdout.splitlines(); mismatches = []
        if run.returncode or len(observed) != count:
            mismatches.append(dict(reason='execution-or-row-count', returncode=run.returncode, rows=len(observed)))
        else:
            for i, (values, row) in enumerate(zip(vectors, observed)):
                n, _ = expected(pair[label], values, target, field, binary_truncate)
                want = b''.join(f'{b:03d}'.encode() for b in stored_bytes(n, field, byteorder)) + b'|'
                if row != want and len(mismatches) < 10: mismatches.append(dict(index=i, expected=want.decode(), actual=row.decode(errors='replace')))
        reports.append(dict(side=label, tested=count, agreement=not mismatches, mismatches=mismatches,
                            source_sha256=digest(source.encode()), stdout_sha256=digest(run.stdout)))
    report = sealed(dict(shape_sha256=digest(pair), input_sha256=digest(input_bytes), count=count,
                         reports=reports, enabled=all(r['agreement'] for r in reports),
                         binary_truncate=binary_truncate, byteorder=byteorder,
                         complete_written_state='all receiving storage bytes; solver also compares overflow condition'))
    (folder/'validation.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


def prove(pair, folder, validation, binary_truncate=True):
    require_ci()
    from importlib.metadata import version
    if version('z3-solver') != VERSION: raise ValueError('unpinned-z3')
    if not validation['enabled'] or validation['shape_sha256'] != digest(pair): raise ValueError('encoder-disabled')
    solver, integers = query(pair, binary_truncate)
    smt = solver.to_smt2(); (folder/'query.smt2').write_text(smt)
    result = str(solver.check()); model = None
    if result == 'sat':
        model = {n: str(solver.model().eval(v, model_completion=True)) for n,v in integers.items()}
    report = sealed(dict(result=result, version=VERSION, query_sha256=digest(smt.encode()),
                         pair_sha256=digest(pair), validation_sha256=validation['content_sha256'],
                         complete_written_state=True, counterexample_scaled_integers=model,
                         counterexample_is_kill=False, scope='local-twin', timeout_ms=30000))
    (folder/'solver.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


def recheck(path):
    from importlib.metadata import version
    import z3
    from .equivalence_automation import verify
    report = verify(json.loads((path/'solver.json').read_text()))
    if version('z3-solver') != report['version'] or digest((path/'query.smt2').read_bytes()) != report['query_sha256']:
        raise ValueError('solver-binding')
    solver = z3.Solver(); solver.set(timeout=30000); solver.from_file(str(path/'query.smt2'))
    if str(solver.check()) != report['result']: raise ValueError('proof-not-reproduced')
    return report['result']
