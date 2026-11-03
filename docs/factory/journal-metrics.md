# Public attempt journal metrics

Planned: an observational collector for the nineteen-case report. It reads
caller-selected public journal exports, checks the exact byte digest and hash
chain, and projects bounded public fields. It does not authenticate a signer,
admit a request, reconcile the full controller protocol, or qualify P5.

The inventory uses schema `factory-metrics-inventory/1`, `case_ids` (nineteen
unique IDs from the approved case inventory), `exact_e` (the source commit),
and `journals`. Each journal entry contains a relative `path` and `binding`:
`case_id`, `exact_e`, `execution_id`, `workflow_run_id`,
`workflow_run_attempt`, `attempt_identity_sha256`, `source_sha256` and
`journal_head_sha256`. These associations need independent authentication
against the signed receipt inventory. A hash alone establishes no authority.

The emitter is `tools/report_attempt_metrics.py INVENTORY NEW_OUTPUT`.
It refuses an existing output, source drift, conflicting snapshots of one
attempt, foreign observation tickets, malformed chains and unknown event kinds.
Duplicate exports of the identical attempt contribute once. Every expected
case remains present; absent evidence is UNOBSERVED.

Generation transport estimates, logical conservative accounting, pending
logical reservations and conservative count exposure are separate. The report
does not add overlapping components or label estimates as actual billing.
An unknown count retains its entire recorded hold. Known subtotals carry a
missing-observation count; they are not complete run totals.

A transport reservation precedes the opener. Its presence is not proof of a
physical send. Generation usage and count-endpoint estimates stay separate.
Missing cached/reasoning usage remains unknown. Journal UTC timestamps do not
establish monotonic elapsed time. Missing human coverage does not mean zero
interventions.

Not yet: production hooks, complete human-event coverage, monotonic
phase timing, physical-send proof, invoice reconciliation, authenticated final
receipt joins, native qualification and final source/request binding. This
tranche implements the read-only journal collector and deterministic JSON
emitter; it does not complete the metrics work item or change any existing gate.
Planned: synthetic regression tests run in the existing full Verify discovery suite.

## Human-event observations

Planned: the optional inventory field `human_events` supplies a relative `path`,
exact `source_sha256` and `campaign_id` for a public human-event JSONL export.
`encode_human_event` produces structured records for a separately owned durable
sink; it performs no signing or live append. Each record binds the source commit,
campaign, actor ID, affected cases, optional execution IDs and public evidence
digests. Action labels are restricted to the agreed intervention categories;
there is no free-text notes or private-material field.

Corrections append a new event ID pointing to the latest superseded ID. The
collector retains the original rows, rejects correction forks, and counts the
latest version once globally and on each affected case. Empty streams and
unreferenced cases have zero *observed* events, but their actual intervention
counts remain unknown. Complete coverage, human identity authentication and
joins to authorized execution receipts are still outstanding. The report cannot
attest them from self-described metadata or hashes.
