# Image extraction revision 2 — prospective repair

October 7, 2026. Operator review; not independent attestation.

The authorized r1 launcher started successfully. Its extractor failed after
494.437 seconds at `class-count-bound`, before producing a complete catalogue.
Terminal report content hash:
`f604f680ee7f5beb67bf80df379d0e2aaaff46d97e77d5e3729a97f442c73c21`.
The signed failure, partial outputs and all 396 frozen files are preserved.
Public-key verification and read-only owned-resource cleanup verification passed.
No retry is authorized and the old monitor remains paused.

The old bound counted every JAR-origin class occurrence and wrote one file per
distinct class hash. Revision 2 retains original archive blobs and indexes each
byte-identical archive once. Every archive origin is retained; duplicate entry
names retain their ordinal and bytes. No class-name deduplication or runtime
resolution inference is permitted. Offline replay reopens each archive, checks
the complete class-entry list, every ordinal/hash/size and every origin. Loose
classes and JDK runtime files remain separate retained blobs.

This is an explicit prospective resource-bound change: up to 1,000,000 indexed
class entries, 50,000 artifact origins and 256 MiB of catalogue metadata. The
512 MiB per-blob and 8 GiB unique-blob bounds remain. All limits are bound in the
new core/plan. Identical archives no longer multiply indexed-entry counts or
small-file writes. This improves the representation; it does not prove the
native image fits the new limits or that provenance qualification passes.

The execution limits remain one network-free container, zero database or target
JVM executions, zero model calls, 900 seconds extraction, 600 seconds cleanup
reserve, one 30-minute window and no retries. Admission binds the exact public
branch through the plan instead of hard-coding the old r1 branch. Fresh output,
exact Git bytes, snapshot hashes, a distinct Tower signer and a fresh decision
remain mandatory. Existing r1 plans are refused by revision 2; their original
immutable executable remains available for audit only.

**Not launched.** A new immutable snapshot, public commit, declared window and
exact Tower decision are required before any Docker execution. No old launcher,
output directory, authorization or failed slot may be reused. The five-path
census remains separately gated; J1 predicates and expected outcomes are unchanged.

Offline validation: six extractor/controller tests passed, including duplicate
archive origins and entry ordinals, complete byte replay, missing Tower/public
snapshot/time guards, timeout preservation and refusal to clean foreign-owned
resources. Docker was mocked throughout these tests; no native image extraction
or database pair ran for revision 2. This document is the prospective milestone,
not an execution receipt.
