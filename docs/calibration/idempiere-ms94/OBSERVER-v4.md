# MS94: Oracle rollback baseline correction

Equipment-03 stopped after its second operations reference: one pass, one
`insufficient-evidence`, 60 unstarted slots. The signed report is
`e8139af66336f05df0a4df8a69da5db1efbdabc45d1563d053f09d06522cf717`.
Both lanes exited successfully. The recorded second result remains unchanged.

## Diagnosis from the retained native capture

In `journey-ddf28736371547099a017e7454365c5d`, Oracle session SID 63,
serial 59827 held transaction `4.21.1654` and the business-partner write lock:

| Sample | Transaction | Rollbacks | Commits | Undo applied |
| --- | --- | ---: | ---: | ---: |
| 1079 | 4.21.1654 | 0 | missing | 0 |
| 1080 | 4.21.1654 | 0 | 122 | 0 |
| 1100 | ended | 1 | 122 | 39 |

Observer v3 retained sample 1079 with `setdefault`, even after complete counters
were available in sample 1080 while the same transaction held the write lock.
It therefore refused a rollback witness at sample 1100. The capture proves the
missing value and the baseline-selection defect; it does not establish why the
Oracle dynamic-view query returned that transient missing value.

## Versioned correction

Observer v4 may replace an incomplete baseline only with a complete integer
counter tuple for the same session and XID while the target write lock is still
observed. It never replaces a complete baseline or imputes a missing counter.
The end witness still requires exactly one rollback, increased undo applied,
unchanged commits, and transaction end. The witness now records its baseline
sample index. Queries, sampling limits and reference timings are unchanged.

The complete judge is separately versioned as
`idempiere-qualified-judge-v5-observer-ms94`. Historical observer, judge,
controller and publication code stays intact. Equipment-03's snapshots, verdicts
and publications are preserved. New development reassessment is not native
qualification and does not turn the old stopped result into a pass.

## Validation and continuation

61 focused tests passed, including both observer versions, reviewed rules and
snapshot execution. New cases cover incomplete baselines, missing end counters,
lost write locks, different XIDs, intervening commits and multiple rollbacks.
Separate reassessment of both equipment-03 captures finds the required native
witnesses without generating new observations.

Equipment-04 repeats the entire 62-pair schedule from fresh databases with the
same 15-hour limit, zero model calls, no GCP, and first-non-pass stopping rule.
Howard Weale authorized diagnosis and continuation on 2026-09-28. His approved
SDK, purchasing reference/effects rule and ownership decision are unchanged;
their exact review packet remains
`e25e04f572af098bbc8753c02ad0a45f81f1aa0ee23be02bc4ed6be623d9d876`.
Stage B still requires all native qualification criteria to pass.

A separate read-only task follow-up checks progress and alerts on termination,
failure or required attention. It cannot restart a stopped campaign, alter the
frozen equipment or authorize generation. Scheduled checks depend on the Codex
app being available and are not an instantaneous process-exit alarm.
