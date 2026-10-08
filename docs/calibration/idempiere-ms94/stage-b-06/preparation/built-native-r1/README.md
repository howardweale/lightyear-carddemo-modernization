# B06 retained-runtime native launch r1

Status: implemented and checked offline; not native-qualified. Zero model calls and no Docker execution in this increment. Operator review, not independent attestation.

## Direct native launcher

New built-runtime plans execute the captured Java/Equinox command directly. They do not invoke Maven or javac. The two in-process practice agents are explicitly removed; suspended JDWP is added so the independent posting observer attaches before candidate execution. The actual process arguments must equal the plan, both live and in signed-receipt replay. UTC, real clocks, calendar guard and J1 predicates are unchanged.

The only Tycho properties edit is the single `__provider.tc.0` value from `B06RuntimeCatalogTest` to `LightyearOperationsTest`. All other property bytes remain exact. Separately bound class-file overlays enumerate the candidate, support and, for the existing outside-origin controls, `B06OutsideControl`, including their compiled inner classes. No package directory, resource or JAR exemption is introduced. Source hash, successful zero-model compilation record, exact output set, class-file identity and external-observer catalogue must agree. The existing signed compilation windows were verified while preparing these inputs.

The application container uses retained image `sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`, with a read-only root. Its inherited builder entrypoint is explicitly replaced by a sleeping carrier; the host invokes only the new direct worker. Capture and observer containers retain their existing base image. Immutable worker, selector and class inputs have no writable alias through `/results`. Writable configuration, workspace, reports and results mounts are separate. The observer receipt binds the image, read-only root, exact mount set and direct launch hash.

Before and after the JVM, the worker uses the same `bundle_content_view()` as capture/replay. All 44 application entry maps are exact except the explicitly enumerated compiled classes. The runtime artifacts, restored source JARs, active config, dev properties and sealed layer files are checked. Host replay binds these records to the receipt. These worker checks supplement the read-only image/mount enforcement and external JDI evidence; candidate-written output is not an independent observer.

Historical plans continue to replay with their original worker. No historical frozen worker or evidence was edited. The new runtime is prospective and must be selected and bound in fresh plans.

## Prepared qualification inputs

[preparation.json](preparation.json) binds 61 already compiled sources, 218 class references and all five census source selections. Private prepared inputs have content hash `60801b30807aae595de82a7ccf7371a3481e7d81784dfc94ccc3f8dda2f227f2`. This is input preparation, not a candidate run or qualification result. The old source/compilation files and all failures remain unchanged. Raw classes stay local.

The requested census reservation is October 8, 15:30 PDT through October 9, 02:30 PDT (`2026-10-08T22:30:00Z`â€“`2026-10-09T09:30:00Z`). It does not authorize execution. The five-path executable snapshot is not sealed: the complete runtime catalogue is still missing. A late or incomplete plan must not be launched to preserve the reservation.

## Exact catalogue prerequisite

Saved practice evidence includes all 44 application bundle captures, 27,834 extracted JDK class files, and six loaded-class blobs. The measured inventory also lists 204 non-application JARs under `/root/.m2` (203 bundle locations plus the launcher), containing 62,978 expanded class entries. Their hashes and sizes were measured, but their raw archives were not retained. Six observed class blobs or the old partial catalogue cannot establish the full closure.

[selected-archives.json](selected-archives.json), content hash `e448a715a38da620d42d40a6e50455640b8ee5240f6c7ae4de38172a050cb5df`, selects exactly those 204 archives (132,922,294 bytes). A new Tower-gated copy mode uses the retained image, a read-only root and no network. It streams only these exact files to a fresh local output, checks every size/hash, independently replays the copies, preserves errors and permits no retries. No Maven, javac, Java, database or native pair runs. Owned cleanup and the freeze are checked before signing the terminal report. Nothing is uploaded from that output.

The archive-copy Tower decision is explicitly a prerequisite decision, not census, qualification or measurement approval. A proposed 30-minute copy window will be bound in its separate plan. The requested census start has not been silently turned into an archive-copy authorization.

After the copy succeeds: assemble the complete byte catalogue and generated host bindings; seal/publish the five-path snapshot and obtain its exact Tower decision; run all five paths on both engines; then obtain separate journey qualification decisions/windows. Preserve first failures and unstarted slots. The five paths remain J1 retained, J1 duplicate invoice, J1 null crash/direct delivery, J2 retained, J3 materials retained. No qualification credit comes from the build-once practice or catalogue copy. The October 9 generated-provenance deadline remains.

## Offline validation

The final combined offline suite passed 68 tests, including 10 direct-launch tests, exact Git-byte archive freeze preparation, selected-archive controller guards and the historical extraction/qualification regressions. Tests use temporary public fixtures and mocked container/process execution: exact bytes, tampering, extra class/resources, wrong selector, missing authority, deadline, mount aliases, no inherited builder entrypoint, timeout secret removal, and replay bindings. This is not a claim of native qualification.
