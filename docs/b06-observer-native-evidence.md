# Codex instruction: B06 observer, fix the obvious and get native evidence

Howard decided this on 2026-10-10 at 5:44 PM PT. It replaces the measurement gate
in `codex-b06-memory-next.md`. The host baseline was right to stop there, but the
gate was wrong: a lighter synthetic workload can't reproduce a failure driven by
native payload sizes and transient serialization peaks. Evidence now comes from
two instrumented native engineering runs, after the changes below.

Standing constraints are unchanged:

- zero model calls;
- no Maintec or customer data;
- no rewriting of preserved evidence;
- separate worktrees;
- final-head CI completed green before merge;
- Howard's commit-specific merge approval.

**The October 11 hold stays in force** until Howard approves the exact request
in Part 4.

## What the evidence now says (record this in the milestone)

- **r3 did not progress further in application terms.** It recorded 12,396
  generation entries, against 12,394 (diagnostic r1) and 12,414 (practice r1).
  Every native run fails at about the same application point.
- **The five accepted unmatched returns cluster in the last 300 records**
  (230,866–231,011). The OOM follows 147 records later. The last audit is
  `ClassDefiner.defineClass` at depth 110. A single application phase is the
  leading hypothesis for both symptoms. It is a hypothesis to test, not a
  conclusion.
- **Host retention grows at about 560 bytes per event and is not bounded.**
  Native payload tails are much larger:
  - definition input up to 262 KB, against 10 KB on the host;
  - class-data graphs with a median of 110 nodes, against 1;
  - depth up to 213, against 131.

  After-GC sampling can't see serialization peaks.
- **The host run stopped on the 128 MiB structural-audit bound** at about 236,000
  records. A memory-fixed native run would likely hit the same bound next.

## Part 1: bounded-memory changes (implement; no reproduction prerequisite)

These are improvements whatever the root cause. Prove each one by test, not by
reproducing the native OOM.

1. **Class definitions.** Write each definition to the evidence stream once, at
   first sight. Keep only `class_object_id → sha256` and the prepared flag in
   memory. No resident `bytecode_hex`.
2. **Entry payloads.** Write stack, definition bytes, lambda-form and class-data
   graphs when the entry is recorded. `pending` keeps only the match key and its
   age, with a hard cap that produces a signed stop.
3. **`completed`.** Evict each entry once the factory class is emitted.
4. **Streaming serialization.** Write JSON directly to the output with bounded
   buffers, and count audit bytes as they are written. **No second serialization
   just to count.** Where encoding matters, write large byte arrays as base64 or
   raw blob records with hashes, not hex inside a JSON string.
5. **Less audit volume.** Today there are about 15 audit records per generation
   call (206,365 audit records for 12,396 entries).
   - Keep everything needed to diagnose a refusal: event type, thread, method,
     depth, request ID, event-set position, arm state.
   - Drop or aggregate the rest, for example routine resume traffic as counters
     per event set.
   - Report the before and after records per call.
   - The aim is that a full native pair fits under the existing 128 MiB audit
     bound. If it can't, propose a new bound, with a measured basis, for
     Howard's approval.
6. **Format.** Use a new version marker for the changed record format. Old
   archives must still verify through the old reader, with a replay test for r1
   and r3.

**Host tests:**

- The `--native-volume-memory` stress run at 192 MiB completes. Its after-GC
  curve is flat after warm-up: the slope is not significantly above zero, and
  you report the fit.
- Add a **transient-peak test**: one entry with a 1 MiB definition and a
  4,096-node graph at 85% heap occupancy. It must not OOM. Measure the
  serialization allocation for it.
- All existing observer, audit, unmatched-return, admission and engineering-hold
  tests pass. The Linux JDI CI job passes on the final head.

## Part 2: native diagnostics (implement)

1. **Breakpoint lifecycle records.** Record when each entry and exit request is
   created, enabled and disabled (request ID, class, method, thread filter, time
   and audit index), plus class-prepare events for the watched classes.
2. **Heap telemetry.** Record heap used and max, GC count and time every
   1,000 events, plus a high-water mark.
3. **Safety stop.** A clean signed `observer-resource-limit` stop at 85% heap,
   and `-XX:+HeapDumpOnOutOfMemoryError` to an owned private path. On the guard
   stop, also take a heap histogram before exiting.
4. **Phase marker.** Record the generation-entry count against application
   progress markers already available to the broker, so the 12,400 point can be
   tied to what the application was doing.
5. **Mode and cap.** A per-attempt mode, either `strict` or
   `diagnostic-unmatched-return`. Diagnostic mode has a hard cap of
   **10 accepted unmatched returns**, up from the 3 proposed earlier, because r3
   showed 5 in a cluster. The cap must let the run pass the cluster and reach
   whatever comes next. Exceeding it is a signed stop.
6. **Memory limits from `LIMITS`.** Wire them into the real `docker create` and
   `java` arguments. Proposed for the runs: observer `-Xmx1536m`, container
   `--memory 2g`. This is deliberate headroom, so the run reaches the 12,400
   point with telemetry instead of failing on the ceiling; it is not a claim
   about the right production size. The heap telemetry from the runs sets the
   final values.

## Part 3: separate engineering signing key

Before any native attempt:

- generate a separate engineering signing key;
- record its public fingerprint in the approval;
- make the launcher refuse any other key;
- make admission paths reject records signed by the engineering key.

Never read or reuse the qualification key.

## Part 4: approval request for Howard (prepare, then stop)

Write the request with exact values:

- implementation commit;
- observer source and compiled hashes;
- engineering key fingerprint;
- image digest (`554a5203…`, unchanged);
- heap and container values;
- audit bound;
- unmatched-return cap.

**Sequence: exactly two attempts, then stop.**

1. **Attempt 1, strict mode:** expected to refuse at the first unmatched return.
   Purpose: lifecycle and class-prepare records at the 12,400 point, with low
   memory pressure.
2. **Attempt 2, diagnostic mode** with the 10-return cap: expected to pass the
   cluster. Purpose: what comes after it, with heap telemetry, the guard and a
   heap dump if needed.

The window and limits are as before:

- per attempt: 60 minutes of work, 10 minutes of cleanup, a 30-minute candidate
  timeout;
- Oracle-only J1 retained reference;
- zero credit;
- no overlap with any J1 or B06 evidence window.

Give Howard the request at least 4 hours before the proposed start. **Do not
lift the hold yourself.**

## Part 5: alternatives measurement (in parallel; offline; no approval needed)

This has been deferred three times. Do it now on the host, with numbers:

1. `jlink --generate-jli-classes` and a dynamic CDS archive from a host training
   run. What share of the watched generation calls disappears?
2. The JDK dump options for lambda forms, method handles and lambda proxies:
   - coverage of each generated-code category, including hidden classes;
   - attribution;
   - output size;
   - overhead.
3. **The 2c split** on the r1 and r3 streams: generation entries classified as
   JDK-internal plumbing versus application-derived, as counts and percentages.

Publish `docs/b06-observer-alternatives.md` with a comparison table.

## Part 6: decision point

After the two native attempts, report:

- what happens at the 12,400 point: lifecycle records, class-prepare, the
  application phase;
- the cause of the unmatched returns, if identified;
- heap telemetry and whether the guard or OOM triggered;
- how far attempt 2 got, and why it stopped;
- the alternatives table from Part 5.

**Firm rule:** if the two attempts don't identify the cause of the 12,400-point
failure, stop observer repair. Howard then chooses an alternative design from
Part 5. No further observer-repair attempts are proposed without his explicit
decision.

## Deliverables

1. **PR:** Parts 1–3 with tests, plus the evidence-summary milestone.
2. **The Part 4 approval request,** then stop.
3. **PR:** the Part 5 alternatives measurements. This can merge independently.
4. **After the runs (if approved):** a results milestone and the Part 6 decision
   memo.
