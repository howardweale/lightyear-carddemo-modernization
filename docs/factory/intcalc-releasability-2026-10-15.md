# INTCALC releasability — 2026-10-15

Twin-scoped engineering evidence only. No z/OS confirmation and no customer release.

Green main campaign 38763552148 at `f343925026bee705ed3c16a734dc5bae4b24c588`. Raw records are preserved.

| Criterion | Measured | State now | After signatures alone |
| --- | --- | --- | --- |
| Business outcomes | 8/8 | met | met |
| I/O outcomes | 85/86 | exception pending | met only with the exact structurally unreachable edge accepted |
| Twin mutant kill rate | 308/421 | below threshold | 308/308 |
| Output diversity | ['TRANSACT:TRAN-RECORD.TRAN-CAT-CD', 'TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY', 'TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID', 'TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME', 'TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP', 'TRANSACT:TRAN-RECORD.TRAN-SOURCE', 'TRANSACT:TRAN-RECORD.TRAN-TYPE-CD'] | failed | still fails unchanged threshold/2 |
| Effective threshold policy | False | not effective | blocked until prerequisites and policy choice are resolved |

| Scope | Raw kills / eligible | Projected kills / eligible | Independent cross-check |
| --- | --- | --- | --- |
| twin | 308/421 | 308/308 | True |
| zos-facing | 308/421 | 308/421 | True |

Loader assessments: {'resolved-by-valid-comparisons': 113}. No sites removed; no loader kill or coverage credit.

The JSON lists every exclusion by basis, every unresolved ID, targeted comparison counts, and every constant's source and mutant bindings.

Howard's choices: individual constant exceptions with an explicit policy decision, or a threshold/3 constant exemption. Neither is effective merely by accepting the existing threshold/2 request.

The six-request signing simulation is paused at this criterion, as required by the supplied stop rule.

Not releasable: Output diversity: source-assigned constants cannot meet threshold/2 as written; Howard must decide an explicit policy change before a signing-only release path can be claimed. Large original mutation receipts await the designated retention store; local staging and artifact hashes are recorded in the index. P1 must land with exact-head approval before generating the six final unsigned requests; no effective signatures have been applied.
