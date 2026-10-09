# B06 runtime preparation milestone — October 8, 2026

Operator review; not independent attestation. This milestone publishes runtime
preparation and preserves unsuccessful attempts; it is not native qualification
or permission to launch a campaign.

## Delivered

- Exact public-commit, immutable-snapshot and Tower-bound runtime launch guards.
- Tycho 4.0.8 properties and observed Equinox boot-classpath capture/replay, with
  historical schema support. The Maven-Surefire booter assumption is superseded.
- In-process preservation and strict classification of transient source-only
  bundles; application bundle capture, warning baseline and failure diagnostics.
- Bounded completion/error reporting and atomic capture; prior failures remain
  separately recorded rather than retried or converted into successes.
- Build-once runtime with direct Java consumers, separately bound per-run classes,
  exact application bytes and read-only runtime mounts. Content-normalization
  proposals are historical, not active admission shortcuts.
- Exact selected-archive copy, offline class index and private five-path input
  assembly. Public files contain metadata and hashes; private archives, compiled
  reference classes, captures and keys stay local.

## Recorded evidence

The [build-once practice](calibration/idempiere-ms94/stage-b-06/preparation/build-once-r1/terminal/README.md)
passed one build and two consumers in 1,031.157 seconds. It bound 44 application
bundles and classified 102 source-only temporary bundles. The 777-file freeze
remained unchanged and owned cleanup passed. Practice is not qualification.

The [archive copy](calibration/idempiere-ms94/stage-b-06/preparation/built-catalog-r1/terminal/README.md)
passed for 204 archives / 132,922,294 bytes, with signed terminal records,
independent replay, 291 frozen files unchanged and actual owned cleanup.
The [offline assembly](calibration/idempiere-ms94/stage-b-06/preparation/built-census-offline-r1/README.md)
indexes 122,650 class entries and binds 82 private input references across five
paths. Earlier runtime failures remain in the preparation chronology.

Publication itself performs no Docker commands, models or native pairs. Offline
regressions and the PR's Windows/Linux provenance CI validate the implementation;
local-evidence and explicitly enabled host-JDK tests may skip on clean CI hosts.

## Remaining gates

The observer-v2 integration is a separate follow-up. A new five-path native census
must cover J1's three paths and J2/J3 retained references on both engines under an
exact executable snapshot, public commit, window and signed Tower decision.
Journey qualification and zero-model preflight remain before any measurement.
B04 stays void; B05, template-r1, work/ms94, J1 predicates and frozen evidence are
unchanged. Historical expired plans in this PR grant no new run authority.
