# B06 bounded observer and native diagnostics

Status: offline implementation and validation in progress; engineering hold remains.

Howard's decision dated 2026-10-10 17:44 PDT supersedes the host reproduction
prerequisite. The historical ~560 bytes/event retained growth and the mismatch
between host and native payload tails justify this work; they do not prove the
native OOM's initiating cause.

The new opt-in `bounded-observer-v1` format streams class definitions on first
sight. A private disk index stores class identity, definition hash and prepared
state, with a fixed 256-entry heap cache and 262,144 slots. Pending activations
retain matching identifiers and entry age, with a hard 256-activation cap.
Return records reference the already emitted entry. Completed payloads are not
retained. Checkpoint frames reference class definitions rather than duplicating
constant pools and method bodies. Binary fields are base64; the JSON writer uses
bounded chunks. Audit records use a bounded record buffer. Large routine event details are
losslessly DEFLATE/base64 encoded once, with length and SHA-256 checks; quotas
count their wire bytes. Refusal context stays directly inspectable.

The engineering-only JDI mirror adapter bounds the JDK's own strong class cache
to 1,024 mirrors (512 low-water), retaining active and unprepared types. It uses
exact-name JDWP queries and refuses full enumeration or unsupported runtime
bytes. All seven pinned JDI class hashes match the preserved public image
catalogue; actual runtime bytes are rechecked before collection. See
[binding and lifecycle tests](b06-jdi-mirror-adapter.md).

Routine set-open/dispatch/resume traffic is aggregated. Every dispatched event
retains request, method, thread, depth and arm information; a refusal adds the
full pending context captured before dispatch. Lifecycle and heap metadata share
the unchanged 500,000-record / 128 MiB diagnostic quota. The original 50,000
ordinary-evidence cap remains. No evidence cap has been raised.

Native diagnostics bind strict or diagnostic mode, a ten-unmatched-return cap,
heap telemetry each 1,000 events and an 85% resource guard. The guard suspends for
a broker-collected histogram and a signed stop receipt; an OOM dump remains in
owned private output. Application phase receipts bind existing worker/checkpoint
markers to observed generation-entry counts. They do not invent business-phase
inference. Java receives a 1,536 MiB heap, zero soft-reference retention policy,
and a private state directory; the observer container limit is 2,048 MiB.

The engineering authority is separate. Its public fingerprint is
`4ce00cfa28c13f74c12e6569b6aae010fe7e7185849accad8340c2fc367be9f0`.
Admission rejects that signing identity even after labels or paths are changed.
Only its public PEM is versioned. All engineering entry points remain held.

The prospective request is limited to two Oracle-only retained-reference J1
attempts: strict first, diagnostic second. Each has 60 minutes work and ten
minutes cleanup, a 30-minute candidate timeout, zero models and zero credit.
The exact implementation/classes/template hashes and proposed calendar will be
published after validation; no approval or native execution is implied.

## Validation record

- Existing historical readers remain available for their original formats.
- 104 focused checks passed with eleven optional skips before the final audit
  aggregation changes; updated final-head validation is still required.
- The exploratory bounded payload variant avoided OOM but hit the unchanged
  audit byte cap after 29,360 generation entries. Peak sampled after-GC heap was
  34,200,992 bytes. That run is preserved and is not an acceptance pass.
- The second variant stayed below 17,565,256 bytes after GC but reached the
  128 MiB metadata quota at 27,907 generation entries. Its fitted retained
  growth remained positive: 32.07 bytes/emitted record, 95% interval
  31.82–32.33. This is not a flat-curve pass.
- The first mirror-cache variant stopped at its pin guard: unknown JDI
  preparation status was conservatively retained. The correction reads actual
  status outside the JDI cache lock; genuinely unprepared mirrors remain pinned.
- The corrected full-volume 192 MiB host experiment is running. Flatness and
  completion are not yet claimed.
- A production-serializer transient test passed with a 1 MiB definition and
  4,096-node graph resident at 85% occupancy of a 192 MiB heap. Final-source
  measurements will accompany the final validation record.

No Docker, native application, model or customer-data execution occurred.
All historical failures remain failed. Green final-head CI and Howard's
commit-specific merge approval are required; this document grants neither.
