# B06 transient source bundles — offline correction r6

Status: implemented and offline-tested; **no Docker, model call, new executable freeze, publication or Tower request** in this increment. Operator review, not independent attestation. The r5b failure and all prior snapshots remain unchanged.

## Failure preserved

r5b ran once for 391.297 seconds. Signed terminal report `f182d02a75c63c0c628e861014c3a41dbe59f46ad5c3db46426bfd2408c45fd9` records failure and completed cleanup. The exact worker error was:

```
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/tycho_wrapped_source10021272085316246407.jar'
```

Stage: `runtime_inventory.measure`, `p.stat()`, after the Tycho properties/command checks and JDK extraction, before completed inventory and signed resolution. Controller: `ValueError: runtime-worker-failed`. All 281 frozen files and signed start/terminal records verified; read-only owned-label container/network/volume inventories were empty. No rerun or reclassification.

## Implemented contract

The separate no-candidate closure agent records every bundle's symbolic name, version and presence of `Eclipse-SourceBundle`. While the JVM is alive, every file bundle beneath `java.io.tmpdir` is copied create-new to `/results/runtime-transient/<id>.jar`; size and SHA-256 are recorded. The bounded probe thread is non-daemon so shutdown cannot silently truncate the copy phase. A full class-origin transformer catalogue supplements the snapshot's class-to-bundle attribution; failure to write it halts the JVM.

Only a `/tmp/tycho_wrapped_source[0-9]+.jar` location with the source header, `.source` symbolic name, matching copied manifest identity, zero class entries, zero nested JARs and no loaded class attribution receives `transient-source-only`. The observed copy hash is evidence for this run, not an invariant between runs. Unknown temporary locations and ordinary missing files still refuse. No pattern alone grants trust.

Inventory records the identity and preserved-copy hash outside its class-provenance artifacts. The signed producer and offline replay both re-inspect the actual preserved bytes. Replay requires those local copies; a signed assertion of zero classes is insufficient. The runtime catalogue is bound through the signed inventory hash. Source archives and class-origin captures remain local.

New observation `/3`, launch receipt `/4` and resolved-runtime `/4` make the new evidence mandatory without reinterpreting old records. `/2` and Tycho `/3` replay remain unchanged. The previous exact `surefire.properties` capture and closed-key reader remain in force.

`transient_sources.bind_measured` independently replays both inputs before comparing. Proven source-only bundles match by symbolic name and version. Every other bundle keeps its exact path, identity and artifact hash; the launcher, framework and JVM artifacts also stay exact. This helper establishes no native admission on its own.

## Complete saved-location census

[Machine-readable audit](bundle-location-audit.json), SHA-256 `a91e4dd44ddb63790c95128cef6bfa0e19d88d1439ef1dbc9964c2b6b8a28e20`, lists all 349 non-system bundle locations from r5b and compares them with r4 window2. The system bundle is listed separately by count and is still bound through the framework artifact.

| Root | Count | Saved-evidence finding |
|---|---:|---|
| `/root/.m2` | 203 | All paths also occur in the preceding attempt; byte stability and Linux survival are not established by path equality. |
| `/application` | 44 | 41 unchanged paths; three timestamped folder paths differ. Four target/work folder copies were retained. |
| `/tmp` | 102 | All match the source-wrapper path shape; all 102 random paths differ between attempts. No source-only acceptance is inferred from the old observation. |
| Other | 0 | No other non-system bundle locations. |

The old run has no preserved source copies, header/version fields or complete class catalogue, so it cannot be upgraded or successfully replayed under the new contract. Its six-class catalogue is not a complete source-attribution census.

### Next failure found offline: non-source build timestamps

These three bundles changed path **and manifest bytes/version** from `13.0.0.202610081632` to `13.0.0.202610081715`:

- `org.adempiere.ui.zk`
- `org.adempiere.server`
- `org.idempiere.webservices`

All six manifest hashes and exact old/new paths are in the audit. These are non-source folder bundles. They do not receive the transient-source exception. Application `target/*SNAPSHOT.jar` files and the whole `org.idempiere.test` folder are build outputs too; unchanged paths do not establish unchanged contents. The saved catalogue does not provide complete prior/current byte inventories for them.

**Do not request another window yet.** Exact closure-to-measured matching will reject the known three timestamp differences. A prospective deterministic-build/runtime-reuse design must address this while preserving exact non-source bytes, paths and J1 predicates. Neither timestamp normalization nor a broader source allowlist has been implemented. A build qualifier alone would not prove reproducible JAR bytes or a stable test-folder manifest.

After resolving this offline blocker and selecting a fresh window, prepare one new Git-byte executable snapshot and exact public-bound Tower request covering both the retained Tycho-properties fix and this source-copy proof. Do not reuse r5b's expired authorization or frozen paths. No request has been installed or signed here.

## Validation

67 focused offline tests passed, covering all six requested controls, missing/tampered copies, manifest identity, nested JARs, duplicate source identity, signed producer/replay, changed ordinary bytes and cross-run source path/hash variation. The Java agent compiled with the host JDK.

The real host-JVM synthetic OSGi test demonstrated that the copy survives deletion of the original by `deleteOnExit`. This Windows JDK does not expose fork argv through `ProcessHandle.Info`; the full observation therefore refuses after capture. The test explicitly checks that refusal; it does not claim a Linux native observation or successful full closure. Synthetic producer/replay tests supply declared synthetic observations and ephemeral test signatures only. No production signing key was opened.
