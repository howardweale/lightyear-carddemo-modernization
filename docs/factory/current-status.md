# Factory current status — 2026-10-16

Factory: activated locally (signed-only); threshold policy not effective.

INTCALC business outcomes 8/8; I/O 85/86; raw mutation kills 308/421.

| Scope | Raw | Projected, pending decisions |
| --- | --- | --- |
| twin | 308/421 | 308/308 |
| zos-facing | 308/421 | 308/421 |

Loader assessments: resolved-by-valid-comparisons: 113.

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

Diversity deficit: 7 fields.
- TRANSACT:TRAN-RECORD.TRAN-CAT-CD
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP
- TRANSACT:TRAN-RECORD.TRAN-SOURCE
- TRANSACT:TRAN-RECORD.TRAN-TYPE-CD

The loader overlay is twin-scoped. Without signed and confirmed z/OS loader-domain evidence, all 113 raw gaps remain and no z/OS-facing exclusion is applied.
Hypothetical z/OS rate after confirmation: 308/345; not applied.

## POSTTRAN

Not releasable: nine fresh-campaign gaps remain after the effective twin-only October 12 supplement; no new z/OS acceptances.
Business 24/24; I/O 85/86; diversity deficit 0 fields.
twin: 360/370 projected; 10 unresolved.
zos-facing: 360/390 projected; 30 unresolved.

POSTTRAN compiler expiry: 2026-10-30T14:46:00+00:00. Signing deadline: 2026-10-29T14:46:00+00:00.
At least five days remain at rendering time.
[Operator runbook](https://github.com/howardweale/lightyear-carddemo-modernization/blob/f7a137ae5635bed903600afff816d1393c9e420e/docs/factory/posttran-phase2-runbook.md). Preparation and rehearsal do not authorize execution.

## CardDemo data slice

210/210 original records reconstructed; 1,560/1,560 browse comparisons. Overall indeterminate: public IMS framing, DL/I integration and screen/session evidence remain separate gates.

## B06 access

Windows metadata is accessible. Both signed terminal/cleanup records and signed inventory metadata reverified; cause remains unidentified under both preregistered criteria. Raw captures were not reread.

## Draft #341

The targeted equivalence draft remains separate and unsigned; no new acceptances are imported from it. [Review PR #341](https://github.com/howardweale/lightyear-carddemo-modernization/pull/341).

Typed condition support: True. Threshold/3 support: True. Presence of code is not effective policy approval.

Not releasable: exact threshold/3 comparison and mutation bindings, ordered effective signatures and non-provisional release evidence remain required.

This is recorded local activation and twin-scoped evidence; it grants no execution, release, or z/OS authority.

[Measured verdict](intcalc-releasability-2026-10-15.md) · [Decision packet](howard-decision-packet-2026-10-16.md)
