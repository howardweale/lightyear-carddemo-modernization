"""Narrow, listed equivalence arguments for source-bound overwritten sentinels."""
from .scenario_coverage import code
from hashlib import sha256

# Reviewed initializers immediately before an operation followed by complete
# FILE STATUS success/failure assignment to APPL-RESULT, before any consumer.
SITES={'CBACT04C':{235,253,271,290,308,523,542,560,578,596},
       'CBTRN02C':{237,255,274,292,310,328,450,563,583,601,620,638,656,675}}


def argument(text,program,mutant):
    if not mutant.get('source_path') and sha256(text.encode()).hexdigest()!=mutant['source_sha256']:raise ValueError('equivalence-source-changed')
    if mutant.get('source_path') or mutant['line'] not in SITES[program]:return None
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
