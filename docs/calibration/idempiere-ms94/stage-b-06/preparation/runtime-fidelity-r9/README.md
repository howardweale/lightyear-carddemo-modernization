# B06 fidelity, warning baseline and frozen practice r9

Prepared offline at Howard's request. **No Docker or model calls, and no Tower
request.** The next practice requires Howard's approval of the frozen plan.
Operator review, not independent attestation. Historical failures are preserved.

## Shared content view

`bundle_content_view()` is used by capture, application identity (producer and
replay), and saved-content comparison. JARs are copied byte-for-byte and no JAR
entry is filtered. Folder views enumerate every file under the bundle root,
including Bundle-ClassPath, dev output, embedded POMs, localization, licenses,
scripts, source/resources and class files. Directory nodes carry no bytes;
folder identity is the full named-file map, also used for archived folders.
This explicit folder rule does not filter JAR directory entries.

Only these root-relative run-written paths are excluded from folders:

| Path | Reason |
| --- | --- |
| target/work | Test workspace, generated installation and mutable OSGi state |
| target/surefire-reports | Reports written by the test fork |
| target/surefire | Transient Surefire execution output |
| target/test-runtime | Generated Tycho test runtime |
| target/configuration | Generated test OSGi configuration |
| target/surefire.properties | Per-run launch properties, separately captured and bound |

No general `target`, `src`, `pom.xml`, `bin`, license, resource or extension
filter remains. Exclusions and reasons are included in each capture proof.
Mandatory Bundle-ClassPath entries still refuse if absent. Optional declared
dev output absence remains recorded and cannot supply a loaded class. Streaming
capture rechecks entry sets, presence and content hashes for mutation.
Historical folder-selection policies /1 and /2 remain replayable; new /3 uses
the common view. No historical capture is edited to fill missing entries.

## Actual saved comparison: incomplete, not 44/44

The same view was applied to the available r4-window2 and r5b full folder copies
and the r8b practice ZIPs. The full per-bundle report is
[saved-comparison.json](saved-comparison.json). The two old full copies match:

| Bundle | r4 files | r5b files | Practice files | Missing from practice |
| --- | ---: | ---: | ---: | ---: |
| org.adempiere.ui.zk | 1577 | 1577 | 1576 | 1 |
| org.adempiere.server | 141 | 141 | 140 | 1 |
| org.idempiere.webservices | 62 | 62 | 61 | 1 |
| org.apache.ant | 65 | 65 | 29 | 36 |

Each of the other 40 application bundles is reported individually as historical
content unavailable. There is no way to recover those bytes offline. A new
practice can capture all 44 faithfully, but cannot prove equivalence to missing
historical inputs. The common-plan six-check gate therefore remains closed
until the required comparison evidence exists or Howard explicitly approves a
prospective replacement baseline. No substitute baseline is assumed here.

## Warning baseline

All three logs have 74 severity lines: 71 WARN and three ERROR lines, collapsing
to the same **61 normalized messages**. The accepted list is their intersection;
there are no unaccepted messages in these logs. Keikai parent-POM packaging and
Log4j2 missing-implementation messages are included explicitly. New messages
block; logs are never suppressed or changed. INFO configuration lines containing
`MissingManifestStrategy = ERROR` are not severity messages.

Normalization is closed: ISO timestamps, per-run UUIDs, 14-digit OSGi qualifiers,
Tycho source temporary IDs, and stable root markers for /application and /root/.m2
(the remaining path is retained). No arbitrary numbers, package names, messages,
versions or severity are erased. [warning-baseline.json](warning-baseline.json)
retains every source line, source log hash, normalized message and intersection.
Baseline content hash:
`d4b0f432b3e62d9bf196f4be41876ba0ee7d5168a8accc5aa31e4c696fd5e0ab`.

## Exact-byte practice and evidence binding

Implementation is committed before freezing. `frozen_runtime.prepare` reads Git
objects from that full commit, creates an exact executable snapshot, and seals
one common plan binding source commit, file hashes, snapshot, image, baseline,
historical content, Java and Tower public-key hash. Practice runs with frozen
cwd/imports and verifies every input before and after execution. Results and
one-shot claims stay outside the snapshot. Limits remain 2700 seconds plus 600
seconds cleanup, one network-free container, no databases/native pairs/models.

The common plan has no mutable execution window. A later Tower authorization
binds the window as a separate artifact alongside that exact plan, snapshot,
public commit and recomputed practice review. Request generation and launch
both recheck all six checks and offline replay. The practice file hashes alone
are never treated as proof of historical equivalence. A failed check prevents
request generation; no plan rewrite is used to turn a failed practice into a
passed one. Any implementation change requires a new commit, freeze and practice.

No next-window request has been created. Frozen hashes and public commit are
recorded in the freeze README after publication and verification.

## Offline validation

106 focused tests passed in 16.384 seconds, including shared-view fidelity,
JAR exact copying, warning intersection/new-message refusal, snapshot/plan
binding, the full synthetic worker/producer/replay pipeline and host Equinox
lifecycle rehearsals. No Docker or model calls. This is not native qualification.
