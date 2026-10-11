# Pinned runners and next-five PR gate timing

Every floating Ubuntu label is now `ubuntu-24.04`, including required-ci.
Windows labels are pinned to `windows-2025`; the existing `macos-15` pin stays.
The Windows-specific 45-minute job allowance follows its renamed matrix label.
Workflow lint refuses a reintroduced floating OS label. Branch protection and
the exact-head green gate remain unchanged; no bypass or merge is authorized.

The requested next five PR observations are #311–#315, the first five published
for this follow-up. `tools/ci_push_latency.py` queries paginated GitHub REST
records, binds each current head and requires every applicable workflow plus
required-ci to complete successfully. It preserves failure/cancellation/skip
as nongreen. Exact push time comes only from a matching GitHub PushEvent.
If retention omits that event, exact push-to-green is unknown; a separately
labelled earliest-workflow-created-to-green proxy is retained. Author/committer
time is never substituted for push time. Head changes reset the observation.

The independent existing three-merge monitor still measures post-merge main CI
latency. It is not replaced by this metric. The new heartbeat records queue
size and quiet progress locally, reporting new completions/failures only.
After five completed observations it reports a table and pauses.

The gate still waits up to 60 minutes inside a 65-minute job. No timeout increase
is justified by five completed measurements yet. The earlier queue reduction
is an observation, not evidence that this change improved capacity. Five
focused timing/required-gate tests passed. No local builds, Docker, machine
changes or B06 actions were performed.
