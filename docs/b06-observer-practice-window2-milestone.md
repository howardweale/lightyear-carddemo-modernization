# B06 observer practice replacement window milestone

The corrected observer is published and tested offline. Its previous r2 window
expired without arming or native execution; the new preparation changes only the
time window for its never-started pair. The native pass remains outstanding.

PRs #285, #286 and #287 merged the observer-v2 integration, catch activation proof,
bulk reads, execution watchdog and startup suspension correction. PR #289 merged
the prior r2 preparation records. PR #290 separately changed two unrelated CI
PostgreSQL pulls to Docker's official digest-pinned ECR Public mirror; those CI
changes are not introduced into this frozen B06 runtime. B06 source remains
`8031ad1c7376f207854d6f99df6a9e80665d0e9a`.

## Replacement preparation

Howard asked to start B06 as soon as possible. The replacement target is October 9,
4:15–7:15 PM PDT, with a latest full-budget start of 5:05:10 PM PDT. One J1 retained
reference Oracle/PostgreSQL pair retains its 7,190-second budget and 600-second
cleanup reserve. No retries, replacement slots or automatic window extensions apply.

Full freeze and final verification passed: 113,579 file hashes,
767 published source comparisons and 41 focused frozen tests.
The window amendment proves 113,578 unchanged files and exactly one
native plan changed only in docker_run_window and content_sha256.

The [public preparation records](calibration/idempiere-ms94/stage-b-06/preparation/observer-practice-r2-window2/README.md)
bind snapshot `e58ea4f5ed0cf1b5347fb256a0d9a425e244530d6af2b24f598682ecd3c77076` and plan
`32d2345c386c350c40bd5ca637bcb60690c78a78f018a30dbf010d2ba047327d`. Preparation performed zero Docker commands, model calls
or native pairs. Prior snapshots and native failures remain unchanged.

## Admission and remaining work

The exact new public commit, plan, snapshot and window require a fresh signed Tower
decision before the one-shot launcher can run. A practice pass is required before
the five-path census, journey qualification and B06 measurement. This milestone
claims no native success or measurement credit. Operator review, not independent
attestation.
