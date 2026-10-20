# INTCALC ordered class: unsigned 30-member review

Prepared 2026-10-20 from retained metadata. Review incomplete; no signature, import, execution authority or qualification credit.

Selected contract: `docs/factory/intcalc-02-appl-result-class-request-2026-10-17.json`
Template queue SHA-256: `550f6ed38a9e8863b959b294af3c61cc91c97f11eff17e324a3476d39bed237e`
Ordered census seal: `e054defd96b168cc73a154fec1492f96c001c91f8c277737c3db78d08ae584a8`

All 81 members and exact provenance are bound in the companion JSON. Thirty members were selected without replacement using its stated deterministic method. The numbered source context is shared below to avoid duplicating the same lines. Historical review does not transfer to this packet.

## 1. CBACT04C-constant-565-324

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 2. CBACT04C-constant-601-354

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 3. CBACT04C-constant-596-346

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Source context lines: 596, 597, 598, 599, 600, 601, 602, 603.

## 4. CBACT04C-constant-547-309

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 5. CBACT04C-constant-258-105

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 6. CBACT04C-constant-313-150

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 7. CBACT04C-constant-601-353

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 8. CBACT04C-delete-MOVE-295-136

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Source context lines: 290, 291, 292, 293, 294, 295.

## 9. CBACT04C-constant-578-331

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Source context lines: 578, 579, 580, 581, 582, 583, 584, 585.

## 10. CBACT04C-delete-MOVE-308-143

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       CONTINUE.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Source context lines: 308, 309, 310, 311, 312, 313, 314, 315.

## 11. CBACT04C-constant-276-119

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 12. CBACT04C-delete-MOVE-502-277

Original:
```cobol
               MOVE 0 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

Source context lines: 182, 186, 188, 190, 191, 197, 203, 205, 213, 215, 220, 224, 328, 331, 333, 340, 423, 435, 438, 447, 502, 632.

## 13. CBACT04C-constant-542-301

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Source context lines: 542, 543, 544, 545, 546, 547, 548, 549.

## 14. CBACT04C-constant-271-112

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Source context lines: 271, 272, 273, 274, 275, 276, 277, 278.

## 15. CBACT04C-constant-381-200

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 16. CBACT04C-delete-MOVE-313-151

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Source context lines: 308, 309, 310, 311, 312, 313.

## 17. CBACT04C-constant-295-134

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 18. CBACT04C-constant-596-345

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       MOVE 7 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Source context lines: 596, 597, 598, 599, 600, 601, 602, 603.

## 19. CBACT04C-delete-MOVE-447-239

Original:
```cobol
               MOVE 0 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

Source context lines: 182, 186, 188, 190, 191, 197, 203, 205, 213, 215, 220, 224, 328, 331, 333, 340, 423, 435, 438, 447, 632.

## 20. CBACT04C-constant-583-339

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 21. CBACT04C-constant-333-166

Original:
```cobol
                   MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 22. CBACT04C-delete-MOVE-379-199

Original:
```cobol
               MOVE 0 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

Source context lines: 182, 186, 188, 190, 191, 197, 203, 205, 213, 215, 220, 224, 328, 331, 333, 340, 379, 423, 435, 438, 447, 632.

## 23. CBACT04C-constant-523-285

Original:
```cobol
           MOVE 8 TO  APPL-RESULT.
```
Replacement:
```cobol
       MOVE 7 TO  APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Source context lines: 523, 524, 525, 526, 527, 528, 529, 530.

## 24. CBACT04C-delete-MOVE-601-355

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Source context lines: 596, 597, 598, 599, 600, 601.

## 25. CBACT04C-delete-MOVE-258-106

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Source context lines: 253, 254, 255, 256, 257, 258.

## 26. CBACT04C-constant-295-135

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 27. CBACT04C-delete-MOVE-276-121

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Source context lines: 271, 272, 273, 274, 275, 276.

## 28. CBACT04C-constant-528-294

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 29. CBACT04C-constant-258-104

Original:
```cobol
               MOVE 12 TO APPL-RESULT
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Source context lines: 133, 134, 135, 235, 238, 240, 253, 256, 258, 271, 274, 276, 290, 293, 295, 308, 311, 313, 328, 331, 333, 358, 360, 379, 381, 401, 403, 423, 425, 447, 449, 502, 504, 523, 526, 528, 542, 545, 547, 560, 563, 565, 578, 581, 583, 596, 599, 601.

## 30. CBACT04C-delete-MOVE-560-317

Original:
```cobol
           MOVE 8 TO APPL-RESULT.
```
Replacement:
```cobol
       CONTINUE.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Source context lines: 560, 561, 562, 563, 564, 565, 566, 567.

## Numbered source context

```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.
134:            88  APPL-AOK            VALUE 0.
135:            88  APPL-EOF            VALUE 16.
182:            PERFORM 0000-TCATBALF-OPEN.
186:            PERFORM 0400-TRANFILE-OPEN.
188:            PERFORM UNTIL END-OF-FILE = 'Y'
190:                    PERFORM 1000-TCATBALF-GET-NEXT
191:                    IF  END-OF-FILE = 'N'
197:                        ELSE
203:                        PERFORM 1100-GET-ACCT-DATA
205:                        PERFORM 1110-GET-XREF-DATA
213:                      PERFORM 1200-GET-INTEREST-RATE
215:                        PERFORM 1300-COMPUTE-INTEREST
220:                     PERFORM 1050-UPDATE-ACCOUNT
224:            PERFORM 9000-TCATBALF-CLOSE.
235:            MOVE 8 TO APPL-RESULT.
238:                MOVE 0 TO APPL-RESULT
240:                MOVE 12 TO APPL-RESULT
253:            MOVE 8 TO APPL-RESULT.
254:            OPEN INPUT XREF-FILE
255:            IF  XREFFILE-STATUS = '00'
256:                MOVE 0 TO APPL-RESULT
257:            ELSE
258:                MOVE 12 TO APPL-RESULT
271:            MOVE 8 TO APPL-RESULT.
272:            OPEN INPUT DISCGRP-FILE
273:            IF  DISCGRP-STATUS = '00'
274:                MOVE 0 TO APPL-RESULT
275:            ELSE
276:                MOVE 12 TO APPL-RESULT
277:            END-IF
278:            IF  APPL-AOK
290:            MOVE 8 TO APPL-RESULT.
291:            OPEN I-O ACCOUNT-FILE
292:            IF  ACCTFILE-STATUS = '00'
293:                MOVE 0 TO APPL-RESULT
294:            ELSE
295:                MOVE 12 TO APPL-RESULT
308:            MOVE 8 TO APPL-RESULT.
309:            OPEN OUTPUT TRANSACT-FILE
310:            IF  TRANFILE-STATUS = '00'
311:                MOVE 0 TO APPL-RESULT
312:            ELSE
313:                MOVE 12 TO APPL-RESULT
314:            END-IF
315:            IF  APPL-AOK
328:                MOVE 0 TO APPL-RESULT
331:                    MOVE 16 TO APPL-RESULT
333:                    MOVE 12 TO APPL-RESULT
340:                    MOVE 'Y' TO END-OF-FILE
358:                MOVE 0 TO APPL-RESULT
360:                MOVE 12 TO APPL-RESULT
379:                MOVE 0 TO APPL-RESULT
381:                MOVE 12 TO APPL-RESULT
401:                MOVE 0 TO APPL-RESULT
403:                MOVE 12 TO APPL-RESULT
423:                MOVE 0 TO APPL-RESULT
425:                MOVE 12 TO APPL-RESULT
435:            END-IF
438:                PERFORM 1200-A-GET-DEFAULT-INT-RATE
447:                MOVE 0 TO APPL-RESULT
449:                MOVE 12 TO APPL-RESULT
502:                MOVE 0 TO APPL-RESULT
504:                MOVE 12 TO APPL-RESULT
523:            MOVE 8 TO  APPL-RESULT.
524:            CLOSE TCATBAL-FILE
525:            IF  TCATBALF-STATUS = '00'
526:                MOVE 0 TO  APPL-RESULT
527:            ELSE
528:                MOVE 12 TO APPL-RESULT
529:            END-IF
530:            IF  APPL-AOK
542:            MOVE 8 TO APPL-RESULT.
543:            CLOSE XREF-FILE
544:            IF  XREFFILE-STATUS = '00'
545:                MOVE 0 TO APPL-RESULT
546:            ELSE
547:                MOVE 12 TO APPL-RESULT
548:            END-IF
549:            IF  APPL-AOK
560:            MOVE 8 TO APPL-RESULT.
561:            CLOSE DISCGRP-FILE
562:            IF  DISCGRP-STATUS = '00'
563:                MOVE 0 TO APPL-RESULT
564:            ELSE
565:                MOVE 12 TO APPL-RESULT
566:            END-IF
567:            IF  APPL-AOK
578:            MOVE 8 TO APPL-RESULT.
579:            CLOSE ACCOUNT-FILE
580:            IF  ACCTFILE-STATUS  = '00'
581:                MOVE 0 TO APPL-RESULT
582:            ELSE
583:                MOVE 12 TO APPL-RESULT
584:            END-IF
585:            IF  APPL-AOK
596:            MOVE 8 TO APPL-RESULT.
597:            CLOSE TRANSACT-FILE
598:            IF  TRANFILE-STATUS  = '00'
599:                MOVE 0 TO APPL-RESULT
600:            ELSE
601:                MOVE 12 TO APPL-RESULT
602:            END-IF
603:            IF  APPL-AOK
632:            CALL 'CEE3ABD' USING ABCODE, TIMING.
```

Before signing, review the exact selected contract and predecessor decision binding through the ordered signing process. This packet does not authorize those actions.
