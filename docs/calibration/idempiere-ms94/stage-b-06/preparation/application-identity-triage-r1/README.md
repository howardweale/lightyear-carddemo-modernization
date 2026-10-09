# B06 application identity triage — October 8, 2026

Completed offline on October 8 (America/Los_Angeles). Zero Docker commands,
model calls or Tower requests. Operator review, not independent attestation.
This comparison diagnoses r9/r10; there is no historical-content requirement.
No normalization or exclusion has been activated. All frozen results remain unchanged.

## Classification and decision

All **42 differing entries in the 21 source bundles** are accounted for:

| Category | Entries | Bundles | Finding |
| --- | ---: | ---: | --- |
| (a) Class file | 0 | 0 | No changed class exists to run javap against |
| (b) Properties timestamp comment | 21 | 21 | Only line 2's generated UTC timestamp changes |
| (c) Generated descriptor with build ID | 21 | 21 | MANIFEST Bundle-Version and Eclipse-SourceBundle host qualifier change |
| (d) Other resource | 0 | 0 | No source-bundle resource difference outside (b)/(c) |

There are no (a) or (d) examples in these 21 bundles; inventing three would be
incorrect. Thus no javap invocations were needed. There are no observed class
byte changes to attribute to bytecode, constant-pool or attribute ordering.
All source-bundle entry sets are identical. Applying the **draft-only** two-rule
proposal makes all 42 source-entry pairs equal; all other bytes remain exact.

The separate test bundle has seven changed non-candidate entries: two (b),
three (c), and two (d) opaque nested JAR files. Nested inspection finds identical
entry sets: source JAR 200 entries (manifest + localization differ), binary JAR
365 entries (only manifest differs); all **324 nested class entries are identical**.
This classification does not silently recursively normalize a JAR resource.
Under the requested exact non-candidate test-bundle rule, the seven differences
still refuse. The build-once draft addresses that blocker. The source-bundle
(b)/(c)-only branch permits the enumerated normalization proposal; it does not
approve it or solve the test-bundle exactness requirement by itself.

## Counts per bundle

| Bundle | Entries | (a) | (b) | (c) | (d) |
| --- | ---: | ---: | ---: | ---: | ---: |
| org.adempiere.base.callout.source | 63 | 0 | 1 | 1 | 0 |
| org.adempiere.base.process.source | 213 | 0 | 1 | 1 | 0 |
| org.adempiere.base.source | 3018 | 0 | 1 | 1 | 0 |
| org.adempiere.install.source | 71 | 0 | 1 | 1 | 0 |
| org.adempiere.payment.processor.source | 14 | 0 | 1 | 1 | 0 |
| org.adempiere.pipo.source | 39 | 0 | 1 | 1 | 0 |
| org.adempiere.plugin.utils.source | 15 | 0 | 1 | 1 | 0 |
| org.adempiere.replication.source | 24 | 0 | 1 | 1 | 0 |
| org.adempiere.report.jasper.source | 26 | 0 | 1 | 1 | 0 |
| org.adempiere.server.source | 76 | 0 | 1 | 1 | 0 |
| org.adempiere.ui.source | 114 | 0 | 1 | 1 | 0 |
| org.adempiere.ui.zk.source | 1253 | 0 | 1 | 1 | 0 |
| org.apache.ecs.source | 143 | 0 | 1 | 1 | 0 |
| org.compiere.db.oracle.provider.source | 19 | 0 | 1 | 1 | 0 |
| org.compiere.db.postgresql.provider.source | 20 | 0 | 1 | 1 | 0 |
| org.idempiere.hazelcast.service.source | 16 | 0 | 1 | 1 | 0 |
| org.idempiere.tablepartition.source | 16 | 0 | 1 | 1 | 0 |
| org.idempiere.test | 531 | 0 | 2 | 3 | 2 |
| org.idempiere.webservices.resources.source | 21 | 0 | 1 | 1 | 0 |
| org.idempiere.webservices.source | 86 | 0 | 1 | 1 | 0 |
| org.idempiere.zk.billboard.source | 38 | 0 | 1 | 1 | 0 |
| org.idempiere.zk.extra.source | 10 | 0 | 1 | 1 | 0 |

## Examples — differing lines only

Three distinct source-bundle examples of each observed category follow. The full
per-entry hash/line inventory is in triage.json; no whole class/resource is printed.

### Category (b)

`org.adempiere.base.callout.source/OSGI-INF/l10n/bundle-src.properties`

- r9 line 2: `#Thu Oct 08 19:43:06 UTC 2026`
- r10 line 2: `#Thu Oct 08 20:01:50 UTC 2026`
`org.adempiere.base.process.source/OSGI-INF/l10n/bundle-src.properties`

- r9 line 2: `#Thu Oct 08 19:43:07 UTC 2026`
- r10 line 2: `#Thu Oct 08 20:01:51 UTC 2026`
`org.adempiere.base.source/OSGI-INF/l10n/bundle-src.properties`

- r9 line 2: `#Thu Oct 08 19:43:04 UTC 2026`
- r10 line 2: `#Thu Oct 08 20:01:48 UTC 2026`


### Category (c)

`org.adempiere.base.callout.source/META-INF/MANIFEST.MF`

- r9 line 6: `Bundle-Version: 13.0.0.202610081942`
- r10 line 6: `Bundle-Version: 13.0.0.202610082001`
- r9 line 8: ` 81942";roots:="."`
- r10 line 8: ` 82001";roots:="."`
`org.adempiere.base.process.source/META-INF/MANIFEST.MF`

- r9 line 6: `Bundle-Version: 13.0.0.202610081942`
- r10 line 6: `Bundle-Version: 13.0.0.202610082001`
- r9 line 8: ` 81942";roots:="."`
- r10 line 8: ` 82001";roots:="."`
`org.adempiere.base.source/META-INF/MANIFEST.MF`

- r9 line 6: `Bundle-Version: 13.0.0.202610081942 | Eclipse-SourceBundle: org.adempiere.base;version="13.0.0.202610081942";r`
- r10 line 6: `Bundle-Version: 13.0.0.202610082001 | Eclipse-SourceBundle: org.adempiere.base;version="13.0.0.202610082001";r`

## Test-bundle rule (proposal only)

Bind the complete non-candidate entry map exactly. Exclude from that map **only
an enumerated per-run class output**, never a filename wildcard, directory, source
file, source JAR, binary JAR, POM, descriptor or other resource. The declaration
must bind the exact class-entry list, source hashes, compiler/image/classpath,
compiled-byte hashes and trusted observed defining path/loader/class bytes;
independent replay must recheck those records. An unlisted inner class or a
missing/different observed hash refuses. Exemption from the base identity is
not exemption from byte binding.

For the retained closure practices the sole proposed top-level exclusion is:
`target/classes/org/idempiere/test/B06RuntimeCatalogTest.class` (2,306 bytes,
SHA256 `5637bcde6f2cee5dc25f7915ff0d9330ee5523dbf83d733aa4c7b02bb4d573b1`).
It is identical in r8b, r9 and r10. **No exclusion has actually been applied**.
For a later candidate launch, the separately declared class is expected to be
`target/classes/org/idempiere/test/LightyearOperationsTest.class`; any additional
compiled classes require explicit per-run list/binding. This is a proposal,
not evidence that that candidate class appeared in these closure runs.

R9/r10 also contain that same probe class inside
`target/org.idempiere.test-13.0.0-SNAPSHOT.jar!/org/idempiere/test/B06RuntimeCatalogTest.class`.
That entire nested archive remains byte-exact; do not exclude it or normalize
its ZIP bytes recursively. The observed defining origin must be the admitted
`target/classes` entry, not this duplicate. Shadow loading must fail.
R8b's prior filtered folder capture lacks the nested JAR; no claim about its
absence in the live runtime follows. R4-window2/r5b and failed r8 retain the test
case name, but no full test-bundle capture; their actual class-entry/hash list
cannot be asserted. test-entry-inventory.json records each availability result.

Removing the one probe class from comparison leaves **all seven non-candidate
differences**. No class-only exclusion can make these rebuilt captures equal.
Future candidate source/compilation must be outside the bound bundle root,
with an explicit class overlay; do not copy changing source/build files into
an otherwise exact base bundle.

## Local preservation and validation

Every differing entry from both runs is preserved: **98 files, 21,399,748 bytes**,
under `work/b06-application-identity-triage-r1/differing-bytes/` in this checkout.
Each file is verified byte-for-byte against its source ZIP entry; hashes and
original archive hashes are in triage.json. This includes both changed nested
JARs and therefore all their contents. Raw bytes stay local, outside Git and
outside all frozen roots. The local folder also holds triage.json and
 test-entry-inventory.json. Review-folder preservation is not public release.

Five proposal tests passed: timestamp line restriction; exact host/version/roots;
unchanged import/resource/class behavior; unapproved names/comments rejected;
base-version changes not normalized. All 42 actual source-entry pairs also
passed the proposed normalization offline. No source normalization has been
added to the active application_identity module or its consumers.

Next review documents: [normalization proposal](source-normalization-proposal.md),
[build-once amendment and practice draft](build-once-draft.md).
