# B06 build-once runtime preparation r1

Current status: the authorized frozen practice passed; see the [terminal result and native handoff](terminal/README.md). No Tower evidence run, native qualification or model call. The preparation text below records the prospective design before that practice. Operator review, not independent attestation. Howard approved build-once preparation on October 8, 2026. Prior failures remain failed. B04 stays void. B05, work/ms94, template-r1 and J1 predicates are unchanged.

## Prospective amendment

The application is built once in a fresh container from the pinned image `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`. A uniquely labelled derived image preserves that build. Subsequent consumers use its exact image ID and execute the captured Java/Equinox command directly; they do not run Maven or javac. The digest of the derived image does not exist until the approved practice builds it. It will be recorded with the content-addressed runtime manifest before either consumer starts, and must be included in any subsequent evidence authorization.

All application entry names and bytes, including opaque nested JARs, source files, generated resources, manifest qualifiers and timestamps, remain exact within this build. No proposed source-bundle normalization is activated. JAR bundles also keep their original raw JAR hash. Folder bundles use the existing shared `bundle_content_view()` and its explicit run-output exclusions unchanged. The historical-content requirement was removed by Howard; no comparison to r4/r5b/r9/r10 gates this plan.

The sole per-run application exception is `org.idempiere.test/target/classes/org/idempiere/test/B06RuntimeCatalogTest.class`. It is overlaid read-only and bound separately by its compiled hash, captured application entry and bytes observed at definition by the practice agent. The expected origin is `file:/application/org.idempiere.test/target/classes/`; loading the copy in the opaque test JAR refuses. No source or entire JAR is exempt. Variant 1 is the build's original class. Variant 2 adds only a constant field; it is compiled outside /application during the build and has a separately recorded source, compiler, classpath and class hash. Both must execute the same no-database test successfully.

This in-process recorder is a practice diagnostic, not production JDI provenance. Every output explicitly leaves native admission false. It cannot qualify generated-class provenance or replace the independent observer needed for later candidate execution.

## Preserved runtime

The build restores the 102 proven source-only temporary JARs from the in-process captures to their original /tmp paths, byte-for-byte. Their names, versions and hashes remain exact across consumers. The existing source-only classifier still requires the narrow Tycho path, source header, no class or nested JAR entries, and no attributed loaded class.

Consumers use a read-only root filesystem with fresh, explicitly writable mounts only for results, the original OSGi configuration path, workspace data and test reports. Each configuration mount starts from the sealed build seed. The original dev.properties, surefire.properties and effective config.ini are checked. Java temporary files go to /results/java-tmp; the agent additionally preserves bundles at the original /tmp paths. This changes capture coverage, not the source-only acceptance rule.

The command is the captured fork argv with two declared additions: `-Djava.io.tmpdir=/results/java-tmp` and the separately sealed practice byte-recorder agent. The boot classpath remains the single measured Equinox launcher. The existing Tycho reader, producer and offline replay are exercised for each process. JDK, framework, launcher and /root/.m2 artifacts retain exact hashes. The derived image pins other filesystem dependencies as well.

## Proposed bounded practice

One fresh build container, then two serial consumer containers. No databases, native pairs, target candidates, external network, models or retries. Work cap 2,700 seconds: build at most 1,500 seconds, each consumer at most 600 seconds. Cleanup reserve 600 seconds. Approve a one-hour window; the runner refuses if fewer than 55 minutes remain. Failure stops the sequence and preserves output. Cleanup checks ownership before removing only this practice's containers and verifies the owned container/network/volume inventory is empty. The uniquely labelled derived image is deliberately retained locally for review, never uploaded by this runner.

At preparation freeze no practice had run or window been approved. The later approved practice and its result are recorded in the terminal report above. The runner requires `--run`, the exact plan, snapshot, public commit and UTC start/end. It verifies public Git bytes and frozen hashes before Docker. The frozen plan has no run authorization and no Tower request; its implementation is committed before snapshot assembly.

Acceptance requires all three captures and replays; exact 350-bundle census (1 system, 203 Maven, 44 application, 102 temporary); all 102 source-only records; unchanged application content except the one bound probe class; correct Tycho properties/launcher; no error file or warning outside the existing hash-bound baseline; unchanged frozen sources; and verified owned cleanup. The two consumer class hashes must differ. New warnings fail; existing accepted warnings remain visible.

Only after this frozen practice passes can a fresh exact Tower evidence request be prepared. That request must bind the same source commit, snapshot, common practice plan, resulting layer digest, manifest and successful practice report. It does not authorize B06 measurement. Generated-class proof, five-path census, journey qualification and final zero-model preflight remain separate gates.

## Offline validation

The new manifest reader successfully read preserved r10 output without changing it: 44 application bundles, 207 exact runtime artifacts and 102 source-only JARs. This is format compatibility only, not a successful new run.

Offline tests cover strict non-candidate entries (including nested JARs, manifest qualifiers and generated resources), exact per-run class allowance, immutable dependency/configuration checks, wrong origin/hash/loader, duplicate actual JVM definitions, frozen input mutation, insufficient windows, container ownership, serial read-only consumers, no retry and failure preservation. Docker lifecycle tests mock the subprocess boundary. A host-JDK test compiles only tiny public fixtures and the practice recorder. Native direct Equinox launch remains unverified until practice.

Validation: 82 focused offline tests passed on the development checkout, including the real host-JVM byte-recorder test and mocked Docker lifecycle tests. Frozen-import results are recorded with the assembled plan.

## Frozen preparation

- Source commit: `11d6ff4c91e76949f171a3a5385b7b59bee5597c`.
- Snapshot (777 files): `c2694d9b28d4af4226f0ce9693c87411768cc63ed52756a7805955b1da6743af`.
- Plan content: `3301aee1764e388b1f451163be3273d7ea1592db3e9b73f0bb8f1f93056512b3` ([plan](plan.json)).
- [Offline check](offline-check.json): 82 tests, zero errors/failures, 3.047 seconds with frozen imports. All 777 hashes checked before and after.
- Runtime files remain local under `work/b06-runtime-snapshots/build-once-r1`; the public plan contains hashes and original committed paths. No private archives are included.
- Docker window: not approved or scheduled. Derived image: not created. Tower request: not issued. B06 measurement: not launched.
