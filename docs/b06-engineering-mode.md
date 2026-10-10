# B06 Oracle engineering mode

Status: implementation prepared; native validation and standing approval pending.
This is a separate, uncredited Oracle-only investigation path based on the strict
#293 diagnostic observer. It does not use #296's accepted unmatched-return mode.
No PostgreSQL instance, pair adjudication, census slot, model call or measurement
is created. Existing J1 business predicates and historical artifacts are unchanged.

## Approval proposed to Howard

- Calendar: **October 11, 2026, 9:00 AM–9:00 PM PDT** (16:00 UTC October 11
  through 04:00 UTC October 12), subject to no overlapping J1/B06 evidence window.
- At most **10** attempts, **one command per attempt**, including failed attempts.
- Fixed application image:
  `sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`.
- Supporting carrier:
  `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`;
  Oracle seed image:
  `sha256:96c4bda58cd8a8dfda586b2d83a2eb2a3e9f28fda0f1915d3fd758c890dc02b7`.
- Per attempt: **60 minutes work + 10 minutes cleanup**, candidate watchdog
  **1,800 seconds**. Last full-budget start **7:50 PM PDT**. The window cannot
  be extended by a retry. A cleanup failure stops the session.
- Docker limits: Oracle 6 GiB/2 CPUs, trusted carrier 8 GiB/4 CPUs,
  application 8 GiB/4 CPUs, observer 768 MiB/1 CPU. These are per-container
  limits, not reservations or a new Docker configuration.
- Diagnostic limits unchanged: 500,000 audit records/128 MiB; 50,000 non-audit
  records. Output stop threshold 8 GiB, polled once per second (not a filesystem
  quota; some overshoot is possible). Require 60 GiB free before starting.
- Output root:
  `C:/Users/howar/OneDrive/Documents/ChatGPT/lightyear-carddemo-modernization/work/b06-engineering`.
- Any other anomaly stops that attempt, no degradation. No qualification or
  measurement credit even when the observer completes.

This is a proposal, **not approval**. Do not create a standing-approval record until
Howard explicitly approves these bindings. Record his real approval reference and
time, seal the record and pin its exact file SHA-256 when invoking the command.
The approval file binds the output root so a second root cannot reset the cap.
No Tower decision or full snapshot freeze is required for each engineering run.

## Execution and preserved inputs

The CLI is `python -B -m tools.ms94_b06_engineering_run`; it requires an approval
file, its approved digest, the retained #293 asset root, exact template plan,
separate output root and existing signing-authority root. It cannot create
approval or keys. It uses the existing authorized signer entry point only after
approval checks. Do not execute it during the current evidence window.

The retained template is bound to content hash
`54d08a53f748fa11a13df8f771b5f50f76e3383c32330346c2f15be854ba17e9`, source
`b0d5749c0a876b7977d8c64bdeca65706b6c129f`. Only its inputs are copied to each fresh
owner. Its snapshot, old outputs, approvals and receipts are never changed or
reused as authority. Runtime source and controller source are recorded separately.
The current implementation deliberately pins the strict baseline observer; changing
its compiled bytes needs an explicit prospective adapter change with regression
proof, not an edit to the old asset root.

An exclusive session lease spans admission through cleanup and artifact sealing.
An interrupted attempt leaves the lease and consumed run directory behind; no
automatic stale-lock recovery exists. Before starting, read the registered evidence
launch directories, refuse an armed launcher without exit, enforce excluded windows,
and refuse any active journey-labelled Docker container. The approval's registered
evidence directories must remain accessible. The operator must register future
evidence windows before any engineering invocation; unregistered calendars cannot
be inferred from Docker. A running worker checks registered evidence state too.

All containers share an owned internal network, publish no host ports and use the
same inherited password handling and cleanup. Actual absence of owned containers,
networks and volumes is required before another attempt. The outer process bounds
work and terminates the child tree before owned-resource recovery. Cleanup still
attempts removal on a timeout; exceeding the reserve is a failed session, not an
extension or successful run.

## Artifact labelling and refusal

Plans, control records and signed broker receipts carry `run_class: engineering`,
`qualification_credit: false`, `measurement_credit: false`. Strict #293 event schemas
and binary class files cannot accept arbitrary extra fields: their unchanged bytes
are enclosed by labelled, signed per-file descriptors in `artifacts.json`. These
descriptors bind every local raw file by path, length and SHA-256. No historical
stream is rewritten merely to label it.

The new engineering artifact type, recursive labels and separate-root marker are
refused at native input admission, qualification execution/replay, Tower request
construction, census plan assembly, controller startup/result admission and B06
measurement admission. Generic measured-native admission also rejects engineering
campaigns/builders. A copied labelled artifact cannot become qualification evidence
by moving or resealing it. Stripping labels also invalidates signed bindings; the
Oracle-only package lacks the required pair evidence. This does not claim protection
against an administrator rewriting verifier code or forging signing authority.

Tests exercise these production boundaries, cap consumption, approval/calendar
failure, stale leases, Oracle-only preparation and cleanup after setup failure.
They mock Docker and never run a JVM. Native operation remains unproven until an
approved engineering attempt. Merge requires Howard's commit-specific approval.
