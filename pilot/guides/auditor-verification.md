# Auditor evidence-verification guide

## Verification procedure

1. Record the release commit and obtain the source-only pilot directory.
2. Run `./source-only-pilot.sh doctor` and retain the result.
3. Run `./source-only-pilot.sh verify`; it must rebuild all reference artifacts byte-for-byte.
4. Inspect `pilot/reference-output/pilot.dossier.json` and verify its `content_sha256`.
5. Hash each path in `evidence_artifacts` and compare it with the dossier's raw `sha256`.
6. Verify every readiness check is true while `mainframe_equivalent` and `production_ready` remain
   false.
7. Confirm model qualification is false unless eight current, independently sealed evaluations—two
   for each trusted workload—and an approved successful portfolio receipt are supplied.
8. Inspect `mainframe.preflight.json`; gates 6 and 8 must be blocked and gate 7 only
   `mechanism_ready`.

## Evidence interpretation

`pilot_ready: true` means a governed evaluator can install the package, inventory approved source,
inspect the composite estate, verify existing bounded development evidence, and identify the exact
live prerequisites. It does not mean the original applications were compiled or executed.

The evidence registry binds raw file bytes so even a valid-looking replacement with a different
identity invalidates the dossier. Subsystem receipts retain their own validation and signing rules;
the pilot dossier does not weaken or replace them.

## Required exceptions

Any exception must identify the failed check, evidence owner, compensating control, expiration,
and approving authority. An exception cannot relabel simulated evidence as live or waive authorized
original execution for an equivalence claim.
