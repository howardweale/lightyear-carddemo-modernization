# Release-grade evidence checklist - 2026-10-18

This dated definition adds evidence requirements to `scenario_policy.release()`.
It grants no signing, execution, activation, import or Phase 2 authority.
Existing exact scenario, source, threshold, ordered decision and claim-scope
checks remain mandatory. Missing fields fail closed; signatures alone do not
make an engineering campaign releasable.

| Named unmet item | Evidence required | Reachability |
|---|---|---|
| `qualified-oracle-required` | The verified judge verdict explicitly records `oracle_status: qualified`. The trusted judge is responsible for qualifying its source oracle. | A qualified twin oracle can satisfy a twin claim. |
| `release-run-required` | That same signed verdict explicitly records `run_class: release`. Engineering runs cannot be relabelled by an unsigned caller. | A future release campaign on the twin can satisfy this. |
| `verified-retained-evidence-required` | Hash-bound public retention manifest and successful download verification receipt, exact asset URLs, sizes and SHA-256s, same campaign head and run. | Public twin evidence can satisfy this after durable retention verification. |
| `protected-main-campaign-required` | Hash-bound dated campaign snapshot: protected main push, strict required checks, all enumerated applicable workflows and child jobs complete successfully on the exact head. | Public twin CI can satisfy this after its full main campaign completes. |
| `production-review-proofs-required` | Existing signature/decision verification succeeds against an externally designated production review key; the signed verdict explicitly excludes fixture/disposable execution. | Real human review of twin evidence can satisfy this; CI rehearsal keys cannot self-designate. |
| `supported-claim-scope-required` | The signed verdict and review bundle both select `twin`, explicitly excluding native runtime claims. | Twin is supported. A z/OS-facing release remains blocked pending a typed native capture verifier. |

The first two facts and `release_grade` references are inside the judge-signed
verdict. Each reference is `{path, sha256}` relative to the supplied evidence
root. Traversal, missing files, changed bytes and duplicate JSON keys are refused.
A retention receipt is an observation of downloaded bytes, not a signature or
release authorization. The campaign snapshot schema is `release-grade-campaign/1`;
its fixture in `tests/test_release_grade.py` specifies the required fields.

These are hash-bound, judge-attested observations, not live GitHub queries or
GitHub-signed attestations. The judge must review exact workflow YAML, changed
paths, pagination, applicable jobs/steps and documented exclusions before signing
the snapshot references. `applicable_workflows` cannot be inferred from only the
`required-ci` shortcut. All observed applicable push workflows must be included.
The consumer cannot independently discover an omitted workflow from an offline
snapshot; that completeness claim belongs to the externally trusted judge.

`production_review_key_sha256` is a new optional, out-of-band argument to
`release()`. It is deliberately absent from evidence packets and current Factory
settings. Absent designation is an unmet gate. No deployed trust configuration is
changed by this patch. The key fingerprint is SHA-256 of the exact externally
supplied public-key bytes; key formatting changes therefore require re-designation.
The existing authority still verifies the current journal head, signatures,
contracts, order, typed conditions and outcome. CI may simulate external trust in
isolated unit fixtures; it cannot thereby create production authority.

A z/OS-facing claim needs matched-source native capture, provenance, runtime
configuration and an implemented typed verifier bound to the reviewed claim.
An unsigned `native: true` flag or a twin campaign cannot satisfy it. This patch
provides no native verifier and therefore refuses every z/OS-facing release.

The request-06 CI rehearsal now reports the separate missing items and continues
to require a non-releasable result. Earlier dated receipts retain their original
combined reason; they remain historical observations. New checklist text is
rendered from evaluated inputs, with fixture tests changing each item separately.
