# INTCALC M1 survivor triage — 23 October 2026

**Triage complete for the retained pinned twin contract; M1 campaign work remains unfinished.**

All 113 sites are classified `equivalent` within the explicitly bounded host contract below. They remain survivors: **311/424 (73.35%)**, not 424/424. The 90% bar requires 382 kills, or 71 additional kills. This review does not provide those kills, change the denominator, or authorize release.

These are source/runtime arguments, not a claim that 200 surviving cases prove equivalence. The retained 30 individually targeted sites each survived 200 cases (6,000 total); the 81 APPL-RESULT class members have no raw-value consumer; two further sites have identical fresh compiler-generated C under the retained normalization. Every mutation is listed below, and its complete argument and exact source/record hashes are in [the JSON record](intcalc-m1-triage-2026-10-23.json).

Scope: pinned GnuCOBOL twin, approved loader inputs and declared fault seams, one invocation with a terminating CEE3ABD shim. Storage and alternate-index arguments retain their explicit compiler/runtime restrictions. Malformed databases, other runtimes and native z/OS are outside this claim. Any contradictory witness must invalidate the affected classification, while retaining the raw record.

| Category | Count |
|---|---:|
| equivalent | 113 |
| missing-scenario | 0 |
| timeout | 0 |
| error | 0 |

| Paragraph / declaration area | Equivalent survivors |
|---|---:|
| 0000-TCATBALF-OPEN | 6 |
| 0100-XREFFILE-OPEN | 6 |
| 0200-DISCGRP-OPEN | 6 |
| 0300-ACCTFILE-OPEN | 6 |
| 0400-TRANFILE-OPEN | 6 |
| 1000-TCATBALF-GET-NEXT | 3 |
| 1050-UPDATE-ACCOUNT | 3 |
| 1100-GET-ACCT-DATA | 3 |
| 1110-GET-XREF-DATA | 3 |
| 1200-A-GET-DEFAULT-INT-RATE | 3 |
| 1200-GET-INTEREST-RATE | 3 |
| 1300-B-WRITE-TX | 7 |
| 9000-TCATBALF-CLOSE | 6 |
| 9100-XREFFILE-CLOSE | 6 |
| 9200-DISCGRP-CLOSE | 6 |
| 9300-ACCTFILE-CLOSE | 6 |
| 9400-TRANFILE-CLOSE | 6 |
| 9910-DISPLAY-IO-STATUS | 5 |
| 9999-ABEND-PROGRAM | 1 |
| FILE SECTION | 1 |
| LINKAGE SECTION | 1 |
| PROCEDURE entry | 5 |
| WORKING-STORAGE | 11 |
| copybook data declaration | 4 |

No `missing-scenario` site was identified in this scoped triage, so no separating witness is invented. The source-derived edge scenarios and a new CI development campaign remain required. They can challenge these arguments and improve behavior coverage, but cannot be represented as 71 expected kills. No release campaign, real signature or native measurement was performed.

## Written arguments

### A01

INTCALC reads this copybook group via READ INTO and consumes only its first16-character XREF-CARD-NUM. The mutated customer/account receiving items follow those16 bytes and are never referenced or passed/output as a group. Key lookup uses the distinct unchanged FD fields. Changing this receiving suffix size/scale may truncate/pad unused bytes but preserves every consumed byte. This excludes FD key-layout mutations.

### A02

WS-RECORD-COUNT is a standalone working-storage counter whose only use is ADD1 to itself. It is never read by a condition, output, display, alias or external parameter. Size/scale/increment/deletion changes cannot affect observable program behavior.

### A03

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

### A04

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

### A05

The only additional write is padding destination byte2 with a space. Before any display/read of IO-STATUS-04, the unchanged MOVE TWO-BYTES-BINARY TO IO-STATUS-0403 overwrites bytes2-4 completely. Byte1 is unchanged and intermediate operations access only the separate TWO-BYTES item. Thus the extra destination byte is a dead store for every status byte value.

### A06

The pinned compiler exhaustively tested every256 possible right-byte value: both unsigned initializers+1 and-1 followed by the unchanged right-byte write matched initializer0 (512 equalities). The left byte and final numeric/display value are thus identical for the full byte domain, not merely the declared fault statuses.

### A07

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

### A08

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

### A09

The pinned compiler probe confirms initial numeric storage0 and alphanumeric storage spaces. These four working-storage merchant fields have no other writer/alias or group initialization; each transaction only writes the same0/spaces before output. By induction all records preserve those values when this single redundant assignment is deleted. Scoped to this recorded one-invocation host runtime; no implicit z/OS equivalence.

### A10

The pinned compiler probe records initial TIMING0. The only assignment is MOVE0 and the only read is the one terminal host CEE3ABD call; that shim stops the process. Deleting this zero assignment cannot expose another value in this one-invocation execution contract.

### A11

The pinned compiler probe confirms this unsigned binary item initially has numeric0. Its only other writer overwrites the right byte before every read; the left byte is never changed. The unchanged whole-item zero assignment only re-zeroes that already-zero left byte, while the following right-byte write replaces the other byte. Induction over all calls preserves both final bytes for the entire256-byte input domain.

### A12

IO-STATUS-04 consists of PIC9 VALUE0 followed by PIC999 VALUE0, so its initial four bytes are0000. In this numeric-status branch, the following MOVE overwrites bytes3-4. Bytes1-2 remain their initial00. Every call is on an error path immediately followed by the terminating host CEE3ABD shim; there is no subsequent invocation with a previously formatted nonnumeric status. Thus this single deletion preserves all displayed bytes under the recorded one-invocation host contract, not an arbitrary returning abend implementation.

### A13

APPL-RESULT has only integral0/8/12/16 assignments and numeric0/16 condition-name consumers. Adding one fractional digit preserves all those exactly; it is not displayed, aliased or passed externally. Physical storage change is unobservable to this program.

### A14

TIMING has a sole integral assignment0 immediately before its only external read. The pinned compiler records the original and scaled binary storage as4/8 bytes; binary zero consists entirely of zero bytes, so the terminating host shim reading its declared4-byte parameter still receives0. No other field offset or raw group is consumed. This is scoped to the recorded host ABI, not native z/OS.

### A15

DB2-MIL receives an integral two-digit COB-MIL. Adding one fractional picture digit appends a stored zero. The immediately following DB2-REST is assigned four literal zeros. The whole timestamp is moved into fixed26-character transaction fields, so the new27-character group loses only its final zero. Every copied byte remains identical for every two-digit millisecond input; no numeric field offset is consumed externally.

### A16

The accumulator receives only sums/differences of source amounts already quantized to cents, with the same integer range. An added fractional digit or ROUNDED on this exact cent-valued sum cannot change its value or overflow condition. Its consumers are numeric assignment/comparison, never raw storage output.

### A17

WS-TRANID-SUFFIX starts0 and is incremented by integral1. Its only read is STRING after the10-character parameter date into the16-character transaction ID. The added fractional digit stays0 and becomes the seventeenth character, outside that fixed target. The six integer digits and their overflow range are unchanged; no raw suffix/group consumer exists.

### A18

Pinned Berkeley DB host contract: this unused FD customer field gains one byte, shifting the alternate key buffer but changing neither key ordinal1 nor its11-byte value. GnuCOBOL bdb_findkey matches the current field pointer to ordinal1, bdb_setkey copies that field, and indexed_start_internal searches the existing ordinal1 index. The loader-built record remains50bytes, below both record maxima50/51; indexed_read copies its unchanged50bytes and READ INTO copies them to the unchanged50-byte XREF copybook. Only its16-byte card prefix is consumed. Error lookup displays still use the unchanged11-byte requested account value. No writes use this FD. Thus all valid fixed50-byte twin inputs and declared seams preserve observable behavior. This explicitly excludes malformed database files, different runtimes and z/OS; see the source/runtime argument document.

### A19

The pinned compiler probe records both unsigned9(4) and9(3) as2-byte storage. Every possible second status byte is exercised (256 values); after the unchanged zero-and-right-byte writes, the largest numeric value is255, fitting both pictures. The same byte representation/offset and every representable use are preserved.

### A20

The recorded compiler LENGTH probe confirms this isolated binary item remains in the same GnuCOBOL storage-size class (9/8digits:4bytes;4/3digits:2bytes). All assignments are small integers (APPL-RESULT0/8/12/16, ABCODE999, TIMING0, parameter length10), representable in both pictures. It has no arithmetic range-dependent use or changed external field offset; by-reference ABI and numeric comparisons are preserved. This argument is for the pinned host compiler, not z/OS equivalence.

### A21

The performed 1400-COMPUTE-FEES paragraph consists solely of EXIT and no executable side effect. Replacing that PERFORM with CONTINUE leaves state and control flow unchanged.

### A22

END-OF-FILE startsN and its only assignment isY. The enclosing TEST BEFORE UNTIL rejectsY, so the first IF always seesN. This PERFORM is in that first IF ELSE and is unreachable in the pinned source, including declared I/O faults. Its deletion is equivalent; this does not repair the original missing final-account update.

## Complete site inventory

| Mutant | Source line | Paragraph | Operator | Category | Argument |
|---|---:|---|---|---|---|
| CBACT04C-CVACT03Y-receiving-scale-6-2 | CVACT03Y.cpy:6 | copybook data declaration | receiving-scale | equivalent | A01 |
| CBACT04C-CVACT03Y-receiving-scale-7-4 | CVACT03Y.cpy:7 | copybook data declaration | receiving-scale | equivalent | A01 |
| CBACT04C-CVACT03Y-receiving-size-6-1 | CVACT03Y.cpy:6 | copybook data declaration | receiving-size | equivalent | A01 |
| CBACT04C-CVACT03Y-receiving-size-7-3 | CVACT03Y.cpy:7 | copybook data declaration | receiving-size | equivalent | A01 |
| CBACT04C-constant-192-48 | CBACT04C.cbl:192 | PROCEDURE entry | constant | equivalent | A02 |
| CBACT04C-constant-192-49 | CBACT04C.cbl:192 | PROCEDURE entry | constant | equivalent | A02 |
| CBACT04C-constant-235-81 | CBACT04C.cbl:235 | 0000-TCATBALF-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-235-82 | CBACT04C.cbl:235 | 0000-TCATBALF-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-240-89 | CBACT04C.cbl:240 | 0000-TCATBALF-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-240-90 | CBACT04C.cbl:240 | 0000-TCATBALF-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-253-96 | CBACT04C.cbl:253 | 0100-XREFFILE-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-253-97 | CBACT04C.cbl:253 | 0100-XREFFILE-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-258-104 | CBACT04C.cbl:258 | 0100-XREFFILE-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-258-105 | CBACT04C.cbl:258 | 0100-XREFFILE-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-271-111 | CBACT04C.cbl:271 | 0200-DISCGRP-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-271-112 | CBACT04C.cbl:271 | 0200-DISCGRP-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-276-119 | CBACT04C.cbl:276 | 0200-DISCGRP-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-276-120 | CBACT04C.cbl:276 | 0200-DISCGRP-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-290-126 | CBACT04C.cbl:290 | 0300-ACCTFILE-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-290-127 | CBACT04C.cbl:290 | 0300-ACCTFILE-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-295-134 | CBACT04C.cbl:295 | 0300-ACCTFILE-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-295-135 | CBACT04C.cbl:295 | 0300-ACCTFILE-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-308-141 | CBACT04C.cbl:308 | 0400-TRANFILE-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-308-142 | CBACT04C.cbl:308 | 0400-TRANFILE-OPEN | constant | equivalent | A03 |
| CBACT04C-constant-313-149 | CBACT04C.cbl:313 | 0400-TRANFILE-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-313-150 | CBACT04C.cbl:313 | 0400-TRANFILE-OPEN | constant | equivalent | A04 |
| CBACT04C-constant-333-166 | CBACT04C.cbl:333 | 1000-TCATBALF-GET-NEXT | constant | equivalent | A04 |
| CBACT04C-constant-333-167 | CBACT04C.cbl:333 | 1000-TCATBALF-GET-NEXT | constant | equivalent | A04 |
| CBACT04C-constant-360-188 | CBACT04C.cbl:360 | 1050-UPDATE-ACCOUNT | constant | equivalent | A04 |
| CBACT04C-constant-360-189 | CBACT04C.cbl:360 | 1050-UPDATE-ACCOUNT | constant | equivalent | A04 |
| CBACT04C-constant-381-200 | CBACT04C.cbl:381 | 1100-GET-ACCT-DATA | constant | equivalent | A04 |
| CBACT04C-constant-381-201 | CBACT04C.cbl:381 | 1100-GET-ACCT-DATA | constant | equivalent | A04 |
| CBACT04C-constant-403-212 | CBACT04C.cbl:403 | 1110-GET-XREF-DATA | constant | equivalent | A04 |
| CBACT04C-constant-403-213 | CBACT04C.cbl:403 | 1110-GET-XREF-DATA | constant | equivalent | A04 |
| CBACT04C-constant-425-224 | CBACT04C.cbl:425 | 1200-GET-INTEREST-RATE | constant | equivalent | A04 |
| CBACT04C-constant-425-225 | CBACT04C.cbl:425 | 1200-GET-INTEREST-RATE | constant | equivalent | A04 |
| CBACT04C-constant-449-240 | CBACT04C.cbl:449 | 1200-A-GET-DEFAULT-INT-RATE | constant | equivalent | A04 |
| CBACT04C-constant-449-241 | CBACT04C.cbl:449 | 1200-A-GET-DEFAULT-INT-RATE | constant | equivalent | A04 |
| CBACT04C-constant-504-278 | CBACT04C.cbl:504 | 1300-B-WRITE-TX | constant | equivalent | A04 |
| CBACT04C-constant-504-279 | CBACT04C.cbl:504 | 1300-B-WRITE-TX | constant | equivalent | A04 |
| CBACT04C-constant-523-285 | CBACT04C.cbl:523 | 9000-TCATBALF-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-523-286 | CBACT04C.cbl:523 | 9000-TCATBALF-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-528-293 | CBACT04C.cbl:528 | 9000-TCATBALF-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-528-294 | CBACT04C.cbl:528 | 9000-TCATBALF-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-542-300 | CBACT04C.cbl:542 | 9100-XREFFILE-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-542-301 | CBACT04C.cbl:542 | 9100-XREFFILE-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-547-308 | CBACT04C.cbl:547 | 9100-XREFFILE-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-547-309 | CBACT04C.cbl:547 | 9100-XREFFILE-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-560-315 | CBACT04C.cbl:560 | 9200-DISCGRP-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-560-316 | CBACT04C.cbl:560 | 9200-DISCGRP-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-565-323 | CBACT04C.cbl:565 | 9200-DISCGRP-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-565-324 | CBACT04C.cbl:565 | 9200-DISCGRP-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-578-330 | CBACT04C.cbl:578 | 9300-ACCTFILE-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-578-331 | CBACT04C.cbl:578 | 9300-ACCTFILE-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-583-338 | CBACT04C.cbl:583 | 9300-ACCTFILE-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-583-339 | CBACT04C.cbl:583 | 9300-ACCTFILE-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-596-345 | CBACT04C.cbl:596 | 9400-TRANFILE-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-596-346 | CBACT04C.cbl:596 | 9400-TRANFILE-CLOSE | constant | equivalent | A03 |
| CBACT04C-constant-601-353 | CBACT04C.cbl:601 | 9400-TRANFILE-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-601-354 | CBACT04C.cbl:601 | 9400-TRANFILE-CLOSE | constant | equivalent | A04 |
| CBACT04C-constant-638-382 | CBACT04C.cbl:638 | 9910-DISPLAY-IO-STATUS | constant | equivalent | A05 |
| CBACT04C-constant-639-384 | CBACT04C.cbl:639 | 9910-DISPLAY-IO-STATUS | constant | equivalent | A06 |
| CBACT04C-constant-639-385 | CBACT04C.cbl:639 | 9910-DISPLAY-IO-STATUS | constant | equivalent | A06 |
| CBACT04C-delete-ADD-192-50 | CBACT04C.cbl:192 | PROCEDURE entry | delete-ADD | equivalent | A02 |
| CBACT04C-delete-MOVE-235-83 | CBACT04C.cbl:235 | 0000-TCATBALF-OPEN | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-240-91 | CBACT04C.cbl:240 | 0000-TCATBALF-OPEN | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-253-98 | CBACT04C.cbl:253 | 0100-XREFFILE-OPEN | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-258-106 | CBACT04C.cbl:258 | 0100-XREFFILE-OPEN | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-271-113 | CBACT04C.cbl:271 | 0200-DISCGRP-OPEN | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-276-121 | CBACT04C.cbl:276 | 0200-DISCGRP-OPEN | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-290-128 | CBACT04C.cbl:290 | 0300-ACCTFILE-OPEN | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-295-136 | CBACT04C.cbl:295 | 0300-ACCTFILE-OPEN | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-308-143 | CBACT04C.cbl:308 | 0400-TRANFILE-OPEN | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-313-151 | CBACT04C.cbl:313 | 0400-TRANFILE-OPEN | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-328-160 | CBACT04C.cbl:328 | 1000-TCATBALF-GET-NEXT | delete-MOVE | equivalent | A08 |
| CBACT04C-delete-MOVE-358-187 | CBACT04C.cbl:358 | 1050-UPDATE-ACCOUNT | delete-MOVE | equivalent | A08 |
| CBACT04C-delete-MOVE-379-199 | CBACT04C.cbl:379 | 1100-GET-ACCT-DATA | delete-MOVE | equivalent | A08 |
| CBACT04C-delete-MOVE-401-211 | CBACT04C.cbl:401 | 1110-GET-XREF-DATA | delete-MOVE | equivalent | A08 |
| CBACT04C-delete-MOVE-423-223 | CBACT04C.cbl:423 | 1200-GET-INTEREST-RATE | delete-MOVE | equivalent | A08 |
| CBACT04C-delete-MOVE-447-239 | CBACT04C.cbl:447 | 1200-A-GET-DEFAULT-INT-RATE | delete-MOVE | equivalent | A08 |
| CBACT04C-delete-MOVE-491-264 | CBACT04C.cbl:491 | 1300-B-WRITE-TX | delete-MOVE | equivalent | A09 |
| CBACT04C-delete-MOVE-492-265 | CBACT04C.cbl:492 | 1300-B-WRITE-TX | delete-MOVE | equivalent | A09 |
| CBACT04C-delete-MOVE-493-266 | CBACT04C.cbl:493 | 1300-B-WRITE-TX | delete-MOVE | equivalent | A09 |
| CBACT04C-delete-MOVE-494-267 | CBACT04C.cbl:494 | 1300-B-WRITE-TX | delete-MOVE | equivalent | A09 |
| CBACT04C-delete-MOVE-502-277 | CBACT04C.cbl:502 | 1300-B-WRITE-TX | delete-MOVE | equivalent | A08 |
| CBACT04C-delete-MOVE-523-287 | CBACT04C.cbl:523 | 9000-TCATBALF-CLOSE | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-528-295 | CBACT04C.cbl:528 | 9000-TCATBALF-CLOSE | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-542-302 | CBACT04C.cbl:542 | 9100-XREFFILE-CLOSE | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-547-310 | CBACT04C.cbl:547 | 9100-XREFFILE-CLOSE | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-560-317 | CBACT04C.cbl:560 | 9200-DISCGRP-CLOSE | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-565-325 | CBACT04C.cbl:565 | 9200-DISCGRP-CLOSE | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-578-332 | CBACT04C.cbl:578 | 9300-ACCTFILE-CLOSE | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-583-340 | CBACT04C.cbl:583 | 9300-ACCTFILE-CLOSE | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-596-347 | CBACT04C.cbl:596 | 9400-TRANFILE-CLOSE | delete-MOVE | equivalent | A03 |
| CBACT04C-delete-MOVE-601-355 | CBACT04C.cbl:601 | 9400-TRANFILE-CLOSE | delete-MOVE | equivalent | A07 |
| CBACT04C-delete-MOVE-630-373 | CBACT04C.cbl:630 | 9999-ABEND-PROGRAM | delete-MOVE | equivalent | A10 |
| CBACT04C-delete-MOVE-639-386 | CBACT04C.cbl:639 | 9910-DISPLAY-IO-STATUS | delete-MOVE | equivalent | A11 |
| CBACT04C-delete-MOVE-644-389 | CBACT04C.cbl:644 | 9910-DISPLAY-IO-STATUS | delete-MOVE | equivalent | A12 |
| CBACT04C-receiving-scale-133-20 | CBACT04C.cbl:133 | WORKING-STORAGE | receiving-scale | equivalent | A13 |
| CBACT04C-receiving-scale-139-24 | CBACT04C.cbl:139 | WORKING-STORAGE | receiving-scale | equivalent | A14 |
| CBACT04C-receiving-scale-164-26 | CBACT04C.cbl:164 | WORKING-STORAGE | receiving-scale | equivalent | A15 |
| CBACT04C-receiving-scale-169-30 | CBACT04C.cbl:169 | WORKING-STORAGE | receiving-scale | equivalent | A16 |
| CBACT04C-receiving-scale-172-32 | CBACT04C.cbl:172 | WORKING-STORAGE | receiving-scale | equivalent | A02 |
| CBACT04C-receiving-scale-173-34 | CBACT04C.cbl:173 | WORKING-STORAGE | receiving-scale | equivalent | A17 |
| CBACT04C-receiving-scale-72-6 | CBACT04C.cbl:72 | FILE SECTION | receiving-scale | equivalent | A18 |
| CBACT04C-receiving-size-125-13 | CBACT04C.cbl:125 | WORKING-STORAGE | receiving-size | equivalent | A19 |
| CBACT04C-receiving-size-133-19 | CBACT04C.cbl:133 | WORKING-STORAGE | receiving-size | equivalent | A20 |
| CBACT04C-receiving-size-138-21 | CBACT04C.cbl:138 | WORKING-STORAGE | receiving-size | equivalent | A20 |
| CBACT04C-receiving-size-139-23 | CBACT04C.cbl:139 | WORKING-STORAGE | receiving-size | equivalent | A20 |
| CBACT04C-receiving-size-172-31 | CBACT04C.cbl:172 | WORKING-STORAGE | receiving-size | equivalent | A02 |
| CBACT04C-receiving-size-177-35 | CBACT04C.cbl:177 | LINKAGE SECTION | receiving-size | equivalent | A20 |
| CBACT04C-skip-PERFORM-216-74 | CBACT04C.cbl:216 | PROCEDURE entry | skip-PERFORM | equivalent | A21 |
| CBACT04C-skip-PERFORM-220-75 | CBACT04C.cbl:220 | PROCEDURE entry | skip-PERFORM | equivalent | A22 |

## Evidence

- [Retained public aggregate](https://github.com/howardweale/lightyear-carddemo-modernization/releases/download/evidence-2026-10-18-intcalc/equivalence-aggregate.zip), ZIP SHA-256 `06f45c7e2311db34193b2c218d0744b6f18d1fdcd0d2d02f61f402c66e5e4dcb`.
- [Retained verdict publication](intcalc-releasability-2026-10-21.json); the original measured result remains unchanged.
- [XREF runtime argument](gnucobol-xref-layout-argument.md); no native equivalence claim.
- Source and evidence-member hashes, per-site record hashes, and conditions are retained in the companion JSON.
