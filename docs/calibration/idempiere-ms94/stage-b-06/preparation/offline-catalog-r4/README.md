# B06 offline compilation and class catalog — October 5

Operator review; not independent attestation. Zero model calls, native pairs,
database executions and Docker test executions. This is preparation, not native
qualification. B05 evidence, template-r1 and J1 predicates are unchanged.

The approved preparation window ran from 2026-10-05 15:06:15.626 UTC to
16:02:05.012 UTC (08:06–09:02 PDT): 55m49s elapsed including work between
containers. The five recorded container windows total **2,288.827 seconds**
(38m09s), including failures. Every owned container was absent on independent
read-only recheck. All containers used the pinned application image
`sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`,
no network, no capabilities and no private-key mounts.

The observer compiled. Extraction inventoried 10,420 class origins (3,915 distinct
class byte strings) from 2,522 JAR files. Selection admits 1,368 unambiguous
application/runtime classes; Maven-cache alternatives do not determine runtime
identity. Every observed JDI frame must still match the pinned bytes during
native qualification. The catalog includes the actual JUnit terminal callbacks.

The real Doc.class, its constant pool and post(ZZZ) method bind the complete lock
SQL fragments, including the processing, posted, active and processed predicates.
Their hashes, Java binary hash and runtime catalog hash are recorded in the
[signed preparation summary](preparation-summary.json).

Offline test-compilation produced verified candidate/support class catalogs for
61 distinct source versions: the 60 draft inputs with three assertion-import
corrections, plus the declared duplicate-trace source control. Each compile
removed only previous candidate/support/control outputs before compilation, so
stale classes cannot supply missing output. Tests were skipped. Raw source,
class bytes, compiler logs and private catalogs remain local; public evidence
contains hashes and preparation metadata only.

Failures remain preserved:

- The first extraction encountered a directory named `.jar`. Its 8.750-second
  attempt failed and its owned container was removed. The worker now scans files.
- One source lacked an assertNull import; two lacked assertTrue imports. Their
  original failing source hashes and compiler-log hashes remain recorded. New
  sources fully qualify those JUnit calls and passed compilation.
- Container window 3 ran for 367.015 seconds with worker
  `63f848ca4b2841cab0a626cc263f63423b3d9306652492cbb3c44c9befffc06a`.
  Nine sources compiled before source `363c49d6…fb9734` failed because
  `assertNull(String)` was undefined. That worker exited with `AssertionError`;
  this is the first recorded assertion-import failure above, not an additional
  native failure. Its window, compiler log and cleanup result remain unchanged.
- The duplicate-trace-key draft reused the retained hash. The declared source
  transformation is now materialized and compiled separately. The next plan
  revision must bind its new hash explicitly.

No qualification slots were attempted, replaced or restarted. Compilation alone
does not establish the expected native outcome. The signed summary hash is
`d2360cb6f3aa93db322246e9f499a390321ebd3c8bc924fa0a12eb33b6a41f9b`.

Remaining: native slot assembly and finalization, closed posting-cause delivery,
exact executable plan commits and operator-approved Docker windows. The actual
Windows builder-denial record passed in PR #254; it gates measurement and
preflight, not zero-model judge qualification. Codex-process transport proof is
still separate and outstanding.
