"""Narrow, listed equivalence arguments for source-bound overwritten sentinels."""
from .scenario_coverage import code
from hashlib import sha256

# Reviewed initializers immediately before an operation followed by complete
# FILE STATUS success/failure assignment to APPL-RESULT, before any consumer.
SITES={'CBACT04C':{235,253,271,290,308,523,542,560,578,596},
       'CBTRN02C':{237,255,274,292,310,328,450,563,583,601,620,638,656,675}}


def argument(text,program,mutant,compiler_layout=None,storage=None):
    reviewed_sources={'CBACT04C':'5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4',
                      'CBTRN02C':'708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f'}
    if sha256(text.encode()).hexdigest()!=reviewed_sources.get(program):raise ValueError('equivalence-source-changed-needs-new-review')
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
    success_sites={'CBACT04C':{328,358,379,401,423,447,502},'CBTRN02C':{348,482,513,531}}
    if uses_bounded and mutant['operator']=='delete-MOVE' and mutant['line'] in success_sites[program] and words==['MOVE','0','TO','APPL-RESULT']:
        return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_line=mutant['line'],
          argument='Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.',
          supporting_source_lines=([182,186,188,190,191,197,203,205,213,215,220,224,328,331,333,340,423,435,438,447,632] if program=='CBACT04C' else [195,200,202,204,205,208,210,213,216,348,352,354,362,370,382,395,450,453,482,495,496,498,513,531,563,566]),
          approval='listed-for-operator-review; not a release approval')
    host_storage=storage==dict(unsigned_lengths=[2,2],timing_lengths=[4,8],initial_defaults=True,overlay_equalities=512,overlay_maximum=255)
    if host_storage:
        old=code(mutant['original'])
        message=None
        if mutant['operator']=='receiving-size' and 'TWO-BYTES-BINARY' in old:
            message='The pinned compiler probe records both unsigned9(4) and9(3) as2-byte storage. Every possible second status byte is exercised (256 values); after the unchanged zero-and-right-byte writes, the largest numeric value is255, fitting both pictures. The same byte representation/offset and every representable use are preserved.'
        if mutant['operator']=='constant' and 'MOVE 0' in old and 'TWO-BYTES-BINARY' in old:
            message='The pinned compiler exhaustively tested every256 possible right-byte value: both unsigned initializers+1 and-1 followed by the unchanged right-byte write matched initializer0 (512 equalities). The left byte and final numeric/display value are thus identical for the full byte domain, not merely the declared fault statuses.'
        if mutant['operator']=='receiving-scale' and 'TIMING' in old:
            message='TIMING has a sole integral assignment0 immediately before its only external read. The pinned compiler records the original and scaled binary storage as4/8 bytes; binary zero consists entirely of zero bytes, so the terminating host shim reading its declared4-byte parameter still receives0. No other field offset or raw group is consumed. This is scoped to the recorded host ABI, not native z/OS.'
        if mutant['operator']=='delete-MOVE' and old.split()==['MOVE','0','TO','TIMING']:
            message='The pinned compiler probe records initial TIMING0. The only assignment is MOVE0 and the only read is the one terminal host CEE3ABD call; that shim stops the process. Deleting this zero assignment cannot expose another value in this one-invocation execution contract.'
        if program=='CBACT04C' and mutant['operator']=='delete-MOVE' and mutant['line'] in (491,492,493,494):
            message='The pinned compiler probe confirms initial numeric storage0 and alphanumeric storage spaces. These four working-storage merchant fields have no other writer/alias or group initialization; each transaction only writes the same0/spaces before output. By induction all records preserve those values when this single redundant assignment is deleted. Scoped to this recorded one-invocation host runtime; no implicit z/OS equivalence.'
        if mutant['operator']=='delete-MOVE' and old.split()==['MOVE','0','TO','TWO-BYTES-BINARY']:
            message='The pinned compiler probe confirms this unsigned binary item initially has numeric0. Its only other writer overwrites the right byte before every read; the left byte is never changed. The unchanged whole-item zero assignment only re-zeroes that already-zero left byte, while the following right-byte write replaces the other byte. Induction over all calls preserves both final bytes for the entire256-byte input domain.'
        if message:
            return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_line=mutant['line'],argument=message,
              compiler_storage_semantics=storage,supporting_source_lines=[mutant['line']],approval='listed-for-operator-review; not a release approval')
    if mutant['operator']=='constant' and words==['MOVE','IO-STAT1','TO','IO-STATUS-04(1:1)'] and replacement==['MOVE','IO-STAT1','TO','IO-STATUS-04(1:2)']:
        return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_line=mutant['line'],
          argument='The only additional write is padding destination byte2 with a space. Before any display/read of IO-STATUS-04, the unchanged MOVE TWO-BYTES-BINARY TO IO-STATUS-0403 overwrites bytes2-4 completely. Byte1 is unchanged and intermediate operations access only the separate TWO-BYTES item. Thus the extra destination byte is a dead store for every status byte value.',
          supporting_source_lines=list(range(mutant['line'],mutant['line']+5)),approval='listed-for-operator-review; not a release approval')
    if mutant['operator']=='delete-MOVE' and words==["MOVE","'0000'","TO","IO-STATUS-04"]:
        return dict(kind='argued',mutant_id=mutant['id'],source_sha256=mutant['source_sha256'],source_line=mutant['line'],
          argument='IO-STATUS-04 consists of PIC9 VALUE0 followed by PIC999 VALUE0, so its initial four bytes are0000. In this numeric-status branch, the following MOVE overwrites bytes3-4. Bytes1-2 remain their initial00. Every call is on an error path immediately followed by the terminating host CEE3ABD shim; there is no subsequent invocation with a previously formatted nonnumeric status. Thus this single deletion preserves all displayed bytes under the recorded one-invocation host contract, not an arbitrary returning abend implementation.',
          supporting_source_lines=([129,130,131,644,645,646,632] if program=='CBACT04C' else [138,139,140,723,724,725,711]),approval='listed-for-operator-review; not a release approval')
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
