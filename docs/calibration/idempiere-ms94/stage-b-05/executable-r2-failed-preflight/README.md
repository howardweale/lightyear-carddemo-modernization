MS94 B05 r2: preserved preflight preparation failure

The first r2 executable snapshot `80086f7960a7e3cc536fbdbf900ad49b07694ff6eb93c4920418af4580eb5267` failed before a native pair was allocated. Its trial configuration still named the r1 qualified-plan path. Report `6bf4d9a1df3ade5d8f2e427b58370b1f16df37f9776062f3ec902a1c54ea43be` remains unchanged and failed.

Zero model calls, zero native pairs, zero native resources and zero signed archives. Full-entry, gate and diagnostic replay are unavailable, not passed. The signed audit `786cd34143908ec10a5296f91262cec02674e1a8e7ed00416f34a694e64dba04` verified all 1085 frozen files unchanged and controller exit. Preflight body: 1.766 seconds; supervised total: 4.688 seconds.

The failed root was neither amended nor restarted. The correction changed the development configuration path, added an admission guard and a regression test for every native-plan path, then created a separate immutable executable root. That fresh preflight is reported separately under executable-r2. No failed outcome is replaced. B04 remains VOID. Operator review; not independent.
