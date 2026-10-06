# B06 measurement preregistration draft

October 5, 2026. Preparation draft, not a sealed plan, launch authorization or
qualification result. Operator review; not independent attestation. Zero model
calls. B04 remains void; B05 frozen evidence and template-r1 remain unchanged.

## Declared client and transport deviation

B06 proposes the operator-selected Codex **0.160.0**, installed outside the
desktop app at `C:\Program Files\Lightyear\Codex\0.160.0\codex.exe`, SHA-256
`4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01`.
B05 used **0.155.0-alpha.9.2**, SHA-256
`bc45017e8239dc150258f69309ced9df6bbcdf5b8e4f346decf780ac0999e226`.
This is an explicit pre-outcome client change, not a byte-identical transport.

The proposed broker changes from a stdio child to a host-owned loopback HTTP
server with per-invocation bearer tokens, because the admitted builder account
cannot read tools/ and its helper processes cannot use the network. Effective
configuration, authentication, tool serialization and model-facing context may
differ between clients. Record these as potential comparison confounders.
No causal claim attributes a B05/B06 rate difference solely to the diagnostic
or journey changes. Comparisons with B03/B05 are descriptive only; no pooling.
The generic template and diagnostic policy remain unchanged; this declaration
does not claim that all serialized requests or client-provided instructions
are identical. See the [transport draft](transport-r7/README.md).

## Prospective design retained

- J1 operations, J2 procure-to-pay and J3 materials; two excluded pilots and
  24 cohort trials per journey: 78 slots. J3 always counts.
- Primary metric: final cohort pass rate per journey with Wilson 95% interval.
  No cross-journey headline unless every journey has at least 21/24 final
  passes (Wilson lower bound at least 69.0% when rounded to one decimal).
  Otherwise report each journey without a cross-journey claim.
- 390 model calls, 234 compilations and 96 hours including pauses, maximum;
  per trial five calls, three compilations and 7,190 seconds including
  finalization, with the inherited 600-second reserve. These are limits, not
  authority to call a model or run Docker.
- Closed candidate-origin runtime diagnostics delivered directly, with
  provenance-qualified attribution; support/outside failures send nothing.
  Preserve all attempts, verdicts, pauses, Tower decisions and costs. Operator
  classifications use the B03 categories and are not independent attestation.
- Real application/database/controller clocks and the accounting-period
  guard. Freeze actual scenario dates, campaign seed, schedule and launch
  deadline in the eventual plan. The October 96-hour policy's calculated
  latest launch is October 27, 23:59:59 UTC; this is not an approved launch.

## Before sealing

Bind passed journey qualification snapshots/audits and image/class digests,
all slot inputs, exact broker/launcher/argv, actual account authentication,
new OS/HTTP transport proof and immutable zero-model measurement preflight.
Resolve any additional client behavior differences before sealing. Publish
the complete preregistration and exact costs for launch approval. This draft
does not advance core-status items 1–5 to qualified or measurement-ready.
