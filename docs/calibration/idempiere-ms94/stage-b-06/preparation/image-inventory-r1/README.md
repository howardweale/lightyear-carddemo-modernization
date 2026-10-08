# B06 pinned-image inventory, first inventory-only pass

Prepared October 7, 2026 PDT. Operator review; not independent attestation.
This proposal does not authorize Docker execution. An exact fresh Tower decision
must bind its published commit, plan, snapshot and window before any Docker call.

Source commit: `1472d0bf09e84b2a5b881b87163254274713bfc6` (merged review fixes).
The immutable local snapshot contains 429 files copied from exact Git bytes and
the plan core. Only these public metadata files are newly published; all source
bytes are already public. No private class files, captures, keys or reference
sources are included.

| Binding | SHA-256 |
| --- | --- |
| Plan | `4257fceb455c97598d7abb495b6968a9e7bebe28d08edba5ea08bba3c421656f` |
| Snapshot | `2a803f7479f9388cb69598947812f48afafdd81283cd749ed505cfccd4d112f0` |
| Confirmed Tower public key | `65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240` |

Proposed window: **2026-10-08 02:00–02:30 UTC**, October 7 **7:00–7:30 PM PDT**.
Latest start: 02:05 UTC / 7:05 PM PDT. No late launch or extension.

One container from image
`sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`.
Inventory paths, sizes, hashes, archive class-entry counts and nested-archive
counts under `/application`, `/root/.m2` and the resolved image JDK. No class
copies, target JVM, database, native pair, model call or network. Maximum work
900 seconds; cleanup reserve 600 seconds; no retry. An active-container overlap
refuses execution. Cleanup is limited to the exactly owned container.

Append-only progress and per-root counts survive failures. The terminal result
must retain every outcome and verify actual owned cleanup and all frozen hashes.
An inventory is not a runtime-closure catalogue or native provenance proof.
The measured inventory informs a separate scoped extraction and Tower decision.
The five-path census is not authorized by this request. Historical failed
extractions and r10/r11 evidence remain unchanged.

Validation: 25 offline tests and six included tests from the immutable snapshot
passed; all 429 hashes unchanged. Synthetic negative tests print deliberate
failure messages but never call Docker. Two initially mistyped test-module names
were corrected before this validation; the result is not native qualification.
See `preparation-validation.json`, `core.json`, `snapshot.json` and `plan.json`.
