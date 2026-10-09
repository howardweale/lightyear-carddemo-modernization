# Runtime closure r7 — review plan

Window selected by Howard: **October 8, 2026, 11:15 AM–12:15 PM PDT**
(18:15–19:15 UTC). Latest start 11:20 AM PDT (18:20 UTC). No extension.

- Plan content SHA-256: `66e806e3fbe9f5513bcb6c600378bed63a72210349b96b1fcfea2f4302b03b18`.
- Immutable snapshot SHA-256: `168d35d63031820e3ff222ff0a9454bc32db7fc14ab1fa9b36ac5e2267d645ba`.
- Snapshot: `work/b06-runtime-snapshots/closure-r7`, 285 Git-byte files.
- Source commit: `ea1fd919b39fa85cd067250aa8392d73fbbe5677`.
- Pinned image: `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`.
- Tower fingerprint: `65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240`.

One network-free runtime-closure container only: offline agent compilation,
no-database Tycho/Equinox JVM, in-process transient/application bundle capture
and JDK extraction. Maximum 2,700 runtime seconds plus 600 seconds cleanup
reserve. Zero retries, databases, native pairs or model calls. No five-path
census, qualification or measurement authorization.

This single plan covers the exact Tycho properties/fork fix, strict transient
source-only proof and prospective application content identity. The accepted
content rule and coverage limitations are in [the r7 report](../application-content-r7/README.md).
Native admission remains blocked pending complete evidence. r4/r5b and all
older failures remain unchanged.

All 285 frozen hashes and critical imports verified. 80 development tests passed;
25 identity/producer/replay tests additionally passed using only frozen production
imports and in-memory synthetic signer keys. The external test harness supplies
fixtures, not production modules. An initial broad frozen-root test invocation
could not import test-only preparation/audit modules; another hit sandbox temp
permissions. These are recorded preparation-test failures, not native attempts.
The final scoped check used the flat frozen inventory module under its test import
alias and did not change the snapshot. No production key was opened.

Review preparation only. This document and plan do not authorize execution.
Before a live request or launch: publish and byte-verify the exact commit;
then obtain Howard's fresh Tower decision binding that commit, plan, snapshot
and this window. No Docker commands or live Tower request occurred during
preparation. Operator review, not independent attestation.
