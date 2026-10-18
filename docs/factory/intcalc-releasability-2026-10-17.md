# INTCALC releasability — 2026-10-17

Twin-scoped engineering evidence only. No z/OS confirmation and no customer release.

Green main campaign 38763552148 at `f343925026bee705ed3c16a734dc5bae4b24c588`. Raw records are preserved.

| Criterion | Measured | State now | After signatures alone |
| --- | --- | --- | --- |
| Business outcomes | 8/8 | met | unchanged measured coverage |
| I/O outcomes | 85/86 | incomplete; exact exception decision required | evaluate exact accepted edge; signatures add no measured outcomes |
| Twin mutant kill rate | 308/421 | below 95% numerical target | 308/308 projected; evidence prerequisites still apply |
| Output diversity | 7 fields: TRANSACT:TRAN-RECORD.TRAN-CAT-CD, TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY, TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID, TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME, TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP, TRANSACT:TRAN-RECORD.TRAN-SOURCE, TRANSACT:TRAN-RECORD.TRAN-TYPE-CD | constant exemption evidence incomplete | verify complete constant bindings and caught mutants under threshold/3 |
| Effective threshold policy | False | not recorded | requires all typed evidence; provisional evidence cannot authorize release |

| Scope | Raw kills / eligible | Projected kills / eligible | Independent cross-check |
| --- | --- | --- | --- |
| twin | 308/421 | 308/308 | True |
| zos-facing | 308/421 | 308/421 | True |

Loader assessments: {'resolved-by-valid-comparisons': 113}. No sites removed; no loader kill or coverage credit.

The JSON lists every exclusion by basis, every unresolved ID, targeted comparison counts, and every constant's source and mutant bindings.



This dated reassessment preserves the original campaign. New targeted mutants require fresh CI receipts; implementation alone supplies no evidence credit.
Not releasable: Fresh complete caught-mutant evidence required for: TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME, TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY, TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP. Retained campaign index does not certify complete durable retention. Ordered effective decisions are not recorded in these unsigned inputs. Non-provisional release evidence is not established by this retained engineering campaign.
