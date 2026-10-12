# Factory review decisions — 2026-10-11

Howard’s October 11 decisions supersede the compiler-refusal blocker and unaccepted-EOF conclusions in the earlier review311 milestone. Historical campaign JSON and raw outcomes remain unchanged. This dated overlay records chat authority; it is not a signed threshold approval.

## Adequacy and generator

| Program | Raw sites | Actual kills | Listed argued equivalents | Compiler refusals excluded | Conditional eligible fraction |
|---|---:|---:|---:|---:|---:|
| INTCALC / CBACT04C | 426 | 308 | 113 | 5 | 308/308 |
| POSTTRAN / CBTRN02C | 489 | 369 | 114 | 6 | 369/369 |

The conditional fractions depend on the listed equivalence arguments, which await independent review. Three POSTTRAN arguments were added after the measured campaign; their raw status remains survived. Raw kill fractions remain 308/426 and 369/489. Compiler refusals are listed exclusions, not kills or blockers. Unexplained survivors still block adequacy.

The generator now omits provably invalid literal reference modifications: nonpositive offsets/lengths and bounds beyond simple, proven DISPLAY layouts, including a shrunken containing group. It avoids all 11 historical refusal sites (5 + 6), retaining 421 and 483 candidates. It preserves original IDs and operands for every retained candidate and records every avoided site. Unknown layouts and dynamic bounds are deferred to the compiler. This is static prevention checked against the historical diagnostics, not a claim that a new compiled campaign ran or that every future candidate compiles.

## Accepted EOF exceptions

Howard accepted the source-unreachable false edges at CBACT04C:189 and CBTRN02C:203 on **2026-10-11**, based on the original [I/O gap arguments](io-gap-arguments.json). Acceptance is bound to the exact source hashes and outcome IDs in the [dated decision record](howard-decisions-2026-10-11.json). The policy checks those bindings; a changed source or different edge cannot inherit this acceptance. Both measured I/O fractions remain 85/86, plus one accepted unobserved exception per program. No observed edge is fabricated and coverage denominators remain intact.

## Legacy behavior: keep by default

The [keep-or-fix register](keep-or-fix-register.json) records REWRITE-109 at CBTRN02C:554–560 and the unreachable final-account update at CBACT04C:219–220, including source hashes, supporting lines and observed behavior. These are legacy defects, not twin defects. Converted code must reproduce them by default; changing either behavior requires a separate explicit decision. The registered REWRITE fault returned 0 after status 23 and continued posting. The final-account EOF ELSE is unreachable, so it does not flush the last account. Neither decision accepts unrelated discrepancies such as duplicate transaction IDs.

## Independent review before threshold approval

[Review the random sample of 20 mutants](equivalence-review-sample-2026-10-11.md): 10 from all 113 INTCALC arguments and 10 from all 114 POSTTRAN arguments. The recorded seed is `Howard-2026-10-11-equivalence-review-20-v1`; deterministic SHA-256 ordering samples without replacement. The packet includes each original and mutated operand, argument, supporting source lines, exact source hash, runtime scope when applicable, complete population IDs and population/input LF-normalized hashes. It leaves reviewer identity, findings and dates blank for independent review.

Reproduce the artifacts with `PYTHONPATH=src;. python -B tools/build_factory_decision_review.py` from this checkout. All 18 focused tests passed. The local repository lint command could not run because its environment lacks PyYAML; final-head CI remains required before merge. Focused tests verify the complete pool, repeatable selection, preserved raw evidence, compiler exclusions, source-bound EOF exceptions, and absence of threshold approval. No models, Docker or native B06 runs are involved.

**scenario-threshold/2 remains proposed and unapproved.** Review of the sample precedes Howard’s separate threshold decision. This work grants no release, qualification or measurement credit and does not authorize a merge.

## Addendum — 2026-10-11 retention correction

The [dated correction to the PR318 review milestone](review311-317-milestone.md#correction--howard-retention-follow-up-2026-10-11) supersedes nine POSTTRAN execution refusals formerly counted as kills. The completed fresh compiled phase of failed run 38190468540 confirms 360/483 POSTTRAN kills and 308/421 INTCALC kills; neither is a completed new-head threshold assessment. The summary JSON has an additive correction; raw records remain unchanged. See [retention and margin milestone](retention-fix-milestone-2026-10-11.md).
