# M0 qualification, October 7, 2026

Operator review; not independent attestation. Dedicated Ubuntu x86_64 VM
`ly-tsql-m0` only. Zero model calls and no Windows Docker commands.

Run 013 passes public-corpus M0 acceptance: 42 procedures, 25 trap families,
104 native SQL Server/PostgreSQL pairs. The 40 non-policy correct variants pass
across all declared cases; all 40 non-policy mutants are rejected in the expected
family. Ambiguous UPDATE FROM and unordered TOP remain policy-decision-required
for both variants, across five repetitions each. A correct route to a policy
decision is an accepted qualification outcome, never an equivalence claim.

The signed pair verdicts are unchanged: 38 equivalent, 41 divergent and 25
insufficient-evidence. Two additional setups exercise defensive branches of
`ci-unique` and `xact-abort`. Per-procedure coverage unions exact SQL source sites
across these cases. PostgreSQL statement IDs are unioned only for identical source
bytes; branch fractions are never added. Each module must have a retained native
case proving complete branch/handler coverage. All case assets and mappings are
bound by the run plan and every pair manifest. Offline replay reproduces both the
individual verdicts and the procedure-level acceptance.

The unique-index twin is now a top-level PostgreSQL procedure: its first insert
commits before the second statement, matching SQL Server's partial-commit behavior
when the second statement throws an unexpected CHECK violation. The public extra
case explicitly maps SQL Server 547 to PostgreSQL 23514 while preserving raw
messages. The XACT_ABORT twin records its return-status progression after a
successful insert; an error raised before that point retains zero. Empty
PostgreSQL handlers use a harmless PERFORM so the native profiler can observe them.
No coverage threshold was lowered and no source SQL Server procedure was changed.

Preserved attempts 011 and 012 exposed mismatches in the new setups and the twin
contracts; they remain failed validation evidence. The final run used fresh
databases and receipts. Historical run 010 and all earlier artifacts remain intact.
Attempt 011 took 51.565 seconds (12 pairs); attempt 012 took 33.602 seconds
(8 pairs). Both verified owned cleanup. These costs are additional to run 013.

Native run and cleanup: **286.619282855 seconds**. Reset-only SQL Server total:
80.216413417 seconds; PostgreSQL: 6.523153561 seconds, each over 104 resets.
This is a measured public-fixture throughput/reset benchmark, not performance
equivalence. The exact images and seven-control coverage qualification remain
bound in the signed plan. The coverage collector was unchanged.

Report content hash:
`a61623ae2da0f85611821fa35de761570f25e117dd8dacd3f912f9a3a2fe8b33`.
Recorder public-key hash:
`9f452baaa9778a88a2e9ddf1f7bfc5efea10f651383e92d4bfa2c07fcdeaae18`.
VM independent audit file hash:
`9d8159fc0549b65756f16ee926c3b278957e9fda925c98e679720138e07d7de5`.
Separate Windows offline audit file hash:
`812501cf38aabfb2d8a98d074bea24b71f8d5b465858cd1777b85a30ecccebaa`.
Both audits replayed 104 pairs. The local audit verified 1,792 retained files.
VM read-only inventory independently confirmed absence of the exact run owner's
containers, networks and volumes. No foreign resources were changed.

The JSON summary contains the signed acceptance hash, every case-manifest hash,
coverage fractions, reset measurements and classification. Archives, captures and
recorder keys remain local. No customer certificate or Tower release is implied.
