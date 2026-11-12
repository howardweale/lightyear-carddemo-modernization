# Public attempt journal metrics

Planned: an observational collector for the nineteen-control-drill report. It reads
caller-selected public journal exports, checks the exact byte digest and hash
chain, and projects bounded public fields. It does not authenticate a signer,
admit a request, reconcile the full controller protocol, or qualify P5.

## Terminology correction — 11 November 2026

The nineteen are pass/fail control drills: two clean controls plus seventeen
variants across eight P5 drill families. They are prerequisites to behaviour
execution, not scored behaviour cases and not the behaviour denominator N.
Drill-family names do not establish the mapping to the eight strict gates.

The inventory keeps schema `factory-metrics-inventory/1` and the legacy key
`case_ids`. For this control report, that field is intended to contain the
nineteen control IDs from the exact inventory requiring separate approval.
The collector currently checks nineteen unique valid identifiers; it does not
enforce equality to the qualified-run report's control-ID list. This documentation
correction changes no schema, collector, gate or evidence classification.

The inventory also contains `exact_e` (the source commit) and `journals`. Each journal entry contains a relative `path` and `binding`:
`case_id`, `exact_e`, `execution_id`, `workflow_run_id`,
`workflow_run_attempt`, `attempt_identity_sha256`, `source_sha256` and
`journal_head_sha256`. These associations need independent authentication
against the receipt inventory and its signatures. A hash alone establishes no authority.

The emitter is `tools/report_attempt_metrics.py INVENTORY NEW_OUTPUT`.
It refuses an existing output, source drift, conflicting snapshots of one
attempt, foreign observation tickets, malformed chains and unknown event kinds.
Duplicate exports of the identical attempt contribute once. Every expected
control remains present under the legacy case fields; absent evidence is UNOBSERVED.
UNOBSERVED is a metrics observation state, not a control PASS, tier assignment,
or permission to start behaviour execution.

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
joins to execution receipts and their authorization are still outstanding. The report cannot
attest them from self-described metadata or hashes.
