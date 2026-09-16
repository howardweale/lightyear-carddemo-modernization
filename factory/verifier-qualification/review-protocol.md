# Independent reviewer challenge protocol

Status: **pending independent reviewer and private challenge artifacts**.

1. Record the freeze file and its content hash before creating the evaluation
   results. Keep a copy outside the verifier author's working directory.
2. Define module scope and critical behaviors with the business/source owner.
   State which claims concern source parity and which concern business correctness.
3. Construct correct alternative implementations and faulty implementations in a
   reviewer-controlled workspace. Vary data, representation and fault mechanisms,
   not just identifiers in public examples. Include combined faults and unfamiliar
   but correct code structures. Do not share the private cases before the freeze.
4. Independently execute each fault trigger and retain raw proof of its business
   effect. Exclude equivalent mutants and unexecuted faults from detection-rate
   denominators; report their counts and reasons separately.
5. Run the frozen comparator through the adapter interface. Record raw results
   before interpreting the outcome. The current external evaluator compares cases;
   it does not certify your fault labels or private-set independence.
6. Reconcile witnessed defects against detected, blocked-indeterminate, missed and
   not-exercised outcomes. Report correct implementations accepted/rejected/
   indeterminate separately. Retain all required scenarios in coverage denominators.
7. Inspect surviving faults and normalization losses. A missed critical defect
   blocks qualification. A critical behavior with insufficient evidence also blocks
   qualification; a high aggregate decision rate cannot waive it.
8. Document reviewer identity, review date, pre-freeze access, code/case/runtime
   hashes, fault witnesses, exclusions and sign-off. Store private partner evidence
   only in the agreed access-controlled location.
9. After revealing failures and fixing the comparator, treat this challenge set as
   development evidence. Use another independently reserved set for reevaluation.

This repository intentionally ships no supposedly secret holdout, invented
reviewer signature, vendor-qualification badge or statistical detection claim.
