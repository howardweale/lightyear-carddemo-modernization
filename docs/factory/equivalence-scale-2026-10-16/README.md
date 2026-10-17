# Equivalence scale — E1 signing and measurement

After the two pending class signatures: **185/227 (81.5%)**, using the preserved #341 measurement.

Resolved now: **8/227 (3.5%)**. No new signed decision is inferred from chat.

Held out: **TRANREPT/CBTRN03C: two compiler identities in 413 sites, zero class matches; no evidence of generality.** CBSTM03A/B have not yet been measured.

| Program | Route | Resolved now | After pending signatures |
|---|---|---:|---:|
| INTCALC | S1 compiler | 4 | 4 |
| INTCALC | S2 signed class | 0 | 81 |
| POSTTRAN | S1 compiler | 3 | 3 |
| POSTTRAN | S2 signed class | 0 | 96 |
| POSTTRAN | S3 solver | 1 | 1 |

The union of exact member IDs has no overlap with the existing eight resolutions.
INTCALC's three unobservable members remain in its denominator. Nine additional
POSTTRAN evidence-gap/survivor members are outside the 227 argued population and
remain in the full mutation denominator. These are different denominators.
Reviewer minutes per 1,000 sites are not measured.

## Signing handoff

Use only [PR #359’s merged signing packet](../appl-result-signing-2026-10-16/README.md); #357 provides measurement evidence, not importable contracts.

## Work order and gates

E1 adds projection accounting, real committed-blob Tower import tests, immutable
audit packets and the existing full CI pipeline repeated twice. Fresh results
must be reported separately from the historical figures above.

E2 requires byte storage and whole-program control/effects, zero unsupported
constructs for the requested programs, and 1,000 byte-exact differential inputs
per program. E3 analyses cannot claim equivalence until these gates and the
all-killed-mutants rejection checks pass. E3 interval assumptions require their
own scoped signatures. E4 requires 50 schemata/individual build comparisons and
measured speedup. E5 requires real held-out campaigns, not inventories alone.
E6 is a prospective unsigned policy; E7 groups residual evidence without model
calls. None of these stages is represented as completed by E1.

Execution and tests are CI-only. No model calls or main merge are authorized.
Z3 remains pinned to 4.15.3.0 and the existing wheel SHA-256s. All raw #341
evidence, historical scores and requests remain immutable.

## Fresh E1 measurement

[Run 38930496735](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38930496735) at `9a4ecbdf924b7e238b19d4c6880f59ef91a94dac` completed successfully.

| Program | Fresh resolved | Fresh after pending signatures | Generated cases | Person-minutes per 1,000 sites |
|---|---:|---:|---:|---|
| INTCALC | 4/113 | 85/113 | 1,000 | not measured |
| POSTTRAN | 4/114 | 100/114 | 1,000 | not measured |
| TRANREPT/CBTRN03C | 2/413 compiler identities | no class matches | 0 | not measured |

Fresh E1 totals are 8/227 now and 185/227 after pending signatures, separately reproducing the preserved #341 figures, not adding another 177 resolutions. All 113 INTCALC, 123 POSTTRAN (including nine outside the argued denominator), and 413 TRANREPT mutant results were identical across both full runs. The six exact summary/repeat receipts are in `fresh-e1/`; these measure resolutions, not signed acceptances.

Reviewer effort method: prospectively log active review start/stop intervals and reviewer count for the exact site population; exclude CI wait time, sum person-minutes, divide by distinct reviewed sites and multiply by 1,000. No retrospective estimate is substituted.
