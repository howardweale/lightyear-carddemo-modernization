# Individual review: 47 argued-equivalent mutants

Complete individually argued population from head `2dd787642e66176f78dbf749ec2659e82672cd3e`, run `38198096890`: 30 INTCALC and 17 POSTTRAN. No sampling or reroll. Compiler/class proofs are excluded. This is an operator review packet; independent findings and Howard decisions remain pending. Finite comparisons do not prove equivalence.

Review each argument against its pinned source and runtime scope. Record accept/reject/needs-evidence, reviewer, date and reasons. Supporting lines refer to the program even when the mutated item is in a copybook. Historical acceptance is retained separately. [Full evidence JSON](equivalence-individual-review-2026-10-12.json).

## INTCALC: 30 individual arguments

### CBACT04C-CVACT03Y-receiving-scale-6-2

Source: `spec/mainframe/copybooks/CVACT03Y.cpy` lines 6-6; SHA-256 `ffc6079e09b28739e154bf6c1e1c36d408209faa91f6cf7008078dc596a1c370`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           05  XREF-CUST-ID                      PIC 9(09).                     
```
Replacement:
```cobol
       05  XREF-CUST-ID                      PIC 9(09)V9(1).
```

INTCALC reads this copybook group via READ INTO and consumes only its first16-character XREF-CARD-NUM. The mutated customer/account receiving items follow those16 bytes and are never referenced or passed/output as a group. Key lookup uses the distinct unchanged FD fields. Changing this receiving suffix size/scale may truncate/pad unused bytes but preserves every consumed byte. This excludes FD key-layout mutations.

Supporting source lines: [395, 495]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-CVACT03Y-receiving-scale-7-4

Source: `spec/mainframe/copybooks/CVACT03Y.cpy` lines 7-7; SHA-256 `ffc6079e09b28739e154bf6c1e1c36d408209faa91f6cf7008078dc596a1c370`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           05  XREF-ACCT-ID                      PIC 9(11).                     
```
Replacement:
```cobol
       05  XREF-ACCT-ID                      PIC 9(11)V9(1).
```

INTCALC reads this copybook group via READ INTO and consumes only its first16-character XREF-CARD-NUM. The mutated customer/account receiving items follow those16 bytes and are never referenced or passed/output as a group. Key lookup uses the distinct unchanged FD fields. Changing this receiving suffix size/scale may truncate/pad unused bytes but preserves every consumed byte. This excludes FD key-layout mutations.

Supporting source lines: [395, 495]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-CVACT03Y-receiving-size-6-1

Source: `spec/mainframe/copybooks/CVACT03Y.cpy` lines 6-6; SHA-256 `ffc6079e09b28739e154bf6c1e1c36d408209faa91f6cf7008078dc596a1c370`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           05  XREF-CUST-ID                      PIC 9(09).                     
```
Replacement:
```cobol
       05  XREF-CUST-ID                      PIC 9(8).
```

INTCALC reads this copybook group via READ INTO and consumes only its first16-character XREF-CARD-NUM. The mutated customer/account receiving items follow those16 bytes and are never referenced or passed/output as a group. Key lookup uses the distinct unchanged FD fields. Changing this receiving suffix size/scale may truncate/pad unused bytes but preserves every consumed byte. This excludes FD key-layout mutations.

Supporting source lines: [395, 495]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-CVACT03Y-receiving-size-7-3

Source: `spec/mainframe/copybooks/CVACT03Y.cpy` lines 7-7; SHA-256 `ffc6079e09b28739e154bf6c1e1c36d408209faa91f6cf7008078dc596a1c370`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           05  XREF-ACCT-ID                      PIC 9(11).                     
```
Replacement:
```cobol
       05  XREF-ACCT-ID                      PIC 9(10).
```

INTCALC reads this copybook group via READ INTO and consumes only its first16-character XREF-CARD-NUM. The mutated customer/account receiving items follow those16 bytes and are never referenced or passed/output as a group. Key lookup uses the distinct unchanged FD fields. Changing this receiving suffix size/scale may truncate/pad unused bytes but preserves every consumed byte. This excludes FD key-layout mutations.

Supporting source lines: [395, 495]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-constant-192-48

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 192-192; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
                     ADD 1 TO WS-RECORD-COUNT                                   
```
Replacement:
```cobol
       ADD 0 TO WS-RECORD-COUNT
```

WS-RECORD-COUNT is a standalone working-storage counter whose only use is ADD1 to itself. It is never read by a condition, output, display, alias or external parameter. Size/scale/increment/deletion changes cannot affect observable program behavior.

Supporting source lines: [172, 192]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-constant-192-49

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 192-192; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
                     ADD 1 TO WS-RECORD-COUNT                                   
```
Replacement:
```cobol
       ADD 2 TO WS-RECORD-COUNT
```

WS-RECORD-COUNT is a standalone working-storage counter whose only use is ADD1 to itself. It is never read by a condition, output, display, alias or external parameter. Size/scale/increment/deletion changes cannot affect observable program behavior.

Supporting source lines: [172, 192]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-constant-638-382

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 638-638; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
               MOVE IO-STAT1 TO IO-STATUS-04(1:1)                               
```
Replacement:
```cobol
       MOVE IO-STAT1 TO IO-STATUS-04(1:2)
```

The only additional write is padding destination byte2 with a space. Before any display/read of IO-STATUS-04, the unchanged MOVE TWO-BYTES-BINARY TO IO-STATUS-0403 overwrites bytes2-4 completely. Byte1 is unchanged and intermediate operations access only the separate TWO-BYTES item. Thus the extra destination byte is a dead store for every status byte value.

Supporting source lines: [638, 639, 640, 641, 642]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-constant-639-384

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 639-639; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
               MOVE 0        TO TWO-BYTES-BINARY                                
```
Replacement:
```cobol
       MOVE -1        TO TWO-BYTES-BINARY
```

The pinned compiler exhaustively tested every256 possible right-byte value: both unsigned initializers+1 and-1 followed by the unchanged right-byte write matched initializer0 (512 equalities). The left byte and final numeric/display value are thus identical for the full byte domain, not merely the declared fault statuses.

Supporting source lines: [639]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-constant-639-385

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 639-639; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
               MOVE 0        TO TWO-BYTES-BINARY                                
```
Replacement:
```cobol
       MOVE 1        TO TWO-BYTES-BINARY
```

The pinned compiler exhaustively tested every256 possible right-byte value: both unsigned initializers+1 and-1 followed by the unchanged right-byte write matched initializer0 (512 equalities). The left byte and final numeric/display value are thus identical for the full byte domain, not merely the declared fault statuses.

Supporting source lines: [639]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-delete-ADD-192-50

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 192-192; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: True. Fresh disposition: evidence-gap.

Original:
```cobol
                     ADD 1 TO WS-RECORD-COUNT                                   
```
Replacement:
```cobol
       CONTINUE
```

WS-RECORD-COUNT is a standalone working-storage counter whose only use is ADD1 to itself. It is never read by a condition, output, display, alias or external parameter. Size/scale/increment/deletion changes cannot affect observable program behavior.

Supporting source lines: [172, 192]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-delete-MOVE-491-264

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 491-491; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           MOVE 0                    TO TRAN-MERCHANT-ID                        
```
Replacement:
```cobol
       CONTINUE
```

The pinned compiler probe confirms initial numeric storage0 and alphanumeric storage spaces. These four working-storage merchant fields have no other writer/alias or group initialization; each transaction only writes the same0/spaces before output. By induction all records preserve those values when this single redundant assignment is deleted. Scoped to this recorded one-invocation host runtime; no implicit z/OS equivalence.

Supporting source lines: [491]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-delete-MOVE-492-265

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 492-492; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           MOVE SPACES               TO TRAN-MERCHANT-NAME                      
```
Replacement:
```cobol
       CONTINUE
```

The pinned compiler probe confirms initial numeric storage0 and alphanumeric storage spaces. These four working-storage merchant fields have no other writer/alias or group initialization; each transaction only writes the same0/spaces before output. By induction all records preserve those values when this single redundant assignment is deleted. Scoped to this recorded one-invocation host runtime; no implicit z/OS equivalence.

Supporting source lines: [492]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-delete-MOVE-493-266

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 493-493; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           MOVE SPACES               TO TRAN-MERCHANT-CITY                      
```
Replacement:
```cobol
       CONTINUE
```

The pinned compiler probe confirms initial numeric storage0 and alphanumeric storage spaces. These four working-storage merchant fields have no other writer/alias or group initialization; each transaction only writes the same0/spaces before output. By induction all records preserve those values when this single redundant assignment is deleted. Scoped to this recorded one-invocation host runtime; no implicit z/OS equivalence.

Supporting source lines: [493]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-delete-MOVE-494-267

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 494-494; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           MOVE SPACES               TO TRAN-MERCHANT-ZIP                       
```
Replacement:
```cobol
       CONTINUE
```

The pinned compiler probe confirms initial numeric storage0 and alphanumeric storage spaces. These four working-storage merchant fields have no other writer/alias or group initialization; each transaction only writes the same0/spaces before output. By induction all records preserve those values when this single redundant assignment is deleted. Scoped to this recorded one-invocation host runtime; no implicit z/OS equivalence.

Supporting source lines: [494]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-delete-MOVE-630-373

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 630-630; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           MOVE 0 TO TIMING                                                     
```
Replacement:
```cobol
       CONTINUE
```

The pinned compiler probe records initial TIMING0. The only assignment is MOVE0 and the only read is the one terminal host CEE3ABD call; that shim stops the process. Deleting this zero assignment cannot expose another value in this one-invocation execution contract.

Supporting source lines: [630]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-delete-MOVE-639-386

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 639-639; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
               MOVE 0        TO TWO-BYTES-BINARY                                
```
Replacement:
```cobol
       CONTINUE
```

The pinned compiler probe confirms this unsigned binary item initially has numeric0. Its only other writer overwrites the right byte before every read; the left byte is never changed. The unchanged whole-item zero assignment only re-zeroes that already-zero left byte, while the following right-byte write replaces the other byte. Induction over all calls preserves both final bytes for the entire256-byte input domain.

Supporting source lines: [639]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-delete-MOVE-644-389

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 644-644; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
               MOVE '0000' TO IO-STATUS-04                                      
```
Replacement:
```cobol
       CONTINUE
```

IO-STATUS-04 consists of PIC9 VALUE0 followed by PIC999 VALUE0, so its initial four bytes are0000. In this numeric-status branch, the following MOVE overwrites bytes3-4. Bytes1-2 remain their initial00. Every call is on an error path immediately followed by the terminating host CEE3ABD shim; there is no subsequent invocation with a previously formatted nonnumeric status. Thus this single deletion preserves all displayed bytes under the recorded one-invocation host contract, not an arbitrary returning abend implementation.

Supporting source lines: [129, 130, 131, 644, 645, 646, 632]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-scale-133-20

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 133-133; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
       01  APPL-RESULT             PIC S9(9)   COMP.                            
```
Replacement:
```cobol
       01  APPL-RESULT             PIC S9(9)V9(1)   COMP.
```

APPL-RESULT has only integral0/8/12/16 assignments and numeric0/16 condition-name consumers. Adding one fractional digit preserves all those exactly; it is not displayed, aliased or passed externally. Physical storage change is unobservable to this program.

Supporting source lines: [133]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-scale-139-24

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 139-139; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
       01  TIMING                  PIC S9(9) BINARY.                            
```
Replacement:
```cobol
       01  TIMING                  PIC S9(9)V9(1) BINARY.
```

TIMING has a sole integral assignment0 immediately before its only external read. The pinned compiler records the original and scaled binary storage as4/8 bytes; binary zero consists entirely of zero bytes, so the terminating host shim reading its declared4-byte parameter still receives0. No other field offset or raw group is consumed. This is scoped to the recorded host ABI, not native z/OS.

Supporting source lines: [139]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-scale-164-26

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 164-164; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           06 DB2-MIL                   PIC 9(002).                             
```
Replacement:
```cobol
       06 DB2-MIL                   PIC 9(002)V9(1).
```

DB2-MIL receives an integral two-digit COB-MIL. Adding one fractional picture digit appends a stored zero. The immediately following DB2-REST is assigned four literal zeros. The whole timestamp is moved into fixed26-character transaction fields, so the new27-character group loses only its final zero. Every copied byte remains identical for every two-digit millisecond input; no numeric field offset is consumed externally.

Supporting source lines: [164]. Register dependencies: [].

Targeted valid/scheduled: 2/200. Outcomes: {'baseline-refusal': 198, 'survived': 2}. Evidence gaps: 198.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-scale-169-30

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 169-169; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           05 WS-TOTAL-INT              PIC S9(09)V99.                          
```
Replacement:
```cobol
       05 WS-TOTAL-INT              PIC S9(09)V9(3).
```

The accumulator receives only sums/differences of source amounts already quantized to cents, with the same integer range. An added fractional digit or ROUNDED on this exact cent-valued sum cannot change its value or overflow condition. Its consumers are numeric assignment/comparison, never raw storage output.

Supporting source lines: [169]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-scale-172-32

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 172-172; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           05 WS-RECORD-COUNT           PIC 9(09) VALUE 0.                      
```
Replacement:
```cobol
       05 WS-RECORD-COUNT           PIC 9(09)V9(1) VALUE 0.
```

WS-RECORD-COUNT is a standalone working-storage counter whose only use is ADD1 to itself. It is never read by a condition, output, display, alias or external parameter. Size/scale/increment/deletion changes cannot affect observable program behavior.

Supporting source lines: [172, 192]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-scale-173-34

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 173-173; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           05 WS-TRANID-SUFFIX          PIC 9(06) VALUE 0.                      
```
Replacement:
```cobol
       05 WS-TRANID-SUFFIX          PIC 9(06)V9(1) VALUE 0.
```

WS-TRANID-SUFFIX starts0 and is incremented by integral1. Its only read is STRING after the10-character parameter date into the16-character transaction ID. The added fractional digit stays0 and becomes the seventeenth character, outside that fixed target. The six integer digits and their overflow range are unchanged; no raw suffix/group consumer exists.

Supporting source lines: [173]. Register dependencies: [].

Targeted valid/scheduled: 2/200. Outcomes: {'baseline-refusal': 198, 'survived': 2}. Evidence gaps: 198.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-scale-72-6

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 72-72; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           05 FD-XREF-CUST-NUM                  PIC 9(09).                      
```
Replacement:
```cobol
       05 FD-XREF-CUST-NUM                  PIC 9(09)V9(1).
```

Pinned Berkeley DB host contract: this unused FD customer field gains one byte, shifting the alternate key buffer but changing neither key ordinal1 nor its11-byte value. GnuCOBOL bdb_findkey matches the current field pointer to ordinal1, bdb_setkey copies that field, and indexed_start_internal searches the existing ordinal1 index. The loader-built record remains50bytes, below both record maxima50/51; indexed_read copies its unchanged50bytes and READ INTO copies them to the unchanged50-byte XREF copybook. Only its16-byte card prefix is consumed. Error lookup displays still use the unchanged11-byte requested account value. No writes use this FD. Thus all valid fixed50-byte twin inputs and declared seams preserve observable behavior. This explicitly excludes malformed database files, different runtimes and z/OS; see the source/runtime argument document.

Supporting source lines: [37, 38, 70, 71, 72, 73, 74, 204, 393, 395, 397, 495]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-size-125-13

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 125-125; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
       01  TWO-BYTES-BINARY        PIC 9(4) BINARY.                             
```
Replacement:
```cobol
       01  TWO-BYTES-BINARY        PIC 9(3) BINARY.
```

The pinned compiler probe records both unsigned9(4) and9(3) as2-byte storage. Every possible second status byte is exercised (256 values); after the unchanged zero-and-right-byte writes, the largest numeric value is255, fitting both pictures. The same byte representation/offset and every representable use are preserved.

Supporting source lines: [125]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-size-138-21

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 138-138; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
       01  ABCODE                  PIC S9(9) BINARY.                            
```
Replacement:
```cobol
       01  ABCODE                  PIC S9(8) BINARY.
```

The recorded compiler LENGTH probe confirms this isolated binary item remains in the same GnuCOBOL storage-size class (9/8digits:4bytes;4/3digits:2bytes). All assignments are small integers (APPL-RESULT0/8/12/16, ABCODE999, TIMING0, parameter length10), representable in both pictures. It has no arithmetic range-dependent use or changed external field offset; by-reference ABI and numeric comparisons are preserved. This argument is for the pinned host compiler, not z/OS equivalence.

Supporting source lines: [138]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-size-139-23

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 139-139; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
       01  TIMING                  PIC S9(9) BINARY.                            
```
Replacement:
```cobol
       01  TIMING                  PIC S9(8) BINARY.
```

The recorded compiler LENGTH probe confirms this isolated binary item remains in the same GnuCOBOL storage-size class (9/8digits:4bytes;4/3digits:2bytes). All assignments are small integers (APPL-RESULT0/8/12/16, ABCODE999, TIMING0, parameter length10), representable in both pictures. It has no arithmetic range-dependent use or changed external field offset; by-reference ABI and numeric comparisons are preserved. This argument is for the pinned host compiler, not z/OS equivalence.

Supporting source lines: [139]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-receiving-size-172-31

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 172-172; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
           05 WS-RECORD-COUNT           PIC 9(09) VALUE 0.                      
```
Replacement:
```cobol
       05 WS-RECORD-COUNT           PIC 9(8) VALUE 0.
```

WS-RECORD-COUNT is a standalone working-storage counter whose only use is ADD1 to itself. It is never read by a condition, output, display, alias or external parameter. Size/scale/increment/deletion changes cannot affect observable program behavior.

Supporting source lines: [172, 192]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-skip-PERFORM-216-74

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 216-216; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
                       PERFORM 1400-COMPUTE-FEES                                
```
Replacement:
```cobol
       CONTINUE
```

The performed 1400-COMPUTE-FEES paragraph consists solely of EXIT and no executable side effect. Replacing that PERFORM with CONTINUE leaves state and control flow unchanged.

Supporting source lines: [216, 518, 520]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBACT04C-skip-PERFORM-220-75

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 220-220; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: evidence-gap.

Original:
```cobol
                    PERFORM 1050-UPDATE-ACCOUNT                                 
```
Replacement:
```cobol
       CONTINUE
```

END-OF-FILE startsN and its only assignment isY. The enclosing TEST BEFORE UNTIL rejectsY, so the first IF always seesN. This PERFORM is in that first IF ELSE and is unreachable in the pinned source, including declared I/O faults. Its deletion is equivalent; this does not repair the original missing final-account update.

Supporting source lines: [137, 188, 189, 220, 340]. Register dependencies: [{'entry_sha256': 'f3cbe2093fd1403894073099fd70e5f5ea3c24b86d116158a99c29293d57f184', 'id': 'CBACT04C-FINAL-ACCOUNT-EOF-ELSE', 'required_disposition': 'keep-by-default'}].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

## POSTTRAN: 17 individual arguments

### CBTRN02C-CVACT03Y-receiving-scale-7-4

Source: `spec/mainframe/copybooks/CVACT03Y.cpy` lines 7-7; SHA-256 `ffc6079e09b28739e154bf6c1e1c36d408209faa91f6cf7008078dc596a1c370`.

Historical status: survived. Historical individual acceptance: False. Fresh disposition: survived.

Original:
```cobol
           05  XREF-ACCT-ID                      PIC 9(11).                     
```
Replacement:
```cobol
       05  XREF-ACCT-ID                      PIC 9(11)V9(1).
```

The receiving account item extends from11 integer bytes to11 integer plus1 fractional byte. READ INTO preserves the first11 bytes; the extra byte comes from following unused filler. Every consumer is a numeric MOVE to an unsigned11-digit integer at394,469,505. The XREF group/filler has no external consumer. In the exact pinned runtime, cob_move_display_to_display invokes store_common_region with source size12/scale1 and target size11/scale0: lf1=-1,lf2=0,hf1=hf2=11,lcf=0,gcf=11,csize=11,p=source,q=target. It copies exactly the first11 bytes without examining the fractional byte. All declared decimal account IDs and any filler byte therefore preserve keys/output IDs. This mutation does not alter the FD/index layout.

Supporting source lines: [383, 394, 469, 505]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-constant-717-443

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 717-717; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
               MOVE IO-STAT1 TO IO-STATUS-04(1:1)                               
```
Replacement:
```cobol
       MOVE IO-STAT1 TO IO-STATUS-04(1:2)
```

The only additional write is padding destination byte2 with a space. Before any display/read of IO-STATUS-04, the unchanged MOVE TWO-BYTES-BINARY TO IO-STATUS-0403 overwrites bytes2-4 completely. Byte1 is unchanged and intermediate operations access only the separate TWO-BYTES item. Thus the extra destination byte is a dead store for every status byte value.

Supporting source lines: [717, 718, 719, 720, 721]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-constant-718-445

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 718-718; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: True. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
               MOVE 0        TO TWO-BYTES-BINARY                                
```
Replacement:
```cobol
       MOVE -1        TO TWO-BYTES-BINARY
```

The pinned compiler exhaustively tested every256 possible right-byte value: both unsigned initializers+1 and-1 followed by the unchanged right-byte write matched initializer0 (512 equalities). The left byte and final numeric/display value are thus identical for the full byte domain, not merely the declared fault statuses.

Supporting source lines: [718]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-constant-718-446

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 718-718; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
               MOVE 0        TO TWO-BYTES-BINARY                                
```
Replacement:
```cobol
       MOVE 1        TO TWO-BYTES-BINARY
```

The pinned compiler exhaustively tested every256 possible right-byte value: both unsigned initializers+1 and-1 followed by the unchanged right-byte write matched initializer0 (512 equalities). The left byte and final numeric/display value are thus identical for the full byte domain, not merely the declared fault statuses.

Supporting source lines: [718]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-delete-MOVE-209-47

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 209-209; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: survived. Historical individual acceptance: False. Fresh disposition: survived.

Original:
```cobol
                     MOVE SPACES TO WS-VALIDATION-FAIL-REASON-DESC              
```
Replacement:
```cobol
       CONTINUE
```

The only external description read is the whole80-byte WS-VALIDATION-TRAILER copied to a reject record at448. That path is selected only by nonzero validation reason after1500-VALIDATE-TRAN. Every validation failure100/101/102/103 first assigns a complete space-padded literal to the76-byte description. Successful validation never takes the reject path. Later posting failure109 occurs after the reject-versus-post choice; its description is never consumed before the next iteration resets validation. Deleting the initial spaces assignment therefore changes no consumed byte, including multiple records, without assuming initial storage.

Supporting source lines: [180, 181, 182, 208, 209, 210, 211, 212, 213, 214, 215, 370, 372, 385, 386, 387, 397, 398, 399, 410, 411, 412, 417, 418, 419, 440, 441, 442, 448, 556, 557, 558]. Register dependencies: [{'entry_sha256': '3e594ded713e215d42eab988ea80be98bdaf0dbd1d6856feae54d09b04e05ffa', 'id': 'REWRITE-109', 'required_disposition': 'keep-by-default'}].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-delete-MOVE-557-314

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 557-558; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: survived. Historical individual acceptance: False. Fresh disposition: survived.

Original:
```cobol
                MOVE 'ACCOUNT RECORD NOT FOUND'                                 
                  TO WS-VALIDATION-FAIL-REASON-DESC                             
```
Replacement:
```cobol
       CONTINUE
```

The account REWRITE INVALID KEY branch assigns this description after the main loop already selected posting at211/212. The posting paragraph returns from2800, performs2900 and exits. No branch to2500-WRITE-REJECT-REC follows. The next loop either ends or resets the numeric reason before validation; every later rejecting validation overwrites the entire description. Thus the557 assignment has no consumer and is a dead store. The original reason109 failure-propagation gap (observed RC0) remains unresolved and is not repaired or accepted by this argument.

Supporting source lines: [208, 209, 210, 211, 212, 215, 219, 440, 441, 442, 444, 448, 554, 555, 556, 557, 558, 559, 560]. Register dependencies: [{'entry_sha256': '3e594ded713e215d42eab988ea80be98bdaf0dbd1d6856feae54d09b04e05ffa', 'id': 'REWRITE-109', 'required_disposition': 'keep-by-default'}].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-delete-MOVE-709-434

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 709-709; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
           MOVE 0 TO TIMING                                                     
```
Replacement:
```cobol
       CONTINUE
```

The pinned compiler probe records initial TIMING0. The only assignment is MOVE0 and the only read is the one terminal host CEE3ABD call; that shim stops the process. Deleting this zero assignment cannot expose another value in this one-invocation execution contract.

Supporting source lines: [709]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-delete-MOVE-718-447

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 718-718; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: True. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
               MOVE 0        TO TWO-BYTES-BINARY                                
```
Replacement:
```cobol
       CONTINUE
```

The pinned compiler probe confirms this unsigned binary item initially has numeric0. Its only other writer overwrites the right byte before every read; the left byte is never changed. The unchanged whole-item zero assignment only re-zeroes that already-zero left byte, while the following right-byte write replaces the other byte. Induction over all calls preserves both final bytes for the entire256-byte input domain.

Supporting source lines: [718]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-delete-MOVE-723-450

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 723-723; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
               MOVE '0000' TO IO-STATUS-04                                      
```
Replacement:
```cobol
       CONTINUE
```

IO-STATUS-04 consists of PIC9 VALUE0 followed by PIC999 VALUE0, so its initial four bytes are0000. In this numeric-status branch, the following MOVE overwrites bytes3-4. Bytes1-2 remain their initial00. Every call is on an error path immediately followed by the terminating host CEE3ABD shim; there is no subsequent invocation with a previously formatted nonnumeric status. Thus this single deletion preserves all displayed bytes under the recorded one-invocation host contract, not an arbitrary returning abend implementation.

Supporting source lines: [138, 139, 140, 723, 724, 725, 711]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-receiving-scale-142-14

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 142-142; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
       01  APPL-RESULT             PIC S9(9)   COMP.                            
```
Replacement:
```cobol
       01  APPL-RESULT             PIC S9(9)V9(1)   COMP.
```

APPL-RESULT has only integral0/8/12/16 assignments and numeric0/16 condition-name consumers. Adding one fractional digit preserves all those exactly; it is not displayed, aliased or passed externally. Physical storage change is unobservable to this program.

Supporting source lines: [142]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-receiving-scale-148-18

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 148-148; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
       01  TIMING                  PIC S9(9) BINARY.                            
```
Replacement:
```cobol
       01  TIMING                  PIC S9(9)V9(1) BINARY.
```

TIMING has a sole integral assignment0 immediately before its only external read. The pinned compiler records the original and scaled binary storage as4/8 bytes; binary zero consists entirely of zero bytes, so the terminating host shim reading its declared4-byte parameter still receives0. No other field offset or raw group is consumed. This is scoped to the recorded host ABI, not native z/OS.

Supporting source lines: [148]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-receiving-scale-173-20

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 173-173; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
           06 DB2-MIL                   PIC 9(002).                             
```
Replacement:
```cobol
       06 DB2-MIL                   PIC 9(002)V9(1).
```

DB2-MIL receives an integral two-digit COB-MIL. Adding one fractional picture digit appends a stored zero. The immediately following DB2-REST is assigned four literal zeros. The whole timestamp is moved into fixed26-character transaction fields, so the new27-character group loses only its final zero. Every copied byte remains identical for every two-digit millisecond input; no numeric field offset is consumed externally.

Supporting source lines: [173]. Register dependencies: [].

Targeted valid/scheduled: 2/200. Outcomes: {'baseline-refusal': 198, 'survived': 2}. Evidence gaps: 198.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-receiving-scale-187-28

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 187-187; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
           05 WS-TEMP-BAL                   PIC S9(09)V99.                      
```
Replacement:
```cobol
       05 WS-TEMP-BAL                   PIC S9(09)V9(3).
```

The accumulator receives only sums/differences of source amounts already quantized to cents, with the same integer range. An added fractional digit or ROUNDED on this exact cent-valued sum cannot change its value or overflow condition. Its consumers are numeric assignment/comparison, never raw storage output.

Supporting source lines: [187]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-receiving-size-134-7

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 134-134; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
       01  TWO-BYTES-BINARY        PIC 9(4) BINARY.                             
```
Replacement:
```cobol
       01  TWO-BYTES-BINARY        PIC 9(3) BINARY.
```

The pinned compiler probe records both unsigned9(4) and9(3) as2-byte storage. Every possible second status byte is exercised (256 values); after the unchanged zero-and-right-byte writes, the largest numeric value is255, fitting both pictures. The same byte representation/offset and every representable use are preserved.

Supporting source lines: [134]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-receiving-size-147-15

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 147-147; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
       01  ABCODE                  PIC S9(9) BINARY.                            
```
Replacement:
```cobol
       01  ABCODE                  PIC S9(8) BINARY.
```

The recorded compiler LENGTH probe confirms this isolated binary item remains in the same GnuCOBOL storage-size class (9/8digits:4bytes;4/3digits:2bytes). All assignments are small integers (APPL-RESULT0/8/12/16, ABCODE999, TIMING0, parameter length10), representable in both pictures. It has no arithmetic range-dependent use or changed external field offset; by-reference ABI and numeric comparisons are preserved. This argument is for the pinned host compiler, not z/OS equivalence.

Supporting source lines: [147]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-receiving-size-148-17

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 148-148; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
       01  TIMING                  PIC S9(9) BINARY.                            
```
Replacement:
```cobol
       01  TIMING                  PIC S9(8) BINARY.
```

The recorded compiler LENGTH probe confirms this isolated binary item remains in the same GnuCOBOL storage-size class (9/8digits:4bytes;4/3digits:2bytes). All assignments are small integers (APPL-RESULT0/8/12/16, ABCODE999, TIMING0, parameter length10), representable in both pictures. It has no arithmetic range-dependent use or changed external field offset; by-reference ABI and numeric comparisons are preserved. This argument is for the pinned host compiler, not z/OS equivalence.

Supporting source lines: [148]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________

### CBTRN02C-rounded-403-196

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 403-403; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed). Historical individual acceptance: False. Fresh disposition: equivalent (argued, listed).

Original:
```cobol
                COMPUTE WS-TEMP-BAL = ACCT-CURR-CYC-CREDIT                      
```
Replacement:
```cobol
       COMPUTE WS-TEMP-BAL ROUNDED = ACCT-CURR-CYC-CREDIT
```

WS-TEMP-BAL sums/differences three two-decimal source amounts. The exact result is cent-valued, so ROUNDED to the existing two-decimal target cannot change the result or integer overflow.

Supporting source lines: [403]. Register dependencies: [].

Targeted valid/scheduled: 200/200. Outcomes: {'survived': 200}. Evidence gaps: 0.

Independent finding: **pending**. Reviewer / date / reasons: ____________________
Howard decision (accept / reject / needs-evidence), scope / reason / date: ____________________
