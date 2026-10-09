# B06 exact built-runtime catalogue prerequisite r1

Prepared for Howard's approved October 8, 2026 16:00-16:30 PDT window (23:00-23:30 UTC), latest start 16:05 PDT. Execution still requires the exact signed Tower decision. Operator review, not independent attestation.

This copies exactly 204 runtime archives (132,922,294 bytes) from retained image `sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`. It uses one read-only, network-free container with an explicit Python entrypoint: no inherited build entrypoint, Maven, Java, database, native pair or model call. Copy limit 900 seconds; cleanup reserve 600 seconds; no retries. Only owned resources may be cleaned. Raw archives remain local.

- Source commit: `8b010e333d6d0b409c21d376c46ca24408623006`.
- Snapshot: `0bbf2cdc9f1fca68c50dd9936c464569fdf424574d7b4c2104456f8e621f3f17` (291 frozen files).
- Plan: `5cf9502f702eff96bf31c9873ab4f5a2870b5b471033f6d3dbef6b9835e5bc7e`.
- Core: `c484c81bacfeca57b2020b5e4f47628f62121d1860e18a5ae9664b39797347a2`.
- Selection: `e448a715a38da620d42d40a6e50455640b8ee5240f6c7ae4de38172a050cb5df`.
- Tower public-key fingerprint: `65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240`.

Twelve offline extraction/authorization tests passed with imports from this frozen snapshot in 1.648 seconds. All frozen hashes verified before and after. Tests used temporary public fixtures and mocked Docker calls; no actual Docker command was run. The source increment's combined offline suite separately passed 68 tests.

The controller verifies the public commit's exact file bytes, snapshot and fresh signed Tower history before any Docker command. Each selected archive must match its measured size and SHA-256; independent replay checks the complete copied set. Failure is preserved, with no replacement output. The signed terminal report records the actual duration, copy catalogue hash, snapshot verification and owned cleanup.

This prerequisite does not authorize the five-path census, journey qualification or measurement. The previously requested 15:30 census did not start. The census needs its own complete executable plan, public binding, new window and Tower decision after this prerequisite succeeds. Earlier failures and the successful build-once practice remain unchanged. Native admission remains false.
