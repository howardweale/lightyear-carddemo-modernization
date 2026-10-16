# Factory current status — 2026-10-15

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
