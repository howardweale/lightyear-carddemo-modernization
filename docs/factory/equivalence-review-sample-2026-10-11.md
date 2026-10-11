# Independent review: 20 argued-equivalent mutants

Howard requested this review on 2026-10-11. Ten mutants per program were drawn from the complete listed argument population. Selection was not rerolled. Review findings are pending; scenario-threshold/2 remains unapproved.

Seed: `Howard-2026-10-11-equivalence-review-20-v1`. Algorithm: Lowest ten SHA-256(seed + NUL + program + NUL + mutant ID), ID tie-break; without replacement from all listed arguments.

Review each argument against the pinned source and runtime scope. Record accept/reject/needs-evidence, reviewer, date and reasons. Acceptance of EOF exceptions or legacy behavior does not approve these equivalence arguments.

## INTCALC: 10 of 113

Population SHA-256: `86e8f54c59db20247a42e836a6deea09d02fbe1871b813caa002b7616c8f2397`

### CBACT04C-constant-403-212

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 403-403; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Supporting source lines: [133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBACT04C-delete-MOVE-601-355

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 601-601; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Supporting source lines: [596, 597, 598, 599, 600, 601].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBACT04C-delete-ADD-192-50

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 192-192; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
                     ADD 1 TO WS-RECORD-COUNT
```
Replacement:
```cobol
       CONTINUE
```

WS-RECORD-COUNT is a standalone working-storage counter whose only use is ADD1 to itself. It is never read by a condition, output, display, alias or external parameter. Size/scale/increment/deletion changes cannot affect observable program behavior.

Supporting source lines: [172, 192].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBACT04C-delete-MOVE-401-211

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 401-401; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 0 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

Supporting source lines: [182, 186, 188, 190, 191, 197, 203, 205, 213, 215, 220, 224, 328, 331, 333, 340, 423, 435, 438, 447, 632].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBACT04C-receiving-size-133-19

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 133-133; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
       01  APPL-RESULT             PIC S9(9)   COMP.
```
Replacement:
```cobol
       01  APPL-RESULT             PIC S9(8)   COMP.
```

The recorded compiler LENGTH probe confirms this isolated binary item remains in the same GnuCOBOL storage-size class (9/8digits:4bytes;4/3digits:2bytes). All assignments are small integers (APPL-RESULT0/8/12/16, ABCODE999, TIMING0, parameter length10), representable in both pictures. It has no arithmetic range-dependent use or changed external field offset; by-reference ABI and numeric comparisons are preserved. This argument is for the pinned host compiler, not z/OS equivalence.

Supporting source lines: [133].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBACT04C-constant-523-286

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 523-523; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
           MOVE 8 TO  APPL-RESULT.
```
Replacement:
```cobol
       MOVE 9 TO  APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Supporting source lines: [523, 524, 525, 526, 527, 528, 529, 530].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBACT04C-delete-MOVE-502-277

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 502-502; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 0 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

Supporting source lines: [182, 186, 188, 190, 191, 197, 203, 205, 213, 215, 220, 224, 328, 331, 333, 340, 423, 435, 438, 447, 632].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBACT04C-delete-MOVE-290-128

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 290-290; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       CONTINUE.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Supporting source lines: [290, 291, 292, 293, 294, 295, 296, 297].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBACT04C-constant-235-81

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 235-235; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       MOVE 7 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Supporting source lines: [235, 236, 237, 238, 239, 240, 241, 242].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBACT04C-delete-MOVE-240-91

Source: `spec/mainframe/public-source/CBACT04C.cbl` lines 240-240; SHA-256 `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Supporting source lines: [235, 236, 237, 238, 239, 240].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

## POSTTRAN: 10 of 114

Population SHA-256: `c6369d761dbf2c9894df7251126145c9e3e06ae6a5edbcf7abcb1bef6d65ee3b`

### CBTRN02C-constant-583-332

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 583-583; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
           MOVE 8 TO  APPL-RESULT.
```
Replacement:
```cobol
       MOVE 9 TO  APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Supporting source lines: [583, 584, 585, 586, 587, 588, 589, 590].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBTRN02C-delete-MOVE-718-447

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 718-718; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 0        TO TWO-BYTES-BINARY
```
Replacement:
```cobol
       CONTINUE
```

The pinned compiler probe confirms this unsigned binary item initially has numeric0. Its only other writer overwrites the right byte before every read; the left byte is never changed. The unchanged whole-item zero assignment only re-zeroes that already-zero left byte, while the following right-byte write replaces the other byte. Induction over all calls preserves both final bytes for the entire256-byte input domain.

Supporting source lines: [718].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBTRN02C-constant-638-377

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 638-638; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Supporting source lines: [638, 639, 640, 641, 642, 643, 644, 645].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBTRN02C-constant-515-283

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 515-515; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Supporting source lines: [142, 143, 144, 237, 240, 242, 255, 258, 260, 274, 277, 279, 292, 295, 297, 310, 313, 315, 328, 331, 333, 348, 352, 354, 450, 453, 455, 482, 484, 513, 515, 531, 533, 563, 567, 569, 583, 586, 588, 601, 604, 606, 620, 623, 625, 638, 641, 643, 656, 659, 661, 675, 678, 680].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBTRN02C-constant-255-87

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 255-255; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Supporting source lines: [255, 256, 257, 258, 259, 260, 261, 262].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBTRN02C-constant-515-282

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 515-515; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Supporting source lines: [142, 143, 144, 237, 240, 242, 255, 258, 260, 274, 277, 279, 292, 295, 297, 310, 313, 315, 328, 331, 333, 348, 352, 354, 450, 453, 455, 482, 484, 513, 515, 531, 533, 563, 567, 569, 583, 586, 588, 601, 604, 606, 620, 623, 625, 638, 641, 643, 656, 659, 661, 675, 678, 680].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBTRN02C-delete-MOVE-455-246

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 455-455; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Supporting source lines: [450, 451, 452, 453, 454, 455].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBTRN02C-constant-680-414

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 680-680; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Supporting source lines: [142, 143, 144, 237, 240, 242, 255, 258, 260, 274, 277, 279, 292, 295, 297, 310, 313, 315, 328, 331, 333, 348, 352, 354, 450, 453, 455, 482, 484, 513, 515, 531, 533, 563, 567, 569, 583, 586, 588, 601, 604, 606, 620, 623, 625, 638, 641, 643, 656, 659, 661, 675, 678, 680].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBTRN02C-constant-588-339

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 588-588; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Supporting source lines: [142, 143, 144, 237, 240, 242, 255, 258, 260, 274, 277, 279, 292, 295, 297, 310, 313, 315, 328, 331, 333, 348, 352, 354, 450, 453, 455, 482, 484, 513, 515, 531, 533, 563, 567, 569, 583, 586, 588, 601, 604, 606, 620, 623, 625, 638, 641, 643, 656, 659, 661, 675, 678, 680].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

### CBTRN02C-constant-718-445

Source: `spec/mainframe/public-source/CBTRN02C.cbl` lines 718-718; SHA-256 `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`.

Historical status: equivalent (argued, listed); argument origin: inline.

Original:
```cobol
               MOVE 0        TO TWO-BYTES-BINARY
```
Replacement:
```cobol
       MOVE -1        TO TWO-BYTES-BINARY
```

The pinned compiler exhaustively tested every256 possible right-byte value: both unsigned initializers+1 and-1 followed by the unchanged right-byte write matched initializer0 (512 equalities). The left byte and final numeric/display value are thus identical for the full byte domain, not merely the declared fault statuses.

Supporting source lines: [718].

Independent finding: **pending**. Reviewer / date / reasons: ____________________

Machine-readable packet: [equivalence-review-sample-2026-10-11.json](equivalence-review-sample-2026-10-11.json). It includes all population IDs, input hashes, full arguments and raw-record hashes.
