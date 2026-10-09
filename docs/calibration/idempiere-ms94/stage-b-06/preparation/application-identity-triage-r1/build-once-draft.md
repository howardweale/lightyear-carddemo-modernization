# Build-once amendment and practice plan — draft, not authorization

## Reason and scope

Rebuilding the application recreates source metadata and test-bundle artifacts.
The 21 source bundles support the B/C-only proposal. However, the test bundle
contains two changed nested JAR resources plus five changed non-candidate files;
a class-only exclusion leaves all seven differences. Under the requested exact
non-candidate rule the present rebuild-per-run identity is infeasible. Stop
that route and review this alternative. There is no historical-content gate.

**Prospective amendment:** build application outputs once, seal a runtime layer
by image digest and complete file manifest, and make both closure and measured
launches consume that same layer without Maven/Tycho build goals. Compilation
of the exact per-run test/candidate class occurs separately against the pinned
classpath; only explicitly listed class outputs may be overlaid and each remains
bound by compilation and trusted observed-class evidence. All other bytes stay
exact. This is operator review, not independent attestation; earlier failures,
J1 predicates, verdicts, deadlines and diagnostic rules remain unchanged.

## Pinned build layer

Base image: `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`.
The new layer digest is **not yet available**, and must not be invented or
replaced with the base image digest. One network-free builder uses committed,
hash-bound sources/tools. Record the actual build argv, environment, JDK and
compiler identities, start/end real time, exit status and all retained failures.

Seal all runtime application bundles, including the entire test bundle's
non-candidate content, resources, nested JARs and generated metadata. Capture the
full shared content view and actual archive bytes. Record per-file path, size,
SHA256, bundle identity and classpath; retain origin and layer digest. The build
layer also binds framework/launcher/Maven dependency artifacts, runtime OSGi
configuration templates, test properties, lock-SQL/class catalogue, JDK and
observer bytes. The image layer plus manifest provides exact reuse; do not
normalize timestamps to make separate builds look identical.

Tycho transient source JARs must be preserved before their builder JVM exits.
The layer packager restores each preserved source JAR at its exact observed
location, with its exact hash, before sealing. Revalidate source header,
class-free/no-nested-JAR bytes and no loaded attribution. A missing source JAR or
relocated location is a preparation failure; a location/reader amendment would
need explicit review before freeze. This detail must be demonstrated in the
practice, not assumed from a Dockerfile. A writable /tmp mount must not hide or
permit replacement of these bound source files.

## Measured launch (no rebuilding)

The dispatcher accepts only the sealed runtime-layer digest, compiled per-run
class manifest and a closed launch specification. It executes the pinned Java
binary directly with the bound Equinox launcher (`-jar`), installation/configuration
and `-testproperties` arguments derived from the captured fork. It must never
invoke Maven, Gradle, Tycho compile/package/verify, or rewrite base bundle files.
The exact argv and OSGi configuration mapping remain implementation prerequisites,
not an executable command in this draft. No guessed launch is authorized.

The base layer is read-only. Writable logs, OSGi caches and runtime configuration
are placed outside content-identity roots with individually declared paths and
reasons. Record their actual contents separately. Candidate source and compilation
work stay outside the bundle root. Permit only exact class-file overlays from
the per-run compilation manifest; reject extra filenames/inner classes, undeclared
loaders, or a different defining path. Do not exempt a package or `*.class` glob.

For closure practice, the enumerated class is
`target/classes/org/idempiere/test/B06RuntimeCatalogTest.class`. For a later native
candidate it is the separately declared LightyearOperationsTest output and any
explicitly admitted associated outputs. Its source, compiler inputs, class bytes,
loader, actual defining path and trusted observer record must all bind and replay.
Keep the packaged nested JAR byte-exact; require that a duplicate class in that
JAR does not shadow the admitted overlay. Never exclude the whole JAR.

Gate entry checks must demonstrate that every non-candidate base entry remains
unchanged before/after both engines. Producer/replay must verify the layer
manifest, actual loaded catalogue and class overlays. Supporting application
classes remain byte-bound. This does not reduce posting-origin provenance or
admit missing generated-class proof.

## One prospective practice group

DRAFT: needs implementation, offline tests, exact public commit, executable
snapshot, layer-build plan and explicit practice Docker approval before use.
No window or Tower request is created by this document.

- Maximum 45 minutes work plus 10 minutes owned cleanup; one serial group,
  at most one build container and two consumer containers, no parallelism/retry.
  If implementation cannot fit the limit, stop and propose a revised budget.
- Pinned base, network none, cap-drop ALL, no-new-privileges, 8 GiB memory,
  2 CPUs, bounded PIDs. No database containers/native pairs/models/credentials.
- Build once and preserve/seal the artifact set. Native compilation count/time
  is measured and reported separately; it is not zero compilation.
- First consumer performs the no-database closure probe from sealed outputs.
- Second fresh consumer uses the same runtime layer and a separately bound
  no-database per-run probe class (variant declared and hashed in the final plan).
  Demonstrate exact non-candidate map reuse and independent overlay byte binding.
- Observe/record the real Equinox fork, resolved bundles, actual loaded sources,
  JDK, per-run class loader and defining origin. Capture complete runtime data,
  warning baseline, source-only facts and generated-class records where available.
- Independently replay both outputs; verify non-candidate resources/classes
  byte-exact, overlay hashes exact, no build invocation in consumers, no hidden
  writes, and all owned container/network/volume cleanup. Retain both outcomes.
- Offline negatives mutate one class/resource, add an overlay, change a manifest,
  supply the wrong layer/loader/class proof, remove a source JAR, or shadow the
  admitted class from a nested JAR; each must refuse. Failed negatives block.
- Practice failure stops the group and preserves output. No automatic restart,
  replacement slot, layer rebuild or retry. Cleanup only this group's owned
  containers/networks/volumes; no prune or unrelated operations.

## Freeze/admission prerequisites

Pending fields include new layer/manifest hashes, exact build and direct launch
argv/configuration, compiled probe variants, class-overlay evidence/replay format,
public source commit, executable snapshot, practice window and exact runtime
catalogue acceptance. All must be reviewable before authorization. A successful
practice then precedes a separate Tower decision for evidence. This draft
neither starts a run nor creates a measurement or qualification claim.
