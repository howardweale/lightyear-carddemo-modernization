# MS #72 Step 2 — Six CloudBank action kinds

The headless engine works while the Control Tower is closed. It admits fixed
operations, records attempts and evidence in a transactional journal, and resumes
unfinished work from a checkpoint. The Tower reads verified engine evidence and
records authenticated human decisions. It never dispatches these workers.

## What the six kinds accomplish

| Action kind | Prerequisite | Concrete CloudBank operation | Retained result |
|---|---|---|---|
| `widen-observation` | Published synthetic evidence within the declared local scope | Reproduce the eight services' deterministic contract, mapping and patch checks | Eight service receipts |
| `escalate-lane` | The corresponding service contract passed; retained lane permitted | Verify the original MS54–67 publication, its 31 files, hashes, cross-receipt bindings and service coverage | Eight retained-evidence receipts |
| `reparse` | All service evidence passed; a registered newer grammar exists | Reparse the original MS67 platform observation with grammar v2, retaining typed scenario status and evidence hashes that v1 only indexed by name | One parser receipt with 28 typed records and both grammar identities |
| `extend-corpus` | The parser receipt passed; published synthetic scenarios fall within the declared capture scope | Add the 28 existing platform scenarios to the eight service evidence cases | One corpus receipt: 8 previous cases, 28 added, 36 total |
| `rerun` | The admitted corpus changed; local observation permitted | Check all 28 added scenario outcomes and their links to the verified original publication | One rerun receipt binding the previous and expanded corpus hashes |
| `apply-ledger-entry` | Rerun passed, plus current signed human approval of exact terms | Apply the existing MS61 `successful-value-conservation` entry to its recorded Oracle/PostgreSQL observation identities | One derived projection with both complete raw lane records, the normalized comparison and signed human provenance |

The previous delivery executed **16 actions across two kinds**. The expanded
adapter supports **all six kinds**. Its dependency order currently creates six
planning rounds; round count and action-kind count are separate measurements.

Without a provisioned human decision, a normal run completes **19 observations
across five kinds**, verifies eight services, and stops with
`human-decision-required`. It records zero ledger applications and does not claim
full convergence. With a valid decision it completes **20 actions across six
kinds**, including one ledger application. A narrowed policy, missing evidence,
worker failure or exhausted budget can stop it earlier.

These are fresh **local analyses of retained evidence**. No action starts Oracle,
PostgreSQL, a cloud service or a model. Corpus extension imports already published
synthetic records; it does not capture new customer data. The parser's v1 baseline
is reconstructed explicitly for comparison, not represented as a prior recorded
run. This is a bounded JSON evidence grammar, not a new SQL or application parser.
Original MS67 identity and application verdicts remain intact. Public HMAC
verification remains attributed to the original operator exporter.

## Start, pause, resume and inspect

From the repository root:

```bash
export PYTHONPATH=src
python -m lightyear_workflow.execution run
python -m lightyear_workflow.execution verify
./live-control-tower.sh serve
```

PowerShell uses `$env:PYTHONPATH = 'src'` and `.\live-control-tower.ps1 serve`.
`run` and `verify` exit 1 for a halted or invalid run, including an absent human
approval; this is an explicit incomplete result, not a worker crash. `export`
exits 0 when it successfully exports a verified journal, including a halted run.

```bash
python -m lightyear_workflow.execution run --run-dir work/workflow/restart-demo --max-steps 3
python -m lightyear_workflow.execution run --run-dir work/workflow/restart-demo
python -m lightyear_workflow.execution export --run-dir work/workflow/restart-demo --output work/workflow/restart-demo/events.json
```

The same `run` command resumes a paused journal. Completed actions never repeat
within that journal. Interrupted attempts consume their retry budget. Ledger
application means committing a derived projection in the engine journal; it never
mutates the original ledger or a business system. This makes restart after the
application commit idempotent. A terminal halt stays terminal: after obtaining an
approval, changing inputs or changing policy, use a **new run directory** and
retain the old record. Restart downtime counts toward the run's time budget.

Default files are under `work/workflow/cloudbank`: `events.sqlite3` contains the
ordered event and receipt chain; `writer.lock` excludes a second engine;
`convergence.receipt.json` is a derived report. Parser, corpus, rerun and approved
projection artifacts are embedded in their action receipts. `verify` reconstructs
each observation and transition, rather than trusting a stored success flag.

The committed `control-tower/cloudbank-execution.example.json` records the default
five-kind run and its human-decision stop. It is labeled as a recorded example,
used only without an engine journal, and invalidated by changed source or policy.
It contains no synthetic approval masquerading as a human decision.

## Provision and review the sixth action

Install the existing signing support with `python -m pip install -e ".[control-tower]"`.
For a local reference-estate operator, provision a separate CloudBank authority:

```bash
python -m lightyear_control_tower init-operator --authority work/control-tower/cloudbank-authority.json --workload cloudbank:retained-value-conservation --operator-id YOUR_ID --operator-name "YOUR NAME"
```

This creates an individual local credential, service signing keys and
`work/control-tower/cloudbank-trust.json`, containing only the public key and
trusted operator identity. It grants **no approval** and refuses to overwrite
existing authority files. Start the Tower with this authority:

```bash
python -m lightyear_knowledge_graph serve --decision-config work/control-tower/cloudbank-authority.json
```

Sign in through the existing operator dialog using the generated credential.
Review **CloudBank · Retained value conservation**, including exact terms, entry
and ledger hashes, the source receipt, allowed comparison and retained differences.
Approve or reject it with a reason, named owner and review date. CloudBank decisions
have their own `work/control-tower/cloudbank-decisions.sqlite3` journal. Existing
CardDemo credentials, ledger and historical proof workflow remain separate.

The headless executor receives no signing key or operator credential. It checks
Ed25519 signatures, continuous journal order, trusted human identity, an active
session at decision time, review before approval, exact workload/entry/ledger
bindings, latest decision and expiry at midnight UTC on the review date.
Immediately before application it checks
again while reserving the decision database against a concurrent writer, keeping
that reservation through the engine's receipt commit. Revocation during a worker
therefore prevents application. The engine does not write the decision journal.

The projection retains the raw Oracle and PostgreSQL lane records, their unequal
raw comparison, every declared implementation difference, and the normalized
observation identities. It suppresses no fields and promotes no new claim.
Its terms allow exactly one such application per run. A historical application
remains visible after subsequent revocation; the Tower separately reports that
its approval is no longer current. Replay requires the original human decision
journal so a signed prefix cannot hide a decision already present at application
time. An execution export alone is insufficient for an applied-ledger replay.

## Bounds and integrity

`control-tower/execution-policy.json` selects the code-owned
`cloudbank-evidence-actions-v2` adapter. Limits remain eight iterations, 32 total
attempts, two attempts per action, 300 elapsed seconds, 15 seconds per worker,
16 MiB of admitted input and 64 KiB of worker output. The separately read human
journal is bounded to 256 events and 256 KiB. Configuration can only narrow
execution authority. Changing a kind to `always-ask` stops that action and its
dependents; other kinds cannot substitute for it.

Workers use a fixed Python entry point and filtered environment. There are no
submitted commands, arbitrary SQL, network, cloud-management or model operations.
This is an application capability boundary, not a general OS sandbox. Input
admission binds the CloudBank files, implementation, policies and public trust
configuration; symbolic links and excess input are rejected. Source drift, raw
mismatch and budget stops persist. Unreadable evidence remains unavailable.
The engine's independent verifier rejects invented worker output and resealed
verdict changes. This establishes local content and transition integrity within
a trusted host, not independent remote attestation or protection from a host
administrator replacing all trusted state.

## Control Tower and validation

`GET /api/workflow/execution` is read-only. The Tower shows all six action kinds,
their prerequisites, verified counts, blocking reasons and receipts, alongside
the eight service cards. Derived evidence and human provenance can be inspected.
Invalid evidence or disconnection clears the verified display. There is no
browser route to start, resume or apply an engine action.

The automated tests exercise real subprocess workers, restart without repeated
applications, all six kinds with an explicitly synthetic test operator, missing
approval, expiry, revocation during work, writer exclusion, wrong scope, altered
signatures, unreviewed terms, policy narrowing, tampered receipts and budgets.
The positive fixture demonstrates the mechanism; it is not a real operator or
customer decision.

CI's `browser-inspection` job checks Chromium and WebKit at desktop and mobile
sizes: six action cards, eight service cards, the human gate, receipt readability,
overflow, filters, invalid states, JavaScript errors, absence of workflow writes,
and unchanged journal bytes. The `ms72-browser-inspection` artifact retains the
screenshots for visual review. Locally, run `npm ci`,
`npx playwright install --with-deps chromium webkit`, then `npm test` from
`tests/browser`. Network policy may require these checks to run in CI.

Fresh runtime adapters, new customer captures, broader normalization proposals,
weekly owner reports, agent drafting and customer SSO/OIDC remain later work.
