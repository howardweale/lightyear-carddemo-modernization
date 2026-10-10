# Rule evidence strength milestone — October 10, 2026

New synthetic public reference-model data exercises 17 category rows, 13 emitted transactions, four zero-rate rows, four account groups, signed negative balances, large balances, and two-decimal rounding boundaries. Inputs and expected outputs have new identities. The generator, fixed case-matrix seed, oracle source and all datasets are recorded in `tests/mainframe/fixtures/intcalc-discriminating-v1/run.json`. Expected outputs use `carddemo_oracle.run_intcalc`, the same source-faithful reference path as the rehearsal generator, not a legacy execution.

Both candidate baselines agree with their reference outputs. The independent missing-disclosure case fails in both the Python reference and Java candidate with the required missing-default diagnostic. Original fixture, mapping and signed receipts remain unchanged. New test-authority signed runs are in [evidence-strength-v1](evidence-strength-v1/summary.json); they confer no production approval. The historical four receipts, mutation signature and test Tower proof still replay unchanged through the preserved v1 evaluator.

## Per-rule results

| Rule | Old status / strength | Old divergent / failure kills | New status / strength | New divergent / failure kills |
|---|---|---:|---|---:|
| account-boundary | verified / weak | 0 / 0 | verified / weak | 1 / 0 |
| account-update | verified / weak | 0 / 0 | verified / weak | 0 / 0 |
| default-rate | verified / weak | 0 / 1 | verified / weak | 0 / 1 |
| disclosure-rate | untested / not-assessed | 0 / 0 | verified / discriminating | 1 / 0 |
| fixed-width-contract | verified / weak | 0 / 0 | verified / weak | 0 / 0 |
| interest-transaction | verified / weak | 1 / 0 | verified / weak | 1 / 0 |
| monthly-interest | verified / weak | 0 / 1 | verified / discriminating | 4 / 0 |
| nonzero-rate-emission | verified / weak | 0 / 0 | verified / discriminating | 2 / 0 |
| source-final-account | verified / weak | 0 / 0 | verified / weak | 1 / 0 |
| zero-rate | untested / not-assessed | 0 / 0 | verified / weak | 2 / 0 |

A divergent kill must name a rule output; a failure kill requires a successful baseline followed by a mutant execution error. Failure kills count in kill rate but do not by themselves establish discriminating evidence. Only applicable records contribute to output diversity. Each output must have two distinct values, so rules that legitimately produce constant metadata or zero on all applicable rows remain weak even when mutants die. The final-account predicate has only one applicable final row per fixture and remains weak.

## Mutation ownership and limitations

The old report's method-wide sharing is replaced by a small operator adapter. Each generated edit carries its own rule ID, original legacy anchors, exact modern line span and replaced-source digest. Monthly rounding, scale, operand and constant-zero mutants belong only to monthly-interest. Direct and fallback selection, zero-rate branches, account boundaries, final-account branch and record offset have separate anchors. Account-update and fixed-width-contract have no reviewed modern edit adapter yet and report not-applicable; no sibling service mutation is borrowed. This is a CardDemo adapter, not a general Java mutation engine.

Monthly-interest kills rounding, scale-minus-one, operand-swap and constant-zero on the new fixture. Scale-plus-one survives: later accumulation and fixed-width rendering truncate to two decimals, erasing the third digit. The fixture is not altered to hide that survivor. The old zero fixture kills operand-swap by division-by-zero, which demonstrates crash detection, not arithmetic evidence strength.

Verification against Maintec mainframe outputs, under their separate data authorization, is the real ground truth; this work does not perform it. No private intake was accessed, model called, Docker used, or native execution started.

## What can be said publicly

The previously authenticated public T-SQL results retain their original bounded claims. For INTCALC, the new public synthetic reference-model fixture provides discriminating evidence for disclosure-rate, monthly-interest and nonzero-rate-emission only. It does not establish Maintec equivalence, complete workload coverage, or independent attestation. Other agreeing rules are explicitly weak; summaries never include them in the unqualified verified count.

## Validation

21 focused tests passed (16 existing rule tests and 5 new strength/ownership/tamper tests). Host Java baselines and all scoped variants ran against both public fixtures; both new signed runs replayed. Historical evidence inventory and signatures replayed unchanged. Smoke kit findings are report-only in [the v2 proposal](../verify/smoke-fixture-v2-proposal.md).
