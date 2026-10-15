# INTCALC releasability — 2026-10-14

**Not releasable.** Fresh loader-domain evidence and effective decisions are still pending.

This is a provisional, twin-scoped engineering assessment. It is not z/OS confirmation or a customer release.

Main evidence: run 38624637311 at `8650f58c5fdcd0916e22152b5bbbaa1182efdf71`. PR328 cross-check: run 38312412871. Artifact ZIP and retained-file hashes are in [the evidence index](release-evidence-2026-10-14/index.json).

| Criterion | Measured | State |
| --- | --- | --- |
| Business outcomes | 8/8 | Met on retained main run |
| I/O outcomes | 85/86 | Last EOF edge needs effective signed exception |
| Raw mutation kills | 308/421; 162 failure, 146 divergent | Below 90% |
| Systematic sites | 421 | No site removed by loader rule |
| Loader gaps | 113 | Fresh CI overlay pending |
| Effective policy | scenario-threshold/2 | Conditional; unsigned |

## Targeted cases

| Item | Main valid comparisons | PR328 | Difference |
| --- | --- | --- | --- |
| CBACT04C-receiving-scale-164-26 | 200/200 | 200/200 | None |
| CBACT04C-receiving-scale-173-34 | 200/200 | 200/200 | None |
| CBTRN02C-receiving-scale-173-20 | 200/200 | 200/200 | None |

## INTCALC output diversity

| Field | Before | Main | PR328 |
| --- | --- | --- | --- |
| ACCTFILE:ACCOUNT-RECORD.ACCT-ACTIVE-STATUS | 1 | 2 | 2 |
| TRANSACT:TRAN-RECORD.TRAN-ORIG-TS | 1 | 3 | 3 |
| TRANSACT:TRAN-RECORD.TRAN-PROC-TS | 1 | 3 | 3 |

## POSTTRAN output diversity

| Field | Before | Main | PR328 |
| --- | --- | --- | --- |
| ACCTFILE:ACCOUNT-RECORD.ACCT-ACTIVE-STATUS | 1 | 2 | 2 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-GROUP-ID | 1 | 3 | 3 |
| DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-CAT-CD | 1 | 2 | 2 |
| DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-MERCHANT-ID | 1 | 3 | 3 |
| DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-PROC-TS | 1 | 3 | 3 |
| DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-SOURCE | 1 | 3 | 3 |
| DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-TYPE-CD | 1 | 2 | 2 |
| TRANFILE:TRAN-RECORD.TRAN-MERCHANT-ID | 1 | 3 | 3 |
| TRANFILE:TRAN-RECORD.TRAN-PROC-TS | 1 | 3 | 3 |

The seven INTCALC constants remain compared and mutation-tested. Their exact source lines and hashes are retained in the JSON. Their accepted constant classification does not silently activate threshold policy.

## Remaining steps

- 113 raw execution gaps require fresh, individually assessed loader-domain overlays.
- Current raw mutation rate is 308/421, below 90%; new projected rates and independent cross-check await CI.
- Effective threshold/2, constant-field and loader-domain decisions remain unsigned.
- Items 20/23/42 have 200/200 evidence but need explicit current-head effectiveness bindings.

**Not releasable:** finish fresh loader receipts and independent threshold reconciliation, then obtain the specific effective signatures.
