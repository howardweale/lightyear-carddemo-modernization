# B06 provenance review milestone

October 7, 2026. Operator review; not independent attestation.

The PR270/271 follow-up replaces broad artifact extraction with an inventory-first
workflow and a separately gated resolved-runtime extractor. Authoritative JDK
bytes come from lib/modules, not jmods. Forwarding admission now requires
lambda-factory/bootstrap provenance and the byte-bound defining host; application
name prefixes do not grant artifact exemptions. The rejected r11 plan is refused
before authority access or execution. r10 remains failed and all frozen evidence
is preserved.

Validation: 222 offline tests passed, 14 local-evidence tests skipped. All 19 new
portable review tests passed without local captures. A Windows/Linux CI workflow
runs the synthetic pool, LambdaForm, runtime-closure and rejected-plan controls.
No model calls, B06 Docker commands, native pairs or new signing authority.

Remaining: exact inventory snapshot/public commit/window and Tower decision;
measured scoped extraction; general pool-rule approval; complete generated-class
collector/replay proof; then a fresh five-path census and its separate Tower
decision. The Oct 9 end-of-day JDI time box remains in effect. J1 predicates,
expected outcomes, B05 and template-r1 are unchanged. No measurement readiness
or native qualification is claimed.

See [the detailed review record](calibration/idempiere-ms94/stage-b-06/preparation/review-pr269-271/README.md)
and [prospective general pool proposal](calibration/idempiere-ms94/stage-b-06/preparation/review-pr269-271/pool-proposal-v2.md).
