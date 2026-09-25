# iDempiere calibration: measured before and after

Same pinned source, same 1,078 file pairs, same 111,293 in-scope SQL units across Oracle and PostgreSQL.

| Count | Before | Parser extensions | Calibrated gate |
|---|---:|---:|---:|
| Decided units | 776 | 776 | 780 |
| Parsed but indeterminate | 103,922 | 109,112 | 109,108 |
| Unsupported units | 6,595 | 1,405 | 1,405 |
| In-scope units | 111,293 | 111,293 | 111,293 |
| Administrative exclusions | 4,127 | 4,127 | 4,127 |

**Actual lift: 4 additional decided units.** Unsupported units fell by 5,190. No prior decision or divergence was lost.

Parsing more syntax is not the same as deciding more behavior. The parser-only column isolates that distinction. The final column also compares an unambiguous positional prefix before the first unknown or mismatched effect, plus an explicitly supplied context if present. It never searches ahead or drops unmatched operations.

Complete pairs: 1 equivalent, 0 divergent, 1,077 indeterminate. This is still insufficient for a customer equivalence claim.

Applied context hash: none. Context facts are caller-supplied contracts, not authenticated runtime state.

## Schema and session baseline

The generated baseline binds every case and input hash, lists required tables and columns, and retains source-located DDL declarations. Catalog completeness, triggers, constraints, row policies, rewrite rules and session settings remain explicitly unknown. A declaration found in a migration is not the catalog at entry to another migration. Customer catalog/session evidence must fill those facts before the numeric DML comparison can use them.

| Remaining cause (counts overlap) | Units |
|---|---:|
| expression-requires-dialect-or-session-semantics | 93,136 |
| dml-schema-trigger-and-coercion-context-required | 92,763 |
| ordered-effect-alignment-required | 13,150 |
| baseline-object-required | 5,694 |
| constraint-column-domain-required | 5,611 |
| constraint-state-context-required | 2,920 |
| character-empty-string-length-and-collation-policy | 1,260 |
| unsupported-syntax | 1,181 |
| helper-catalog-and-dependent-view-effects | 741 |
| national-character-domain-context-required | 547 |
| opaque-default-expression | 410 |
| datetime-precision-range-and-zone-policy | 226 |

## Evidence

Source commit: `731515dcdd5278b843db33b9d3109d155b881951`.
Measurement hash: `f9e234deb3c33d7e7d2fd2517ca629d077b8f08a77714ab1919ad8cf593e4fea`.
The retained baseline was reproduced from source before measuring the new gate. No normalization rule was applied, no customer system was invoked, and no application-equivalence claim is made.

The full replay bundle contains before/after reports, source-bound changes, a schema/session acquisition baseline, and the report comparison. Compressed report ranges change when causes change; the generic comparison flags that partition change. This replay separately checks the unchanged statement ordinals and records every changed decision.
