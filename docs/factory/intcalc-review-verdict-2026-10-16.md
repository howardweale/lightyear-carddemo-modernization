# INTCALC review verdict — 2026-10-16

Not releasable: exact threshold/3 comparison and mutation bindings, ordered effective signatures and non-provisional release evidence remain required.

Measured head `f343925026bee705ed3c16a734dc5bae4b24c588`, run 38763552148. This is a new analysis of retained evidence, not a new campaign.

| Scope | Before supplement | Projected | Unresolved |
| --- | --- | --- | --- |
| twin | 308/421 | 308/308 | 0 |
| zos-facing | 308/421 | 308/421 | 113 |

Diversity: 7 fields below two values.

- TRANSACT:TRAN-RECORD.TRAN-CAT-CD
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP
- TRANSACT:TRAN-RECORD.TRAN-SOURCE
- TRANSACT:TRAN-RECORD.TRAN-TYPE-CD

The loader overlay is twin-scoped. Without signed and confirmed z/OS loader-domain evidence, all 113 raw gaps remain and no z/OS-facing exclusion is applied.

Hypothetical z/OS rate after confirmation and signing: 308/345. Not applied.

All 113 blocked IDs and the hypothetical exclusions by explicit basis are in the JSON.
