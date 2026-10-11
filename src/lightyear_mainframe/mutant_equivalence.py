"""Narrow, listed equivalence arguments for source-bound overwritten sentinels."""
from .scenario_coverage import code
from hashlib import sha256

# Reviewed initializers immediately before an operation followed by complete
# FILE STATUS success/failure assignment to APPL-RESULT, before any consumer.
SITES={'CBACT04C':{235,253,271,290,308,523,542,560,578,596},
       'CBTRN02C':{237,255,274,292,310,328,450,563,583,601,620,638,656,675}}


def argument(text,program,mutant):
    if not mutant.get('source_path') and sha256(text.encode()).hexdigest()!=mutant['source_sha256']:raise ValueError('equivalence-source-changed')
    if mutant.get('source_path'):return None
    from .systematic_mutation import apply
    apply(text,mutant)
    # All consumers of APPL-RESULT are the 0/16 condition names. The raw
    # working-storage item is neither displayed nor passed/aliased externally.
    reviewed=[code(x).strip() for x in text.splitlines()]
    raw_uses=[x for x in reviewed if 'APPL-RESULT' in x]
    uses_bounded=all(x.startswith(('01  APPL-RESULT','MOVE ')) for x in raw_uses)
    words=code(mutant['original']).split()
    replacement=code(mutant['replacement']).split()
    if (uses_bounded and mutant['operator']=='constant' and words==['MOVE','12','TO','APPL-RESULT']
            and replacement in (['MOVE','11','TO','APPL-RESULT'],['MOVE','13','TO','APPL-RESULT'])):
        return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_line=mutant['line'],
          argument='Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.',
          supporting_source_lines=[i+1 for i,x in enumerate(reviewed) if 'APPL-RESULT' in x or '88  APPL-' in x],
          approval='listed-for-operator-review; not a release approval')
    dead_reason=None
    if program=='CBACT04C':
        count_uses=[x for x in reviewed if 'WS-RECORD-COUNT' in x]
        if (mutant['line'] in (172,192) and mutant['operator'] in ('receiving-size','receiving-scale','constant','delete-ADD')
                and len(count_uses)==2 and count_uses[1]=='ADD 1 TO WS-RECORD-COUNT'):
            dead_reason='WS-RECORD-COUNT is a standalone working-storage counter whose only use is ADD1 to itself. It is never read by a condition, output, display, alias or external parameter. Size/scale/increment/deletion changes cannot affect observable program behavior.'
        if (mutant['line']==216 and mutant['operator']=='skip-PERFORM'
                and reviewed[517]=='1400-COMPUTE-FEES.' and reviewed[519]=='EXIT.'):
            dead_reason='The performed 1400-COMPUTE-FEES paragraph consists solely of EXIT and no executable side effect. Replacing that PERFORM with CONTINUE leaves state and control flow unchanged.'
    if dead_reason:
        return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_line=mutant['line'],
          argument=dead_reason,supporting_source_lines=[172,192] if mutant['line'] in (172,192) else [216,518,520],
          approval='listed-for-operator-review; not a release approval')
    if mutant['line'] not in SITES[program]:return None
    if mutant['operator'] not in ('constant','delete-MOVE'):return None
    lines=[code(x).strip() for x in text.splitlines()]
    if lines[mutant['line']-1].replace('  ',' ').split()!=['MOVE','8','TO','APPL-RESULT.'] and lines[mutant['line']-1].split()!=['MOVE','8','TO','APPL-RESULT']:
        raise ValueError('equivalence-reviewed-operand-changed')
    block=lines[mutant['line']:mutant['line']+12]
    consumer=next((i for i,line in enumerate(block) if line.startswith('IF') and 'APPL-AOK' in line),None)
    if consumer is None:raise ValueError('equivalence-consumer-changed')
    fragment=' '.join(block[:consumer]).replace('  ',' ')
    words=fragment.split()
    normalized=' '.join(words)
    if not all(s in normalized for s in ('MOVE 0 TO APPL-RESULT','MOVE 12 TO APPL-RESULT','ELSE','END-IF')):raise ValueError('equivalence-total-overwrite-not-established')
    return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_line=mutant['line'],
      argument='The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.',
      supporting_source_lines=list(range(mutant['line'],mutant['line']+consumer+2)),approval='listed-for-operator-review; not a release approval')
