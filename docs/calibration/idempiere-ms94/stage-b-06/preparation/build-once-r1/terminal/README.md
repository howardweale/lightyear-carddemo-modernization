# B06 build-once r1 terminal result and native handoff

Operator review, not independent attestation. Practice passed; native admission remains false.

The single authorized October 8 practice built one retained image and ran two direct Java consumers in 1,031.157 seconds (17 minutes 11 seconds). Each capture and offline replay passed. All three processes observed 350 bundles: one system, 203 Maven, 44 application and 102 temporary source bundles. All 102 qualified as source-only. All 44 application bundles matched the built layer exactly except the one explicitly bound probe class. The two probe variants had different compiled hashes. No new warnings or error records occurred; accepted baseline warnings remain visible.

The independent terminal replay passed. Handoff preparation subsequently replayed the saved outputs again through the frozen modules in 21.484 seconds; it did not execute Java or a container. All 777 frozen files remain unchanged. Read-only Docker queries for the exact practice owner confirmed no owned containers, networks or volumes. The derived image is intentionally retained locally. Zero model calls, databases or native pairs. The launcher's process exit code was unavailable (`null`); success is established by the worker output, complete report and replay, not an inferred OS exit code.

| Binding | SHA-256 or commit |
| --- | --- |
| Public preparation commit | `2bc03730948e6c09597a4a5d474c3d621f4d7081` |
| Source commit | `11d6ff4c91e76949f171a3a5385b7b59bee5597c` |
| Immutable snapshot | `c2694d9b28d4af4226f0ce9693c87411768cc63ed52756a7805955b1da6743af` |
| Common plan content | `3301aee1764e388b1f451163be3273d7ea1592db3e9b73f0bb8f1f93056512b3` |
| Practice report file | `f6dcb70cb7c5fb722ac4edf79a82151d91e9d4201407fc22ba49c50eb6550281` |
| Retained image | `sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268` |
| Layer manifest content | `b32ae4770cb0f0b5e4bd6181016f2224ebea1ad666acfb8cdbca785a09dd70d2` |
| Accepted practice summary content | `cdc9eab1907df45b6bfe3c783e828fdb4084b56f47300b2f7787c82b60b34538` |
| Prospective handoff content | `cc713970652cc14c347de60cc30d7ce1b2ba6bb42d80e623bd2b41c22f4f1b64` |

The [accepted summary](accepted-practice.json) and [prospective handoff](prospective-handoff.json) are hash-bound offline records, not signatures or launch authorizations. They contain no archived class bytes, captures, credentials or private references. The new handoff code is outside the frozen snapshot. It imports the frozen validator/replay during the actual handoff check; it does not alter the common plan or authorize rebuilding the image. These new handoff files have not been published.

## Remaining B06 work

1. Implement an explicit Tower-gated evidence adapter for the retained image and unchanged frozen consumer worker. Bind the new host adapter separately, together with the existing source, snapshot, common plan, image, manifest and report. A new window and exact Tower decision are required. The current prospective handoff is deliberately non-executable; no request is in the inbox.
2. Integrate the retained runtime with the native journey worker. The current native worker still invokes Maven. Replace that path prospectively with direct Java/Equinox execution, exact per-slot test properties and compiled candidate overlays, and suspended external JDI attachment. Enumerate every permitted overlay; bind all other entries exactly. Practice agents are not production provenance evidence. Keep J1 predicates unchanged.
3. Complete the native artifact/class catalogue and generated-class provenance proof, then prepare the five-path census: J1 reference, duplicate-invoice mutant, null-crash/direct delivery; J2 reference; J3 materials reference; both engines. Preserve all generated-class records. The October 9 generated-provenance time box remains; report an alternative if it cannot be demonstrated by then.
4. Run separately approved J1/J2/J3 qualification groups, then the zero-model measurement preflight. B06 measurement needs its own completed admission and authorization. No practice result supplies qualification credit.

The handoff guard and adjacent contract/replay/request tests passed: 17 tests, zero Docker executions or model calls. Coverage includes altered source/snapshot/plan hashes, tampered records, inherited model/native admission, absent driver/window, insufficient time reserve and unauthorized rebuild scope. This validates preparation checks only; it does not test a nonexistent evidence driver.

B04 remains void. B05, work/ms94, template-r1, J1 predicates and all earlier failed evidence are unchanged. The completed practice monitor is paused.
