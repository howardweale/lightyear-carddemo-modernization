# iDempiere calibration: measured before and after

Same pinned source, same 1,078 file pairs, same 111,293 in-scope SQL units across Oracle and PostgreSQL.

| Count | Before | Parser extensions | Calibrated gate |
|---|---:|---:|---:|
| Decided units | 776 | 776 | 780 |
| Parsed but indeterminate | 103,922 | 109,112 | 109,108 |
| Unsupported units | 6,595 | 1,405 | 1,405 |
| In-scope units | 111,293 | 111,293 | 111,293 |
| Administrative exclusions | 4,127 | 4,127 | 4,127 |

**Native context lift: 0 additional decided units.** The unchanged current gate decides 780 units without context. The table also retains the older baseline; its four-unit calibration improvement predates this experiment. Unsupported units fell by 5,190. No prior decision or divergence was lost.

Parsing more syntax is not the same as deciding more behavior. The parser-only column isolates that distinction. The final column also compares an unambiguous positional prefix before the first unknown or mismatched effect, plus an explicitly supplied context if present. It never searches ahead or drops unmatched operations.

Complete pairs: 1 equivalent, 0 divergent, 1,077 indeterminate. This is still insufficient for a customer equivalence claim.

Applied context hash: 9b249c9313df8432ec08cd7d07ab68f200d63a2f9efd04af02ed2359b2fd5bc4. Context mode: captured-catalog. Native metadata observations are bound to this replay; they are not independently attested or historical entry-state proof.

## Schema and session baseline

The generated baseline binds every case and input hash, lists required tables and columns, and retains source-located DDL declarations. The acquisition template leaves catalog and session facts unknown. The applied context uses the separately retained native captures. A declaration found in a migration is not the catalog at entry to another migration. Customer catalog/session evidence must fill those facts before the numeric DML comparison can use them.

| Remaining cause (counts overlap) | Units |
|---|---:|
| catalog-side-effects-context-required | 91,972 |
| schema-and-session-baseline-required | 89,555 |
| column-domain-context-required | 86,582 |
| insert-defaults-context-required | 50,601 |
| context-evidence-required | 26,339 |
| ordered-effect-alignment-required | 13,150 |
| baseline-object-required | 5,694 |
| constraint-column-domain-required | 5,611 |
| paired-column-domain-context-required | 4,082 |
| constraint-state-context-required | 2,920 |
| character-empty-string-length-and-collation-policy | 1,260 |
| expression-requires-dialect-or-session-semantics | 1,206 |

## Evidence

Source commit: `731515dcdd5278b843db33b9d3109d155b881951`.
Measurement hash: `0c9ca4df22ac2aab0984e23b4560b9b1ff56a04b90574f5466070c68f7887a7c`.
The retained baseline was reproduced from source before measuring the new gate. No normalization rule was applied, no customer system was invoked, and no application-equivalence claim is made.

The full replay bundle contains before/after reports, source-bound changes, a schema/session acquisition baseline, and the report comparison. Compressed report ranges change when causes change; the generic comparison flags that partition change. This replay separately checks the unchanged statement ordinals and records every changed decision.

## Native context increment

The unchanged current gate without context decides 780 units. The captured context changes that by +0 units.

conditional static comparison on one observed imported baseline; historical entry states not established.
