# Scenario adequacy release gate

The additive signed `scenario-assessment/1` receipt binds an existing verdict
without rewriting it. It carries `scenario_adequacy`, the compared-field
inventory and the proposed thresholds. The factory release policy requires an
equivalent verdict, exact signed assessment, and an operator-signed threshold
approval bound to that verdict and assessment. Missing metrics, zero mutant
denominators, unknown fields, unsolved outcomes and provisional/engineering
evidence fail closed. Historical verdict replay remains unchanged.

The proposal is 100% decision outcomes, at least 90% real legacy mutants killed,
and two values per compared output field. Howard has not approved thresholds.
Listed gaps do not become unreachability proofs or shrink the denominator.
Catalogue and Tower catalogue views show `verified (weak scenarios)` alongside
the existing rule evidence strength when scenario evidence is absent or weak.
The catalogue itself grants no release authority.

No production signer was read or invoked. Test keys are ephemeral. These
changes authorize no B06 work, model calls, customer data or promotion.
