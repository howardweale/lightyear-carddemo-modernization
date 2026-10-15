# Automated equivalence: evidence and review

This pipeline tests whether a mutation has a machine-checkable resolution. It does not ask a model to decide equivalence, approve release or change a historical score. It runs only on GitHub Actions, on public CardDemo source, inside the existing compiler image with network access disabled during measurement.

An accepted resolution has one of four bases:

- Identical normalized object code, including executable data, symbols and relocations. Only debug sections are removed. Normalization preserves literal bytes and token boundaries; each enabled rule has an adversarial difference test. The pinned compiler clock avoids timestamp rewrites. Literal ordering is unchanged.
- A signed class contract, verified against an externally supplied Factory authority and current journal head. A matched class without a signature remains proposed. New class contracts bind matcher code and individual source/mutation hashes. Held-out measurements must be supplied before a class decision can be applied.
- A saved, independently rechecked UNSAT query for the complete local receiving state. Every enabled statement/PIC shape must agree with actual twin receiving bytes on at least 10,000 deterministic random inputs per side. A disagreement disables that shape.
- Two successful executions with a real output/return-code difference. SAT, a failed compilation, a timeout and reaching a branch are not kills.

Unobservable mutations are oracle gaps. They remain in the denominator. Unknown data flow remains unknown. Existing release thresholds, historic individual decisions and twin implementations remain unchanged.

## Running in CI

The `Equivalence automation` workflow has independent INTCALC, POSTTRAN and held-out TRANREPT measurements. The exact source head is checked out. Z3 4.15.3.0 is installed using the approved wheel hash. The compiler, GCC, binutils and compiler configuration are captured from the existing snapshot-pinned image.

Each INTCALC/POSTTRAN run shares one budget across the solver and directed-search stages: at most 200 local solver targets, 30 seconds per solver call, 1,000 generated program scenarios, 14,400 seconds of measurement wall time, 8 GiB of retained output and zero model calls. Encoder calibration inputs are statement-level validation vectors, recorded separately from generated whole-program scenarios. Rechecking is a separate validation pass on the same source head, within the overall CI timeout.

```sh
python3 -B -m tools.run_equivalence_automation INTCALC /output/run
python3 -B -m tools.recheck_equivalence_automation /output/run /output/recheck
```

These commands refuse execution without the CI environment and exact head binding. They are not instructions to run the workloads on an operator computer.

The pipeline records source hashes, the historical per-mutant input projection, normalized compiler objects, solver queries, validation inputs and transcripts, coverage-guided search choices, killing runs, structured remainder packets and a content manifest. The publication job generates the dated Markdown/JSON reports from complete results only. Full artifacts have a 30-day GitHub retention period; archive them before expiry if long-term byte-for-byte replay is needed. Compact proofs, queries, object hashes and review contracts can be retained in Git without the execution binaries.

## Scope of proof

The local solver uses exact rational arithmetic over scaled integer PIC domains. It handles a conservative numeric MOVE/ADD/SUBTRACT/MULTIPLY/COMPUTE and pure numeric IF subset, receiving truncation, ordinary ROUNDED, DISPLAY, COMP-3 and the measured twin BINARY profile. It compares the receiving value and overflow condition; validation compares every receiving byte. All original and mutant input domains are included. Unsupported aliases, divisions, multiple destinations, ON SIZE ERROR handlers and path-to-output masking remain unresolved. A lexical dominating guard narrows the domain only when its operands are unchanged and every intervening statement is translated. I/O, calls, alias writes and changed guard operands prevent that assumption.

Class matching starts with adjacent, unaliased literal dead stores and full-domain receiving-PIC identity. New patterns are designed using INTCALC/POSTTRAN and then measured separately on TRANREPT. A mismatch on the held-out set disables the class. An empty held-out match set does not demonstrate generality. The held-out source has compiler and local-statement measurements; it does not yet have a whole-application twin driver.

Directed search prioritizes observed statements, branches and paragraphs. The observer must agree with its uninstrumented control before its coverage is used. Solver models use the existing public scenario generator only when every required input has a known dataset binding. An internal working-storage value is not fabricated into a customer input. Unmappable or non-killing SAT models remain unresolved.

## Applying Howard's decisions

The pipeline emits unsigned `equivalence-review` contracts for classes and reproducible audit samples. Audit selection uses the run content hash, with 30 members per program/route, or all members for smaller routes. Before review, observed error rates and confidence bounds are unknown, not zero.

Supply decision proofs separately from the run. The submissions JSON maps each exact contract digest to its exported Tower decision proof. `LIGHTYEAR_FACTORY_AUTHORITY` must point to the operator-owned public trust configuration; a key or journal head supplied inside the evidence cannot authorize it.

```sh
python -B -m tools.apply_equivalence_reviews RUN_DIRECTORY submissions.json new-review-overlay.json \
  --held-out HELD_OUT_RUN_DIRECTORY/class-validation.json
```

The command writes a new file exclusively. It does not modify the original run, activate a release threshold or sign anything. A rejected audit item is a confirmed error and retracts the entire program/route from the new overlay. The report uses a one-sided 95% exact binomial upper confidence bound after human review. No error-free audit is inferred from missing reviews.

Every new PR still requires Howard's exact-commit approval after all required final-head checks pass.
