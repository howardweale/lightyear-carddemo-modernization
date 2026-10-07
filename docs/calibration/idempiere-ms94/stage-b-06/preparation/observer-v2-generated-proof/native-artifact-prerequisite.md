# Native artifact prerequisite for the five-path freeze

Operator review; not independent attestation. **Proposed preparation only.**
No Docker execution, native pair, model call or Tower decision is authorized by
this document. The approved observer-binding v2 policy remains unchanged.

The saved r4 catalogue contains selected application classes and framework jar
entries. It does not contain all ordinary classes seen by r10 (for example
`org.compiere.model.MOrder` and the Equinox defining loader), or the pinned Linux
JDK module image and native-provider file bindings. The Windows Corretto host
experiment cannot supply those Temurin/Linux artifact identities.

Section 1 of the approved amendment requires each ordinary class's full bytes
and the actual defining artifact in the resolved runtime. Section 2 requires
`java`, `lib/modules`, release metadata and native-provider files bound to the
pinned image. Neither an observed constant-pool hash nor a package name replaces
these inputs. The five-path freeze must fail if they are missing.

## Exact proposed preparation scope

- One fresh, owned container from application image
  `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`.
- No database, native pair, candidate execution, model, network, credentials or
  private checkpoint/source mount. No image pull or build.
- Read-only image root; explicit Python extraction entrypoint. Only a reviewed
  extractor mounted read-only and a new owned output directory mounted writable.
- Extract class files and jar-entry catalogues from the image's application and
  dependency artifacts, preserving source artifact paths, artifact hashes,
  duplicate entries and differing copies. Do not resolve duplicates by name.
- Capture the JDK release file, executable, module image and native-library
  hashes, plus original class bytes for the generator, class-loader and
  method-handle machinery. Do not execute a target JVM or test harness.
- Bind the existing passing runtime-resolution evidence; keep resolved origins
  distinct from other same-name copies. Never infer a loaded source from a
  directory search alone.
- Maximum 30-minute Tower-authorized window: up to 15 minutes extraction,
  10 minutes reserved for owned cleanup and verification, with 5 minutes for
  admission and container setup. Refuse a late start.
  No retry or replacement. Preserve any failed extraction and its costs.
- Remove only the recorded owned container; verify its absence. No prune,
  shared resource deletion or changes to running campaigns.

Outputs remain local: original image files, jar/class bytes and extraction logs.
Public output is a hash-only manifest, duration, cleanup result and limitations.
The exact extractor/snapshot, public commit and UTC window must be bound in a
separate Tower request before execution. This document is not that request.

After extraction, the five-path snapshot can bind the complete immutable inputs:
J1 retained, duplicate invoice-line mutant, candidate runtime exception/direct
delivery, J2 retained and J3 retained, each on Oracle and PostgreSQL. It still
requires its own published commit verification and exact Tower decision. No
prepared or successful census slot may be reused as a qualification slot.

If equivalent exact image exports already exist outside protected/frozen
campaign paths, they can satisfy this prerequisite offline after hash and origin
verification; a second extraction would not then be needed.
