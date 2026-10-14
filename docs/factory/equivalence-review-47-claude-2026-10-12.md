# Review of the 47 remaining argued equivalents — October 12, 2026

Reviewer: Claude (AI-assisted review), for Howard's acceptance. Not independent human attestation. Checked against `spec/mainframe/public-source` CBACT04C/CBTRN02C at the pinned hashes on main, and the packet in PR #328 (`3ede7ca`).

## Result

- **All 47 arguments are correct within their stated scope.** No argument was found to be wrong. The targeted campaign agrees: 0 refutations.
- **3 are duplicates** of mutants already accepted in the October 11 sample (items 10, 33, 38). Record them once.
- **3 have incomplete targeted evidence** (items 20, 23, 42: 198/200 clock refusals). The arguments are sound; acceptance for the threshold waits for the #328 rerun to complete all 200 comparisons.
- **3 depend on keep-or-fix entries** (30: CBACT04C-FINAL-ACCOUNT-EOF-ELSE; 35, 36: REWRITE-109). They must invalidate automatically if those entries change to fix.
- **11 are host-only** (11–16, 19, 24, 37, 38, 41): they rely on GnuCOBOL default initialisation of fields without VALUE clauses, the host CEE3ABD shim ABI, or the Berkeley DB adapter. They must never count for z/OS-facing claims.
- **The other 36 are z/OS-plausible** (standard COBOL semantics: unused fields, dead stores, exact arithmetic, same storage class). Keep them twin-scoped until a ZD&T or mainframe check confirms them.

## Recommended decision for Howard

Accept all 47 for **twin-scoped** threshold use, with: the 3 duplicates recorded once; items 20, 23, 42 effective only after the #328 rerun completes 200/200 valid comparisons each; dependency links on 30, 35, 36; items 11–16, 19, 24, 37, 38, 41 marked host-only. No z/OS-facing acceptance beyond the two already accepted on October 11.

## Item-by-item

| # | Mutant | Operator | Decision | Scope | Note |
|---|---|---|---|---|---|
| 1 | `CBACT04C-CVACT03Y-receiving-scale-6-2` | receiving-scale | accept | twin; z/OS plausible, unconfirmed | CBACT04C never references XREF-CUST-ID/XREF-ACCT-ID (only FD-XREF-ACCT-ID, lines 204/395/397); only XREF-CARD-NUM is consumed (495). |
| 2 | `CBACT04C-CVACT03Y-receiving-scale-7-4` | receiving-scale | accept | twin; z/OS plausible, unconfirmed | Same as 1. |
| 3 | `CBACT04C-CVACT03Y-receiving-size-6-1` | receiving-size | accept | twin; z/OS plausible, unconfirmed | Same as 1. |
| 4 | `CBACT04C-CVACT03Y-receiving-size-7-3` | receiving-size | accept | twin; z/OS plausible, unconfirmed | Same as 1. |
| 5 | `CBACT04C-constant-192-48` | constant | accept | twin; z/OS plausible, unconfirmed | WS-COUNTERS / WS-RECORD-COUNT has no reference other than line 192. |
| 6 | `CBACT04C-constant-192-49` | constant | accept | twin; z/OS plausible, unconfirmed | Same as 5. |
| 7 | `CBACT04C-constant-638-382` | constant | accept | twin; z/OS plausible, unconfirmed | IO-STATUS-04 bytes 2-4 are overwritten at 641 before the DISPLAY at 642. |
| 8 | `CBACT04C-constant-639-384` | constant | accept | twin; z/OS plausible, unconfirmed | Unsigned binary: -1 stores 1, left byte 0x00; right byte overwritten at 640. |
| 9 | `CBACT04C-constant-639-385` | constant | accept | twin; z/OS plausible, unconfirmed | 1 leaves left byte 0x00; right byte overwritten. |
| 10 | `CBACT04C-delete-ADD-192-50` | delete-ADD | already accepted (sample) | twin; z/OS plausible, unconfirmed | Already accepted in the October 11 20-mutant sample. |
| 11 | `CBACT04C-delete-MOVE-491-264` | delete-MOVE | accept | host only | TRAN-RECORD fields have no VALUE clause and no other writer; relies on GnuCOBOL zero/space initialisation. Not guaranteed on z/OS. |
| 12 | `CBACT04C-delete-MOVE-492-265` | delete-MOVE | accept | host only | As 11. |
| 13 | `CBACT04C-delete-MOVE-493-266` | delete-MOVE | accept | host only | As 11. |
| 14 | `CBACT04C-delete-MOVE-494-267` | delete-MOVE | accept | host only | As 11. |
| 15 | `CBACT04C-delete-MOVE-630-373` | delete-MOVE | accept | host only | TIMING has no VALUE clause; relies on host zero-initialisation. On z/OS the CEE3ABD timing parameter controls clean-up behaviour, so an uninitialised value could differ. |
| 16 | `CBACT04C-delete-MOVE-639-386` | delete-MOVE | accept | host only | TWO-BYTES-BINARY has no VALUE clause; host zero-initialisation (same as accepted 718-447). |
| 17 | `CBACT04C-delete-MOVE-644-389` | delete-MOVE | accept | twin; z/OS plausible, unconfirmed | IO-STATUS-04 has VALUE 0 subfields (129-131); all 17 calls to 9910 are followed by 9999-ABEND, so it runs at most once. |
| 18 | `CBACT04C-receiving-scale-133-20` | receiving-scale | accept | twin; z/OS plausible, unconfirmed | Only assignments 0/8/12/16 and 88-level reads; no external use. |
| 19 | `CBACT04C-receiving-scale-139-24` | receiving-scale | accept | host only | 8-byte scaled zero; CEE3ABD reads 4 bytes of zero. Holds on the host shim; z/OS ABI not proven. |
| 20 | `CBACT04C-receiving-scale-164-26` | receiving-scale | accept argument; evidence pending #328 rerun | twin; z/OS plausible, unconfirmed | 621-622: DB2-MIL integral, DB2-REST '0000'; 27th character truncated by the 26-byte move. Argument sound; targeted evidence incomplete (198/200 clock refusals) until the #328 rerun completes. |
| 21 | `CBACT04C-receiving-scale-169-30` | receiving-scale | accept | twin; z/OS plausible, unconfirmed | Accumulates cent values (467); extra decimal is exact; same integer range. |
| 22 | `CBACT04C-receiving-scale-172-32` | receiving-scale | accept | twin; z/OS plausible, unconfirmed | As 5. |
| 23 | `CBACT04C-receiving-scale-173-34` | receiving-scale | accept argument; evidence pending #328 rerun | twin; z/OS plausible, unconfirmed | STRING DELIMITED BY SIZE into 16-byte TRAN-ID (476-480): extra digit becomes the 17th character and is dropped. Evidence incomplete until #328 rerun. |
| 24 | `CBACT04C-receiving-scale-72-6` | receiving-scale | accept | host only | Relies on GnuCOBOL/Berkeley DB key handling for a shifted FD field. Host-only by construction; lowest-confidence item, a good ZD&T check. |
| 25 | `CBACT04C-receiving-size-125-13` | receiving-size | accept | twin; z/OS plausible, unconfirmed | Both 9(4) and 9(3) unsigned binary are halfwords; max value 255. |
| 26 | `CBACT04C-receiving-size-138-21` | receiving-size | accept | twin; z/OS plausible, unconfirmed | Both fullword; value 999. |
| 27 | `CBACT04C-receiving-size-139-23` | receiving-size | accept | twin; z/OS plausible, unconfirmed | Both fullword; value 0. |
| 28 | `CBACT04C-receiving-size-172-31` | receiving-size | accept | twin; z/OS plausible, unconfirmed | As 5. |
| 29 | `CBACT04C-skip-PERFORM-216-74` | skip-PERFORM | accept | twin; z/OS plausible, unconfirmed | 1400-COMPUTE-FEES (518-520) contains only a comment and EXIT. |
| 30 | `CBACT04C-skip-PERFORM-220-75` | skip-PERFORM | accept, dependent on CBACT04C-FINAL-ACCOUNT-EOF-ELSE | twin; z/OS plausible, unconfirmed | Unreachable ELSE (keep-or-fix entry). Invalidated automatically if that entry changes to fix. |
| 31 | `CBTRN02C-CVACT03Y-receiving-scale-7-4` | receiving-scale | accept | twin; z/OS plausible, unconfirmed | Numeric MOVE to 9(11) integer drops the fractional digit (394, 469, 505); standard truncation. |
| 32 | `CBTRN02C-constant-717-443` | constant | accept | twin; z/OS plausible, unconfirmed | As 7 (POSTTRAN 717-721). |
| 33 | `CBTRN02C-constant-718-445` | constant | already accepted (sample) | twin; z/OS plausible, unconfirmed | Already accepted in the 20-mutant sample. |
| 34 | `CBTRN02C-constant-718-446` | constant | accept | twin; z/OS plausible, unconfirmed | As 9. |
| 35 | `CBTRN02C-delete-MOVE-209-47` | delete-MOVE | accept, dependent on REWRITE-109 | twin; z/OS plausible, unconfirmed | Every failure path 100-103 overwrites the full description before the reject write at 448. Depends on REWRITE-109 staying keep. |
| 36 | `CBTRN02C-delete-MOVE-557-314` | delete-MOVE | accept, dependent on REWRITE-109 | twin; z/OS plausible, unconfirmed | Dead store only because REWRITE-109 is kept; invalidated if it changes to fix. |
| 37 | `CBTRN02C-delete-MOVE-709-434` | delete-MOVE | accept | host only | As 15 (POSTTRAN 709-711). |
| 38 | `CBTRN02C-delete-MOVE-718-447` | delete-MOVE | already accepted (sample) | host only | Already accepted (host-scoped) in the 20-mutant sample. |
| 39 | `CBTRN02C-delete-MOVE-723-450` | delete-MOVE | accept | twin; z/OS plausible, unconfirmed | As 17; all 18 POSTTRAN 9910 calls are followed by 9999-ABEND. |
| 40 | `CBTRN02C-receiving-scale-142-14` | receiving-scale | accept | twin; z/OS plausible, unconfirmed | As 18. |
| 41 | `CBTRN02C-receiving-scale-148-18` | receiving-scale | accept | host only | As 19. |
| 42 | `CBTRN02C-receiving-scale-173-20` | receiving-scale | accept argument; evidence pending #328 rerun | twin; z/OS plausible, unconfirmed | As 20 (POSTTRAN 700-701). Evidence incomplete until #328 rerun. |
| 43 | `CBTRN02C-receiving-scale-187-28` | receiving-scale | accept | twin; z/OS plausible, unconfirmed | WS-TEMP-BAL sums cent values (403-406); the comparison at 407 is unchanged. |
| 44 | `CBTRN02C-receiving-size-134-7` | receiving-size | accept | twin; z/OS plausible, unconfirmed | As 25. |
| 45 | `CBTRN02C-receiving-size-147-15` | receiving-size | accept | twin; z/OS plausible, unconfirmed | As 26. |
| 46 | `CBTRN02C-receiving-size-148-17` | receiving-size | accept | twin; z/OS plausible, unconfirmed | As 27. |
| 47 | `CBTRN02C-rounded-403-196` | rounded | accept | twin; z/OS plausible, unconfirmed | Exact cent result; ROUNDED cannot change it. |

## Related decisions in PR #328

- **Seven INTCALC constant-by-design fields** (TRAN-TYPE-CD '01' at 482, TRAN-CAT-CD '05' at 483, TRAN-SOURCE 'System' at 484, TRAN-MERCHANT-ID 0 and NAME/CITY/ZIP spaces at 491–494): recommend **accept as declared constants**, each bound to its source line and source hash, invalidated if the source changes. A mutant that alters those literals is still detected because the output field is compared.
- **INTCALC duplicate-category scenario** (cause of the 113 INTCALC evidence gaps): a duplicate primary key cannot exist in an indexed (KSDS-style) file, and the loader correctly refuses it (rc 66) before the program runs. Recommend reclassifying it as an expected loader refusal outside the mutation-comparison domain, by explicit scoped decision with fresh receipts, rather than leaving every INTCALC argument blocked by it.
- **Twelve needs-variation fields**: agree; let the #328 systematic run establish diversity.
