"""Narrow typed-IR classes. Match evidence never substitutes for a signature."""
import re
from .equivalence_automation import digest, sealed, refs
from .equivalence_solver import pair, Unsupported
from .scenario_coverage import code

CLASSES = {
    'adjacent-dead-literal-store/1': {
        'argument': 'Both variants only store a numeric literal or do nothing. The next executable statement is an unconditional MOVE to the same unaliased elementary item, without reading it. There is no intervening statement, label, branch or external call. Thus every path from the mutated store overwrites all its bytes before any read.',
        'limits': 'Two adjacent MOVE statements; no alias, partial write, control transfer, conversion error, multiple receiving item or declaration mutation.'},
    'receiving-pic-identity/1': {
        'argument': 'The saved integer-domain query proves that both conversions produce the same complete receiving state for every input allowed by every source PIC. An enabled twin-validated encoder is required. This class does not infer downstream masking.',
        'limits': 'Exact local statement/PIC tuple, saved UNSAT query and independently validated encoder.'},
}


def dead_store(ir, text, mutant):
    try: p = pair(text, mutant, ir)
    except ValueError: return None
    a, b = p['original'], p['mutant']; field = p['fields'][p['target']]
    if a.get('verb') != 'MOVE' or a['expression']['kind'] != 'literal': return None
    if b['kind'] != 'noop' and (b.get('verb') != 'MOVE' or b['expression']['kind'] != 'literal'): return None
    # Literal numeric MOVE must not introduce an exceptional conversion.
    from fractions import Fraction
    for s in (a, b):
        if s['kind'] != 'noop' and abs(Fraction(s['expression']['value'])) >= 10**(field['digits']-field['scale']): return None
    lines = text.splitlines(); following = mutant['end_line']
    while following < len(lines) and not code(lines[following]).strip(): following += 1
    if following == len(lines): return None
    next_statement = next((s for s in ir['statements'] if s['location']['line'] == following+1 and s['location']['path'].endswith('.cbl')), None)
    if not next_statement or next_statement.get('verb') != 'MOVE' or next_statement.get('target') != p['target']: return None
    if p['target'] in refs(next_statement['expression']): return None
    # Require a complete one-line MOVE, avoiding an unparsed size-error clause.
    from .equivalence_solver import statement
    try: parsed = statement(lines[following], ir)
    except ValueError: return None
    if parsed.get('target') != p['target']: return None
    return sealed(dict(class_id='adjacent-dead-literal-store/1', mutant_sha256=digest(mutant),
                       target=p['target'], overwrite_line=following+1, pair_sha256=digest(p),
                       argument=CLASSES['adjacent-dead-literal-store/1']['argument']))


def class_contract(job, head, class_id, matches, packet_path, packet_sha256, matcher_sha256):
    if not matches: raise ValueError('empty-class-request')
    proof = sealed(dict(class_id=class_id, matcher_sha256=matcher_sha256,
                        matches=matches, claim_scope='twin', head=head,
                        argument=CLASSES.get(class_id, {}).get('argument', 'Source-bound legacy APPL-RESULT census and listed dependencies; full operator review required.')))
    from lightyear_control_tower.factory_policy import validate_contract
    contract = dict(schema='factory-contract/1', kind='equivalence-review', program=job if job in ('INTCALC', 'POSTTRAN') else 'factory',
                    sources=[dict(path=packet_path, sha256=packet_sha256, commit=head)],
                    details=dict(packet_sha256=packet_sha256, items=sorted(matches), class_proof_sha256=proof['content_sha256'],
                                 reviewer_type='human', claim_scope='twin', dependencies=[dict(class_id=class_id, matcher_sha256=matcher_sha256)]))
    validate_contract(contract)
    return dict(contract=contract, class_proof=proof, status='unsigned', resolves_members=False)


def signed_member(authority, request, proof, mutant_id, match, matcher_sha256):
    from .equivalence_automation import verify
    from .equivalence_compiler import require_ci
    verify(request['class_proof'])
    cp = request['class_proof']; contract = request['contract']
    if cp['matcher_sha256'] != matcher_sha256 or cp['matches'].get(mutant_id) != match:
        raise ValueError('class-match-binding')
    if contract['details']['class_proof_sha256'] != cp['content_sha256']:
        raise ValueError('class-proof-binding')
    if authority is None or not authority.signed_only: raise ValueError('signed-class-authority-required')
    decision = authority.equivalence(proof, contract, mutant_id, 'twin')
    return dict(class_id=cp['class_id'], decision_sha256=proof['decision_sha256'], match_sha256=digest(match))


def unobservable_counter(ir, text, mutant):
    """Closed token census for an isolated, unconsumed numeric self-counter.

    This is an oracle-gap finding only. No equivalence exclusion follows from
    it. Layout mutations, aliases and group consumers are deliberately refused.
    """
    if mutant.get('source_path') or mutant['operator'] not in ('constant','delete-ADD'):return None
    try:p=pair(text,mutant,ir)
    except ValueError:return None
    a=p['original']
    if a.get('verb')!='ADD':return None
    target=p['target'];field=p['fields'][target]
    if field['location']['path'].endswith('.cpy'):return None
    if refs(a['expression'])!={target}:return None
    from .source import tokenize
    tokens=tokenize(text,'program.cbl');words=[t.text for t in tokens]
    if words.count('PROGRAM-ID')!=1 or any(w in words for w in ('EXTERNAL','GLOBAL','POINTER')):return None
    # A containing group is an implicit consumer of every member.
    parents=field['path'].split('.')[:-1]
    if any(words.count(parent)!=1 for parent in parents):return None
    occurrences=[t for t in tokens if t.text==target]
    if len(occurrences)!=2:return None
    lines={t.line for t in occurrences}
    if lines!={field['location']['line'],mutant['line']}:return None
    return sealed(dict(classification='unobservable',target=target,mutant_sha256=digest(mutant),
                       references=sorted(lines),parents=parents,source_sha256=digest(text.encode()),
                       reason='Only declaration and self-ADD reference this field; no parent-group consumer. Missing observable distinguishes an oracle gap, never a proof.',
                       resolved=False))
