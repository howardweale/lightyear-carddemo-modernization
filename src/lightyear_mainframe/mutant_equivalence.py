"""Narrow, listed equivalence arguments for source-bound overwritten sentinels."""
from .scenario_coverage import code
from hashlib import sha256

# Reviewed initializers immediately before an operation followed by complete
# FILE STATUS success/failure assignment to APPL-RESULT, before any consumer.
SITES={'CBACT04C':{235,253,271,290,308,523,542,560,578,596},
       'CBTRN02C':{237,255,274,292,310,328,450,563,583,601,620,638,656,675}}


def argument(text,program,mutant,compiler_layout=None):
    if not mutant.get('source_path') and sha256(text.encode()).hexdigest()!=mutant['source_sha256']:raise ValueError('equivalence-source-changed')
    if mutant.get('source_path'):
        if program=='CBACT04C' and mutant['source_path']=='CVACT03Y.cpy' and mutant['line'] in (6,7) and mutant['operator'] in ('receiving-size','receiving-scale'):
            from .zos_bindings import ROOT
            from .systematic_mutation import apply
            import re
            operand=(ROOT/'spec/mainframe/copybooks'/mutant['source_path']).read_text(encoding='utf-8')
            apply(operand,mutant)
            visible='\n'.join(code(x) for x in text.splitlines())
            if not re.search(r'(?<![A-Z0-9-])XREF-(?:CUST|ACCT)-ID(?![A-Z0-9-])',visible):
                return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_path=mutant['source_path'],program_sha256=sha256(text.encode()).hexdigest(),source_line=mutant['line'],
                  argument='INTCALC reads this copybook group via READ INTO and consumes only its first16-character XREF-CARD-NUM. The mutated customer/account receiving items follow those16 bytes and are never referenced or passed/output as a group. Key lookup uses the distinct unchanged FD fields. Changing this receiving suffix size/scale may truncate/pad unused bytes but preserves every consumed byte. This excludes FD key-layout mutations.',
                  supporting_source_lines=[395,495],approval='listed-for-operator-review; not a release approval')
        return None
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
    if uses_bounded and mutant['operator']=='delete-MOVE' and words==['MOVE','12','TO','APPL-RESULT']:
        candidates=[site for site in SITES[program] if site<mutant['line']<=site+12]
        if candidates:
            start=max(candidates);fragment=' '.join(' '.join(reviewed[start-1:mutant['line']]).split())
            if fragment.startswith('MOVE 8 TO APPL-RESULT') and 'MOVE 0 TO APPL-RESULT ELSE MOVE 12 TO APPL-RESULT' in fragment:
                return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_line=mutant['line'],
                  argument='The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.',
                  supporting_source_lines=list(range(start,mutant['line']+1)),approval='listed-for-operator-review; not a release approval')
    dead_reason=None
    if program=='CBACT04C':
        count_uses=[x for x in reviewed if 'WS-RECORD-COUNT' in x]
        if (mutant['line'] in (172,192) and mutant['operator'] in ('receiving-size','receiving-scale','constant','delete-ADD')
                and len(count_uses)==2 and count_uses[1]=='ADD 1 TO WS-RECORD-COUNT'):
            dead_reason='WS-RECORD-COUNT is a standalone working-storage counter whose only use is ADD1 to itself. It is never read by a condition, output, display, alias or external parameter. Size/scale/increment/deletion changes cannot affect observable program behavior.'
        if (mutant['line']==216 and mutant['operator']=='skip-PERFORM'
                and reviewed[517]=='1400-COMPUTE-FEES.' and reviewed[519]=='EXIT.'):
            dead_reason='The performed 1400-COMPUTE-FEES paragraph consists solely of EXIT and no executable side effect. Replacing that PERFORM with CONTINUE leaves state and control flow unchanged.'
    if program=='CBACT04C' and mutant['line']==220 and mutant['operator']=='skip-PERFORM':
        uses=[x for x in reviewed if 'END-OF-FILE' in x]
        if (len(uses)==5 and reviewed[187]=="PERFORM UNTIL END-OF-FILE = 'Y'" and reviewed[188]=="IF  END-OF-FILE = 'N'"
                and reviewed[339]=="MOVE 'Y' TO END-OF-FILE"):
            dead_reason='END-OF-FILE startsN and its only assignment isY. The enclosing TEST BEFORE UNTIL rejectsY, so the first IF always seesN. This PERFORM is in that first IF ELSE and is unreachable in the pinned source, including declared I/O faults. Its deletion is equivalent; this does not repair the original missing final-account update.'
    if compiler_layout=={'S9(9)':4,'S9(8)':4,'S9(4)':2,'S9(3)':2} and mutant['operator']=='receiving-size' and mutant['line'] in ({133,138,139,177} if program=='CBACT04C' else {142,147,148}):
        old=code(mutant['original'])
        if any(name in old for name in ('APPL-RESULT','ABCODE','TIMING','PARM-LENGTH')):
            dead_reason='The recorded compiler LENGTH probe confirms this isolated binary item remains in the same GnuCOBOL storage-size class (9/8digits:4bytes;4/3digits:2bytes). All assignments are small integers (APPL-RESULT0/8/12/16, ABCODE999, TIMING0, parameter length10), representable in both pictures. It has no arithmetic range-dependent use or changed external field offset; by-reference ABI and numeric comparisons are preserved. This argument is for the pinned host compiler, not z/OS equivalence.'
    if mutant['operator']=='receiving-scale' and 'APPL-RESULT' in code(mutant['original']):
        dead_reason='APPL-RESULT has only integral0/8/12/16 assignments and numeric0/16 condition-name consumers. Adding one fractional digit preserves all those exactly; it is not displayed, aliased or passed externally. Physical storage change is unobservable to this program.'
    if (program=='CBACT04C' and mutant['line']==169 and mutant['operator']=='receiving-scale') or (program=='CBTRN02C' and mutant['line']==187 and mutant['operator'] in ('receiving-scale','rounded')):
        dead_reason='The accumulator receives only sums/differences of source amounts already quantized to cents, with the same integer range. An added fractional digit or ROUNDED on this exact cent-valued sum cannot change its value or overflow condition. Its consumers are numeric assignment/comparison, never raw storage output.'
    if program=='CBTRN02C' and mutant['line']==403 and mutant['operator']=='rounded':
        dead_reason='WS-TEMP-BAL sums/differences three two-decimal source amounts. The exact result is cent-valued, so ROUNDED to the existing two-decimal target cannot change the result or integer overflow.'
    if mutant['operator']=='receiving-scale' and mutant['line']==({'CBACT04C':164,'CBTRN02C':173}[program]) and 'DB2-MIL' in code(mutant['original']):
        if any("MOVE '0000'" in x and 'DB2-REST' in x for x in reviewed):
            dead_reason='DB2-MIL receives an integral two-digit COB-MIL. Adding one fractional picture digit appends a stored zero. The immediately following DB2-REST is assigned four literal zeros. The whole timestamp is moved into fixed26-character transaction fields, so the new27-character group loses only its final zero. Every copied byte remains identical for every two-digit millisecond input; no numeric field offset is consumed externally.'
    if program=='CBACT04C' and mutant['operator']=='receiving-scale' and mutant['line']==173:
        dead_reason='WS-TRANID-SUFFIX starts0 and is incremented by integral1. Its only read is STRING after the10-character parameter date into the16-character transaction ID. The added fractional digit stays0 and becomes the seventeenth character, outside that fixed target. The six integer digits and their overflow range are unchanged; no raw suffix/group consumer exists.'
    if dead_reason:
        return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_line=mutant['line'],
          argument=dead_reason,supporting_source_lines=[172,192] if mutant['line'] in (172,192) else [216,518,520] if mutant['line']==216 else [137,188,189,220,340] if mutant['line']==220 else [mutant['line']],
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
