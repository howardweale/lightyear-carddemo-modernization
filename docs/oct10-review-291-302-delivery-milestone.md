# October 10, 2026: first review-corrections delivery milestone

Howard requested publication and merging of the first fixes from the review of
PRs 291–302. This milestone accompanies PR #308. Merge authorization is subject
to completed green checks on its final head; a queued, running, cancelled or
failed required check is not acceptance. This document does not authorize
engineering execution or claim that the remaining review work is complete.

## Delivered behavior

| Area | Change | Practical result |
|---|---|---|
| Engineering execution | Unconditional review hold in supervisor, child and native execute entrypoints | Previous October 11 approval cannot be used through these entrypoints; amended observer and renewed approval are required |
| Evidence admission | Engineering refusal inside census and direct stream replay, including marker ancestry | Relocating raw engineering artifacts does not make them admissible |
| Content verification | Loader bytes checked against SHA-256 before caching; archive/member/depth bounds before decompression | A mismatched loader cannot populate a trusted cache entry; oversized declared archives fail early |
| Host regressions | Explicit Windows/Linux JDK selection and enabled Corretto 21 JDI CI | Captured return and startup dispatch paths actually run on Linux |
| Stress configuration | Explicit recorded 192 MiB heap by default | Host stress can target the old heap; native-volume stability is not yet proved |
| Source bytes | LF restored in the two named development files; prospective changed-source guard | New changed Python/Java sources cannot introduce CRLF; historical pinned files remain unchanged |

## Validation and identity

Implementation commit: `489a20702577151653ab36bfe139f153166686d0`.
Documentation-only additions to this PR do not change those implementation bytes.

- Local Corretto 21.0.10_7: 94 tests in 34.796 seconds; 83 passed, 11 explicit skips.
- [Linux host/JDI run 38091408357](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38091408357): 94 tests in 50.376 seconds; 84 passed, ten optional historical-evidence skips. Real captured-return and queued-start regressions passed; the LF step passed.
- Ten skips require local historical evidence fixtures. The additional Windows
  skip is ProcessHandle.Info command/argument metadata unavailable on that JVM.
- Diff and source-LF checks passed. Byte comparison established that the two
  requested native/replay files differ solely by CRLF-to-LF normalization.

These results are evidence for the focused implementation, not a claim that every
repository workflow has completed. Final-head checks and actual merge state are
visible on [PR #308](https://github.com/howardweale/lightyear-carddemo-modernization/pull/308).
The merge must wait for completed green checks, even though the focused JDI run
above already passed. No rule or workflow is weakened to obtain a merge.

## Boundaries and remaining work

The [engineering hold](b06-engineering-review-hold.md) remains in force after
merge. No native/container attempt, model call, Tower request, operational key
access, new approval receipt or machine configuration change was performed.
Sealed B06 checkouts and historical evidence retain their original bytes.

The [review register](review-291-302-first-fixes.md) lists the unfinished work:
memory-bounded observer and telemetry, separate engineering signing key, exact
source/observer approval binding, real native adapter proof, full-volume stress,
r3 metadata supplement, alternatives measurements, business-rule corrections,
remaining packaging/equality/adopter work and historical CI audit. These are
not implied complete by this first batch. No qualification, measurement or
production release credit is claimed.
