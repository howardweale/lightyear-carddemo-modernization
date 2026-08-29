# Auditor evidence-verification guide

## Verification procedure

1. Record the release commit and obtain the source-only pilot directory.
2. Run `./source-only-pilot.sh doctor` and retain the result.
3. Run `./source-only-pilot.sh verify`; it must rebuild all reference artifacts byte-for-byte.
4. Verify `source-analysis.receipt.json` against the intake, customer graph, and relationship ontology.
   Confirm the reference coverage contains all nine classes, including `hlasm`, `ims`, and `vsam`,
   while treating their relationships as bounded static observations rather than live runtime proof.
5. Verify `estate-assessment.json` against the graph, analysis, intake, and assessment policy.
   Confirm unresolved references remain visible and every slice requires human selection.
6. Inspect `pilot/reference-output/pilot.dossier.json` and verify its `content_sha256`,
   `analysis_sha256`, and `assessment_sha256`.
7. Hash each path in `evidence_artifacts` and compare it with the dossier's raw `sha256`.
8. Verify every readiness check is true while `mainframe_equivalent` and `production_ready` remain
   false.
9. Confirm model qualification is false unless eight current, independently sealed evaluations—two
   for each trusted workload—and an approved successful portfolio receipt are supplied.
10. Inspect `mainframe.preflight.json`; gates 6 and 8 must be blocked and gate 7 only
   `mechanism_ready`.

## Evidence interpretation

`pilot_ready: true` means a governed evaluator can install the package, inventory approved source,
inspect that intake's bounded typed estate, review an advisory evidence-first plan, verify existing
development evidence, and identify the exact live prerequisites. It does not mean the plan is
business-approved or that the original applications were compiled or executed.

The evidence registry binds raw file bytes so even a valid-looking replacement with a different
identity invalidates the dossier. Subsystem receipts retain their own validation and signing rules;
the pilot dossier does not weaken or replace them.

## Required exceptions

Any exception must identify the failed check, evidence owner, compensating control, expiration,
and approving authority. An exception cannot relabel simulated evidence as live or waive authorized
original execution for an equivalence claim.
