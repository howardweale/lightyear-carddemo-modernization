# B06 amended gate and host stress — October 9, 2026

Neither `duplicate return arm` nor `generation return arm without matching
activation` reproduced in these host experiments. The native cause remains
unproven. The [gate amendment](b06-diagnostic-gate-amendment.md) permits one fresh
diagnostic preparation on this evidence; it does not authorize a native launch or
qualification. No degradation mode was implemented.

Howard approved merging #292 at `4e58a37a30108609c720d9cb286a039ee84daf68` and
taking #293 out of draft. All 24 checks passed before #292 was merged as
`c4103b3e4a09c13deb580b233e2305f259729ecd`. #293 is ready and targets main; it is
not merged. The amended source and scope wording are published at
`b0d5749c0a876b7977d8c64bdeca65706b6c129f`; all seven changed files were compared
with the exact GitHub commit bytes.

## Experiment and actual coverage

The public fixture starts four synchronized workers. Beneath 128 recursive calls,
each repeatedly defines a fresh hidden class, constructs and invokes method-handle
adapters, and creates a fresh lambda factory. Corretto 21.0.10_7 runs the real
external #293 JDI collector in v2 mode. The target uses a 4 MiB thread stack and
`java.lang.invoke.MethodHandle.CUSTOMIZE_THRESHOLD=0` to exercise generated
LambdaForm bytecode. These are host experiment parameters, not changes to native
application settings. No faults are injected into the collector or tracker.

| Attempt | Outcome | Generation entries / returns | Duration |
| --- | --- | --- | --- |
| Initial fixture | Fixture `WrongMethodTypeException`; not a stress result | 61 / 61 | 1.609 s |
| Four × 800, ten-minute allowance | Host timeout; incomplete audit | 20,023 / 20,020 | 600.158 s |
| Four × 256 | **Completed 1,024 iterations; complete audit** | **9,283 / 9,283** | **200.593 s** |
| Four × 800, approved thirty-minute allowance | Fixed 128 MiB audit-byte limit; incomplete audit | 27,023 / 27,020 | 995.295 s |

The completed batch recorded all four worker depths between **136 and 151**.
Each worker produced 773 observed `InvokerBytecodeGenerator` entries, 1,285
`ClassDefiner.defineClass` entries and 256 lambda-factory entries. Their event
intervals overlap, with **8,834 generation-thread switches**, so this was
interleaved concurrent activity, not merely four sequential thread names. The
collector and target both exited successfully. Its 139,263 audit records consumed
45,935,657 audit-body bytes. Audit validation completed, with no pending generation
at VM death. The five compiled observer classes are hash-pinned in the metadata.

The approved thirty-minute experiment passed the old time cutoff. It stopped at
the unchanged diagnostic byte bound after **405,342 audit records**, below the
500,000-record cap. It had 25,936 generation-thread switches. The target's stdout
subsequently reported 3,200 iterations after observer disconnection, but those
last iterations were not captured: **that text is not a successful stress audit**.
The helper terminated its owned target after observer failure. Earlier partial
attempts and their open calls remain incomplete, not balanced or relabelled.

The collector byte limit, audit-record limit and tracker guards were not relaxed.
These direct-collector host experiments do not exercise the full native broker;
the native broker's original 50,000 non-audit evidence-record ceiling also remains
unchanged. The large host attempt exceeds that native evidence count, which is
another reason not to claim native admission from it.

[Results and hashes](b06-observer-stress-results.json) contain public-safe metadata
only. Raw streams, bytecode captures and compiled files remain local. Observer
source SHA-256 is `b4b8e34a858464f1b507ba0fe33e1ba92feb7d6afe7d9b637fd30f05c88dc065`;
the corrected public stress fixture SHA-256 is
`2ab58e10c27f2fc6334515912a72c874c3bb3e79a771d85bd84d920be446f666`.

## Diagnostic preparation and remaining gate

The completed four-thread batch satisfies the requested host concurrency/depth
experiment without reproducing either historical refusal. The extended partial
attempt provides additional negative observation only. **A native scheduling
defect is not ruled out.** The fresh diagnostic preparation must disclose the
known audit-byte limit and retain strict stop at the first anomaly.

Proposed window: October 10, 2026, **9:00 AM–noon PDT**. Full pair budget remains
7,190 seconds plus 600 seconds of cleanup reserve, making latest start
**9:50:10 AM PDT**. The full frozen plan must reach Howard by **5:50:10 AM PDT**;
preparation is not approval. Fresh exact Tower and Docker approval are required.
No native or Docker operation was performed by this experiment or preparation.

Five focused scope/authorization tests passed for the diagnostic-only Tower
wording, including rejection of degradation, retries, shortened review lead and
qualification/measurement credit. The [fresh diagnostic packet](calibration/idempiere-ms94/stage-b-06/preparation/observer-diagnostic-r1/README.md)
verified all 113,595 frozen hashes, 771 public source files and 60 focused
frozen tests. Snapshot `ba570784e544a252682737ff0396df59dd7b3fc5d5be63e94c0afc075a1ce555`;
plan `90e8bee67bb84af31bafeb5d78b3cfd107a8715a8c594c3be8c80b33dfdb3c1a`. This is offline preparation, not native admission. No historical failure is relabelled.
After a diagnostic native failure, reproduce the captured event offline, fix its
supported cause and prove the fix on that record before qualification.
