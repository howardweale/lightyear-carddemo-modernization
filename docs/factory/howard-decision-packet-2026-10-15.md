# Howard decision packet — 2026-10-15

Factory: activated locally (signed-only); threshold policy not effective.

INTCALC business outcomes 8/8; I/O 85/86; raw mutation kills 308/421.

| Scope | Raw | Projected, pending decisions |
| --- | --- | --- |
| twin | 308/421 | 308/308 |
| zos-facing | 308/421 | 308/421 |

Loader assessments: {'resolved-by-valid-comparisons': 113}.

| Compared field | Distinct values |
| --- | --- |
| ACCTFILE:ACCOUNT-RECORD.ACCT-ACTIVE-STATUS | 2 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-ADDR-ZIP | 3 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CASH-CREDIT-LIMIT | 51 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CREDIT-LIMIT | 51 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CURR-BAL | 58 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CURR-CYC-CREDIT | 5 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CURR-CYC-DEBIT | 5 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-EXPIRAION-DATE | 51 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-GROUP-ID | 5 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-ID | 50 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-OPEN-DATE | 51 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-REISSUE-DATE | 51 |
| TRANSACT:TRAN-RECORD.TRAN-AMT | 13 |
| TRANSACT:TRAN-RECORD.TRAN-CARD-NUM | 54 |
| TRANSACT:TRAN-RECORD.TRAN-CAT-CD | 1 |
| TRANSACT:TRAN-RECORD.TRAN-DESC | 50 |
| TRANSACT:TRAN-RECORD.TRAN-ID | 52 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY | 1 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID | 1 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME | 1 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP | 1 |
| TRANSACT:TRAN-RECORD.TRAN-ORIG-TS | 3 |
| TRANSACT:TRAN-RECORD.TRAN-PROC-TS | 3 |
| TRANSACT:TRAN-RECORD.TRAN-SOURCE | 1 |
| TRANSACT:TRAN-RECORD.TRAN-TYPE-CD | 1 |

Not releasable: Output diversity: source-assigned constants cannot meet threshold/2 as written; Howard must decide an explicit policy change before a signing-only release path can be claimed. Large original mutation receipts await the designated retention store; local staging and artifact hashes are recorded in the index. P1 must land with exact-head approval before generating the six final unsigned requests; no effective signatures have been applied.

This is recorded local activation and twin-scoped evidence; it grants no execution, release, or z/OS authority.

[Measured verdict](intcalc-releasability-2026-10-15.md) · [Decision packet](howard-decision-packet-2026-10-15.md)

## Decisions and blockers

- Output diversity: source-assigned constants cannot meet threshold/2 as written; Howard must decide an explicit policy change before a signing-only release path can be claimed.
- Large original mutation receipts await the designated retention store; local staging and artifact hashes are recorded in the index.
- P1 must land with exact-head approval before generating the six final unsigned requests; no effective signatures have been applied.

## Targeted comparisons

| Program | Mutant | Valid comparisons / cases |
| --- | --- | --- |
| INTCALC | CBACT04C-CVACT03Y-receiving-scale-6-2 | 200/200 |
| INTCALC | CBACT04C-CVACT03Y-receiving-scale-7-4 | 200/200 |
| INTCALC | CBACT04C-CVACT03Y-receiving-size-6-1 | 200/200 |
| INTCALC | CBACT04C-CVACT03Y-receiving-size-7-3 | 200/200 |
| INTCALC | CBACT04C-constant-192-48 | 200/200 |
| INTCALC | CBACT04C-constant-192-49 | 200/200 |
| INTCALC | CBACT04C-constant-638-382 | 200/200 |
| INTCALC | CBACT04C-constant-639-384 | 200/200 |
| INTCALC | CBACT04C-constant-639-385 | 200/200 |
| INTCALC | CBACT04C-delete-ADD-192-50 | 200/200 |
| INTCALC | CBACT04C-delete-MOVE-491-264 | 200/200 |
| INTCALC | CBACT04C-delete-MOVE-492-265 | 200/200 |
| INTCALC | CBACT04C-delete-MOVE-493-266 | 200/200 |
| INTCALC | CBACT04C-delete-MOVE-494-267 | 200/200 |
| INTCALC | CBACT04C-delete-MOVE-630-373 | 200/200 |
| INTCALC | CBACT04C-delete-MOVE-639-386 | 200/200 |
| INTCALC | CBACT04C-delete-MOVE-644-389 | 200/200 |
| INTCALC | CBACT04C-receiving-scale-133-20 | 200/200 |
| INTCALC | CBACT04C-receiving-scale-139-24 | 200/200 |
| INTCALC | CBACT04C-receiving-scale-164-26 | 200/200 |
| INTCALC | CBACT04C-receiving-scale-169-30 | 200/200 |
| INTCALC | CBACT04C-receiving-scale-172-32 | 200/200 |
| INTCALC | CBACT04C-receiving-scale-173-34 | 200/200 |
| INTCALC | CBACT04C-receiving-scale-72-6 | 200/200 |
| INTCALC | CBACT04C-receiving-size-125-13 | 200/200 |
| INTCALC | CBACT04C-receiving-size-138-21 | 200/200 |
| INTCALC | CBACT04C-receiving-size-139-23 | 200/200 |
| INTCALC | CBACT04C-receiving-size-172-31 | 200/200 |
| INTCALC | CBACT04C-skip-PERFORM-216-74 | 200/200 |
| INTCALC | CBACT04C-skip-PERFORM-220-75 | 200/200 |
| POSTTRAN | CBTRN02C-CVACT03Y-receiving-scale-7-4 | 200/200 |
| POSTTRAN | CBTRN02C-constant-717-443 | 200/200 |
| POSTTRAN | CBTRN02C-constant-718-445 | 200/200 |
| POSTTRAN | CBTRN02C-constant-718-446 | 200/200 |
| POSTTRAN | CBTRN02C-delete-MOVE-209-47 | 200/200 |
| POSTTRAN | CBTRN02C-delete-MOVE-557-314 | 200/200 |
| POSTTRAN | CBTRN02C-delete-MOVE-709-434 | 200/200 |
| POSTTRAN | CBTRN02C-delete-MOVE-718-447 | 200/200 |
| POSTTRAN | CBTRN02C-delete-MOVE-723-450 | 200/200 |
| POSTTRAN | CBTRN02C-receiving-scale-142-14 | 200/200 |
| POSTTRAN | CBTRN02C-receiving-scale-148-18 | 200/200 |
| POSTTRAN | CBTRN02C-receiving-scale-173-20 | 200/200 |
| POSTTRAN | CBTRN02C-receiving-scale-187-28 | 200/200 |
| POSTTRAN | CBTRN02C-receiving-size-134-7 | 200/200 |
| POSTTRAN | CBTRN02C-receiving-size-147-15 | 200/200 |
| POSTTRAN | CBTRN02C-receiving-size-148-17 | 200/200 |
| POSTTRAN | CBTRN02C-rounded-403-196 | 200/200 |

No request in this packet is signed or effective. POSTTRAN execution requires its separate exact plan and signed authorization. See the newest POSTTRAN authorization record for readiness.
