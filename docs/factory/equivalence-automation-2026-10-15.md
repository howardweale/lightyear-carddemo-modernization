# Automated equivalence — 2026-10-15

The retained baseline contains **227 argued equivalents: 180 compiler/class arguments and 47 individual reviews**, plus nine additional POSTTRAN survivors/evidence gaps. INTCALC has 421 eligible mutation sites; POSTTRAN has 483. TRANREPT is a separate held-out inventory of 413 sites, with no inherited kills or equivalence decisions.

The earlier October 12 INTCALC aggregate listed 167 gap IDs beside a count of 113. The complete per-mutant records confirm 113; the additional 54 IDs were killed. This report uses the sealed October 15 integration-run rows and preserves the historical publication unchanged.

Execution: [GitHub Actions run 38775203996](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38775203996), source commit `7d95d7da8fbfd7ad8d4c30979821bf18b75cae54`. Public CardDemo only; zero model calls. All results are twin-scoped.

This run resolves **8/227 (3.5%)** of the argued equivalents automatically, including **5/47 individual reviews**. The 95% target is not met. Unsigned class proposals are excluded.

| Program | Route | Resolved | Of 47 individual reviews | Other survivors resolved | New kills |
|---|---|---:|---:|---:|---:|
| INTCALC | S1 | 4 | 2 | 0 | 0 |
| INTCALC | S2 | 0 | 0 | 0 | 0 |
| INTCALC | S3 | 0 | 0 | 0 | 0 |
| INTCALC | S4 | 0 | 0 | 0 | 0 |
| POSTTRAN | S1 | 3 | 2 | 0 | 0 |
| POSTTRAN | S2 | 0 | 0 | 0 | 0 |
| POSTTRAN | S3 | 1 | 1 | 0 | 0 |
| POSTTRAN | S4 | 0 | 0 | 0 | 0 |
| TRANREPT | S1 | 2 | 0 | 2 | 0 |
| TRANREPT | S2 | 0 | 0 | 0 | 0 |
| TRANREPT | S3 | 0 | 0 | 0 | 0 |
| TRANREPT | S4 | 0 | 0 | 0 | 0 |

| Program | Argued resolved automatically | Unobservable | Unresolved, including unobservable | Estimated review minutes / 1,000 sites |
|---|---:|---:|---:|---:|
| INTCALC | 4/113 (3.5%) | 3 | 109 | 1294.5 |
| POSTTRAN | 4/114 (3.5%) | 0 | 119 | 1231.9 |
| TRANREPT | Not applicable (held out) | 0 | 411 | 4975.8 |

Review-time estimates assume five minutes per remaining packet. They are planning estimates, not measured operator time. The 95% automatic-resolution share is a target; pending class signatures do not contribute.

| Program | Raw before | Raw after | Adjusted before new proofs | Adjusted after |
|---|---:|---:|---:|---:|
| INTCALC | 308/421 | 308/421 | 308/421 | 308/417 |
| POSTTRAN | 360/483 | 360/483 | 360/483 | 360/479 |

Adjusted-before shows the new overlay with no new proof exclusions. Historical individually accepted exclusions and active release policy are not rewritten. Every unobservable or unresolved site remains in the denominator.

## Validation and disabled routes

Each enabled local statement/PIC encoder was checked on at least 10,000 deterministic random in-domain inputs per side, comparing every receiving byte against the actual pinned GnuCOBOL twin. Any disagreement disables that exact statement/PIC shape. Two complete pipeline runs produced identical classifications for every mutant, including unresolved and unobservable cases. Every emitted machine resolution was also independently rebuilt, re-solved or replayed on the same source head.

- INTCALC: 84 solver targets; 1000 generated search/replay cases; 0 disabled encoder shapes.
- POSTTRAN: 100 solver targets; 1000 generated search/replay cases; 0 disabled encoder shapes.
- TRANREPT: 144 solver targets; 0 generated search/replay cases; 0 disabled encoder shapes.

Held-out class measurements: 0. Disabled classes: none observed. Zero matched members is not evidence of generality.

Supported arithmetic is an exact scaled-integer local subset. ON SIZE ERROR handlers, division, aliases and paragraph/path-to-output proofs are explicitly unsupported. The held-out program has compiler/local-statement measurements, but no whole-application execution harness. No downstream masking is assumed.

## Decisions waiting for Howard

Class and audit contracts are unsigned. Approval must bind the exact packet, matcher, source and scope. Model-spend requests: none. This work does not authorize release or native z/OS execution.

| Program | Unsigned class requests | Audit samples | Audit errors / reviewed | 95% upper bound |
|---|---:|---:|---|---|
| INTCALC | 1 | 4 | Pending; no human audit yet | Not estimated before review |
| POSTTRAN | 2 | 4 | Pending; no human audit yet | Not estimated before review |
| TRANREPT | 0 | 2 | Pending; no human audit yet | Not estimated before review |

A confirmed wrong resolution disables its program/route in the signed review overlay. The original CI evidence remains immutable. Reapproval requires repaired implementation, fresh evidence and a new audit.

Recheck commands and artifact bindings are in `equivalence-automation-guide.md`. Full compiler objects, 10,000-input validation transcripts and executed scenarios are retained in the run artifacts; compact proof and review records are published beside this report.
