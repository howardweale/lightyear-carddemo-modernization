# B06 application content identity — prospective r7

Implemented offline. **Native admission remains blocked pending complete evidence**, as Howard explicitly directed after reviewing the limited catalogue coverage. No Docker, model calls or live Tower request. Earlier failures and frozen snapshots are unchanged. Operator review; not independent attestation.

## Step 0: saved class comparison

Every saved loaded-class blob was rehashed, not merely its catalogue entry compared. Both attempts deliberately catalogued six targets. Four belong to `org.adempiere.base`; two belong to the Surefire bundle. None are loaded-class records for the three timestamped application bundles.

| Evidence | Compared | Identical | Different |
|---|---:|---:|---:|
| Loaded application classes (`org.adempiere.base`) | 4 | 4 | 0 |
| Other loaded targets (Surefire) | 2 | 2 | 0 |
| Retained `org.adempiere.ui.zk` class entries, including nested JARs | 1301 | 1301 | 0 |
| Retained `org.adempiere.server` class entries | 59 | 59 | 0 |
| Retained `org.idempiere.webservices` class entries, including nested JARs | 145 | 145 | 0 |
| Retained `org.apache.ant` class entries, including nested JARs | 1386 | 1386 | 0 |

No compared class entry was added, missing or changed. The 2,891 retained class entries are **artifact contents, not evidence that those classes loaded**. [The full report](saved-class-comparison.json) lists every one of the 44 observed application bundles; 43 have no loaded-class catalogue coverage. Complete artifact contents were retained for four folder bundles; complete bytes for the remaining application bundles cannot be reconstructed from this evidence. Empty comparisons do not count as equivalence.

Class report SHA-256: `1e20428201260bacfdf13fdbd540c8c25ac86b542ef6736338d35d104eab5278`.

Howard's follow-up permits proceeding with implementation while keeping admission blocked. This does not claim that the original full-catalogue prerequisite was satisfied, nor does it reinterpret r4/r5b as successful.

## Deliberate identity rule

Only bundles whose normalized original path is strictly beneath `/application/` qualify. Compare:

1. Exact symbolic name and version's numeric major/minor/micro segments.
2. Exact entry-name set and entry kinds. ZIP timestamps/compression are not content.
3. Every non-manifest entry's decompressed bytes, including all resources and nested JAR bytes, exactly. A nested JAR is itself an entry; its bytes are not recursively normalized.
4. The manifest exactly, except the following **main-section** header values:
   - `Bundle-Version`: remove only the fourth, qualifier segment.
   - `Built-By`: normalize its value to a fixed marker.
   - `Bnd-LastModified`: normalize its value to a fixed marker.
   - `Build-Timestamp`: normalize its value to a fixed marker.

The original value of every normalized header is recorded. Presence, header name, ordering and line endings remain exact. Named manifest sections and all other headers remain exact, including `Import-Package`, `Require-Bundle`, `Bundle-ClassPath`, and differently named timestamp headers such as `Build-Time`. No broad timestamp pattern or semantic resource comparison is permitted.

This is a declared identity rule, not a relaxation of execution-byte checks: class and resource bytes remain exact. The rule makes no claim that bytes differing outside its explicit metadata normalization are equivalent. Exact non-application artifact hashes, including `/root/.m2`, JDK, framework and launcher, remain required even when a protected artifact happens to have an application path. The transient-source rule is unchanged.

Each run records original path, full version/qualifier, archive SHA-256, original manifest SHA-256, normalized manifest SHA-256 and content identity. A copied JAR keeps its original bytes. A folder bundle is captured as a bounded archive with every entry; the archive hash is labelled as a folder-copy hash, not an original JAR hash. No directory content is silently excluded.

## Capture, production, replay and measured binding

The no-candidate JVM copies application file bundles while alive into `/results/runtime-application/<bundle id>.jar`. It archives folder bundles there too, including the three timestamped folders. Symlinks, missing files and bounds fail closed; detectable file changes during folder capture refuse. The original per-run archive bytes remain local evidence.

Observation `/4`, launch receipt `/5`, resolved runtime `/5` explicitly require these captures. Signed production, offline replay and scoped class extraction read the retained copies and verify their hashes. Earlier `/2`, `/3`, `/4` resolved-runtime replay paths remain unchanged.

`transient_sources.bind_measured` replays both resolutions before matching source-only identities, application content identities and every remaining exact artifact. `application_identity.bind_measured_posting_classes` then binds each observer-read class byte sequence to its actual defining application archive and declared Bundle-ClassPath. Changed/missing/ambiguous posting class bytes refuse, regardless of metadata equality. This is the prospective measured-run consumer; it emits `native_admission: false`. Existing J1 predicates and frozen plans were not changed. No current native plan is admitted by adding this consumer.

## Actual retained-content check

The new rule was applied offline to complete retained folder copies from both failed attempts:

| Bundle | Non-directory saved entries | Result |
|---|---:|---|
| `org.adempiere.ui.zk` | 1577 | Equal under the declared rule |
| `org.adempiere.server` | 141 | Equal under the declared rule |
| `org.idempiere.webservices` | 62 | Equal under the declared rule |
| `org.apache.ant` | 65 | Equal under the declared rule |

[Content report](saved-content-comparison.json), SHA-256 `9cdf3ec844e0c226cd44f449b534109f0f8ef72bb6cddf525d615f4c0d4efcd9`, records both identities, manifest hashes and every actual normalized header/value. No class or resource difference was ignored. These saved-folder archives enumerate file entries; future live folder capture additionally preserves directories and compares that complete set between runs.

## Validation and remaining boundary

80 focused offline tests pass, including qualifier/ZIP timestamp variation, changed class/resource/extra entry/import/required bundle, unlisted header, outside-application qualifier refusal, copy tampering, independent replay and measured posting-class bytes. Host-JDK tests compile the real closure agent and exercise copy/deleteOnExit and file/folder capture with synthetic OSGi interfaces. Windows does not expose ProcessHandle argv on this host; the real agent therefore refuses a complete observation after capture. This is explicitly tested, not substituted with synthetic native evidence.

The full `/application/org.idempiere.test` folder and rebuilt application archives still require complete fresh captures. Source, probe, candidate or build-output differences in that folder remain differences; no new exception was added for them. Until complete closure/measured evidence passes, native admission stays blocked. A runtime-only capture window is not qualification or measurement authority.

## Fresh request preparation

One fresh runtime-only snapshot/request must cover all three changes: exact Tycho properties/fork binding, transient source preservation, and application content identity. It must bind a new source commit, all new modules, exact public bytes, immutable snapshot and fresh one-hour window, with zero models/databases/native pairs and no retry. The old r5b authorization cannot be reused. A fresh window has been requested from Howard. No live Tower request has been created in this increment; request preparation is for review only.
