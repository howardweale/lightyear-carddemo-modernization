# Unsigned threshold/3 proposal

Howard selected preparation of explicit constant-field exemptions. This proposal is not signed or effective; threshold/2 remains unchanged.

The exemption applies only to the diversity requirement. Every listed field remains compared and mutation-tested. Other fields still need at least two observed values. All business, I/O, mutation, survivor, freshness and dependency requirements remain.

| Field | Source line | Observed values | Bound mutants |
| --- | --- | --- | --- |
| TRANSACT:TRAN-RECORD.TRAN-TYPE-CD | 482 | 1 | 1 |
| TRANSACT:TRAN-RECORD.TRAN-CAT-CD | 483 | 1 | 1 |
| TRANSACT:TRAN-RECORD.TRAN-SOURCE | 484 | 1 | 1 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID | 491 | 1 | 3 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME | 492 | 1 | 1 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY | 493 | 1 | 1 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP | 494 | 1 | 1 |

The JSON includes each literal value, source and line hash, and the status of each bound mutant. Source or line changes invalidate the exemption. Removing comparison or mutation evidence invalidates it.

This resolves the requested policy direction, not release readiness. After P1 lands, the six-request path must be revised explicitly for threshold/3 and proven with a throwaway authority before Howard signs. Do not use a threshold/2 approval to apply these exemptions.
