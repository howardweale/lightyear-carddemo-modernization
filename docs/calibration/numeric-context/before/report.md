# Decidability report

synthetic-numeric-context

Decided **0 / 6 in-scope units (0.000%)**.
Complete cases decided: **0 / 3 (0.000%)**.

Equivalent cases: 0. Divergent cases: 0. Indeterminate cases: 3.
Excluded administrative units: 0. Unsupported units: 0.

Decidability counts both equivalent and divergent results. It is not a pass rate or proof of application equivalence.
Scope: all eligible files in the declared roots; other extensions explicitly excluded
Evidence mode: local-gate-replay. No runtime invocation or source authentication is claimed.

## Denominators by lane

| Lane | All input units | Excluded | In scope | Decided | Decided / all input | Decided / in scope |
|---|---:|---:|---:|---:|---:|---:|
| oracle | 3 | 0 | 3 | 0 | 0.000% | 0.000% |
| postgresql | 3 | 0 | 3 | 0 | 0.000% | 0.000% |

## Causes

Cause counts overlap when a unit has several blockers. The disjoint clusters in report.json account for every unresolved record exactly once.

| Cause | Work required | Units | Sole recorded blocker | Cases |
|---|---|---:|---:|---:|
| dml-schema-trigger-and-coercion-context-required | semantic-evidence | 6 | 0 | 3 |
| expression-requires-dialect-or-session-semantics | semantic-evidence | 6 | 0 | 3 |

## Normalization proposals

Drafts require domain evidence and review. No rule is applied and no gain is predicted.

## Next calibration run

1. Select a cause and inspect its source-bound examples in the report.
2. Narrow a draft proposal and recompute its blast radius with assess.
3. Obtain domain evidence and governed review, then implement the separately tested comparator change.
4. Rerun the same corpus and use compare to measure changes and surface lost divergences.

A parser gap, missing observation or unresolved business meaning must not be hidden by a normalization.

Corpus SHA-256: 6066f185229a8c82a59ea7524051d026af905df10664e033672bec0af72f034f
Report SHA-256: 6d8d9f5c0bfae2d28f462ff43b60ea9da832368a23c1a8325d7e46db9a0824c6
