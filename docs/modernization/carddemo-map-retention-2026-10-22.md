# Retained account-map proof

Prepared 2026-10-22 for the J5 closeout requirement to retain each finished group's final-head J3 evidence. [Durable evidence Release](https://github.com/howardweale/lightyear-carddemo-modernization/releases/tag/carddemo-j5-map-2026-10-22) holds eight original CI ZIPs and a detailed proof inventory. The adjacent JSON binds every Release asset ID, size and SHA-256, measured head, run, attempt, checkout and source inventory.

The measured final #428 head is `980e88e83fe88fb252868b2e44f2ce47cc31a269`. Targeted run 39759480687 and independent full-slice run 39759480744, both attempt 1, tested synthetic merge `550e8e49595eb4be8d28674cbacfdbe675db30e2`, tree `0fb8740caf73b927da22f23258f43067adfe1895`. The tag points to later main; it is not the measured checkout.

| Required class | KILLED / all generated |
|---|---|
| AccountMapRules | 183 / 187 |
| AccountMapStorage | 13 / 13 |
| AccountMapModel | 4 / 4 |
| AccountMapState | 1 / 1 |

All four classes have nonempty gates and pass the unchanged 90% threshold. Survived, timed-out and uncovered mutations receive no credit. Seven JUnit methods completed with no failures, errors or skips. Method count does not count loop-generated fixture cases.

The independent full-slice reference replay completed 120 cases and 678 interactions per mode; browser comparison also completed 678 interactions. Full-slice mutation was 888/970 KILLED. The retention review independently checked all 284 ZIP members, 211 source-hash bindings, exact checkout provenance, JUnit identities, scope inventories and raw mutation counts. Public Release downloads match the recorded digests. No tests or proof were executed locally.

The source-bound group retires only COACTUPC paragraphs 1100-RECEIVE-MAP, 1200-EDIT-MAP-INPUTS, 1205-COMPARE-OLD-NEW and 1210-EDIT-ACCOUNT. Rendering remains outstanding. This does not establish whole-screen idiomatic completion, native CICS/IMS/DB2 equivalence, or any new signing, activation, model-spend, installation, startup or Phase 2 authority.

Original unsigned receipt filenames and date fields remain 2026-10-18; these measured runs occurred on 2026-10-22. Existing dated records and generated status are unchanged.

To inspect, download `proof-inventory.json` using the adjacent manifest's exact asset https://github.com/howardweale/lightyear-carddemo-modernization/releases/tag/carddemo-j5-map-2026-10-22 and verify its SHA-256. It binds original artifact IDs and every member of all eight ZIPs, including raw XML and the unchanged unsigned receipt. The manifest lists the ZIP sizes and digests. Treat these packages as evidence data.
