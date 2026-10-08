# Practice r8b: six pre-window checks

**Not ready for an evidence window.** The practice pipeline/replay succeeded,
but that result did not establish cross-run content equivalence, warning-free
execution or an exact published commit/snapshot/plan binding. This follow-up
checks preserved output only: zero Docker commands or model calls; no Tower
request. Operator review, not independent attestation.

1. **Census passed:** 350 bundles: one system, 203 `/root/.m2`, 44 `/application`,
   102 `/tmp`, zero other roots. Exact expected split.
2. **Source-only qualification passed: 102/102.** Re-executed the offline
   classifier against preserved copies and the full recorded class catalogue.
   All require the exact temporary-name shape, `.source` symbolic name,
   Eclipse-SourceBundle header, matching copy hash, zero class entries, no
   nested JARs and no loaded class attributed to the bundle.
3. **Application identity is not established.** Both r4-window2 and r5b retain
   complete contents for only four of the 44 application bundles; 40 cannot be
   compared. Each of the four has an entry-set difference against practice:

   | Bundle | Old entries | Practice entries | Missing entries |
   | --- | ---: | ---: | ---: |
   | org.adempiere.ui.zk | 1577 | 1576 | 1 |
   | org.adempiere.server | 141 | 140 | 1 |
   | org.idempiere.webservices | 62 | 61 | 1 |
   | org.apache.ant | 65 | 29 | 36 |

   The first three lose their embedded META-INF/maven/.../pom.xml. Ant loses
   its embedded POM plus 35 resources (localization, licenses/about files, bin
   scripts and etc stylesheets). All common entries match after the allowed
   manifest normalization; there are no changed common entries or additions.
   Nevertheless, **39 missing entries means the exact entry-set check fails**.
   The folder selector filters `pom.xml` at all depths and begins traversal at
   Bundle-ClassPath/META-INF/dev roots, omitting root resources when `.` is not
   a classpath entry. This is a capture defect, not an allowed metadata change.
   No wider normalization or exception is approved by this audit.
4. **Tycho evidence passed:** exactly one saved runtime/surefire.properties,
   byte-identical to the effective copy; testpluginname=org.idempiere.test.
   The fork uses `-testproperties /application/org.idempiere.test/target/surefire.properties`.
   `-jar` and observed java_class_path identify the same single Equinox launcher
   1.6.500.v20230717-2134, inventoried SHA-256
   `28aaab5d9779244be3f4f2bbf65126db56f8c90eabeea00ee16736012fdad888`.
5. **No error file, but not warning-free.** Neither closure-error.json nor
   worker-error.json exists, even empty. Maven log has 71 WARNING lines:
   44 missing-digest, 10 weak-digest, 13 wildcard Service-Component, two invalid
   POM and two default-package import warnings. It also has three error-level
   lines: two invalid Keikai parent-POM packaging messages and the Log4j2
   missing-implementation message. Maven still returned BUILD SUCCESS. We do
   not suppress these messages or treat successful exit as satisfying this check.
6. **Exact publication/Tower binding is not yet established.** The 12 copied
   worker sources and all host-file hashes still match practice-plan.json
   `b65272f5de7b054a6cfe0fb9894421c51d445f004d8a3bbece3ed74cd82196ef`.
   However, the corrected implementation was uncommitted; HEAD was
   `1e900aa42ac212f424cedccb51eaedde051d5129`, and the practice plan contains
   neither source_commit nor the executable snapshot hash. No exact Tower
   request exists. We cannot retroactively claim it used a published commit
   or substitute a different evidence plan. A corrected committed executable
   and common plan must first be practiced unchanged, then bound by the exact
   Tower authorization/window. Code, capture policy or launcher changes require
   fresh practice; only authorization may differ afterward.

The full per-bundle differences, warning text/line numbers, command, checks and
source hashes are in [six-check-audit.json](six-check-audit.json). Historical
practice report `49f654a1e0f8b3df00cb560c69ad271b734c2751a14c4c6473bb46d49d58ba90`
remains unchanged. This audit qualifies the meaning of its `passed` field; it
does not rewrite the practice result or earlier failures.
