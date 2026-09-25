# Decidability report

synthetic-numeric-context

Decided **4 / 6 in-scope units (66.667%)**.
Complete cases decided: **2 / 3 (66.667%)**.

Equivalent cases: 1. Divergent cases: 1. Indeterminate cases: 1.
Excluded administrative units: 0. Unsupported units: 0.

Decidability counts both equivalent and divergent results. It is not a pass rate or proof of application equivalence.
Scope: all eligible files in the declared roots; other extensions explicitly excluded
Evidence mode: local-gate-replay. No runtime invocation or source authentication is claimed.

## Denominators by lane

| Lane | All input units | Excluded | In scope | Decided | Decided / all input | Decided / in scope |
|---|---:|---:|---:|---:|---:|---:|
| oracle | 3 | 0 | 3 | 2 | 66.667% | 66.667% |
| postgresql | 3 | 0 | 3 | 2 | 66.667% | 66.667% |

## Causes

Cause counts overlap when a unit has several blockers. The disjoint clusters in report.json account for every unresolved record exactly once.

| Cause | Work required | Units | Sole recorded blocker | Cases |
|---|---|---:|---:|---:|
| catalog-side-effects-context-required | semantic-evidence | 2 | 2 | 1 |

## Normalization proposals

Drafts require domain evidence and review. No rule is applied and no gain is predicted.

## Next calibration run

1. Select a cause and inspect its source-bound examples in the report.
2. Narrow a draft proposal and recompute its blast radius with assess.
3. Obtain domain evidence and governed review, then implement the separately tested comparator change.
4. Rerun the same corpus and use compare to measure changes and surface lost divergences.

A parser gap, missing observation or unresolved business meaning must not be hidden by a normalization.

Corpus SHA-256: 6066f185229a8c82a59ea7524051d026af905df10664e033672bec0af72f034f
Report SHA-256: e3af82d20a1d0698bfabc66adac06e1d016e92ac514e5c7449d35dcbc89b788f
