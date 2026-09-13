# MS #72 Step 2 — Bounded CloudBank evidence execution

The headless engine executes evidence checks while the Control Tower is closed.
It records every attempt and verified result in a transactional journal. Reopening
the Tower reads that journal; it does not start workers or create engine evidence.

## Delivered scope

The first adapter covers CloudBank's eight services: Account, Authorization,
Chatbot, Checks, Credit score, Customer, Test runner and Transfer. Each service
has two code-registered observation lanes:

| Lane | Action | Evidence established |
|---|---|---|
| Service contract | `widen-observation` | Existing CloudBank deterministic artifact verifiers reproduce the checked-in contracts, schemas, mappings, patch bindings and claim boundaries |
| Retained execution | `escalate-lane` | The original MS54–67 publication's 31 files, content hashes, cross-receipt bindings, 28 platform scenarios and eight-service coverage remain valid |

The second lane is available only after the service's contract check passes.
The default successful run makes 16 worker observations over two iterations and
resolves eight **evidence-integrity questions**. It preserves the original MS67
run identity and existing semantic conclusions. These are fresh local checks
of retained evidence, not fresh Oracle/PostgreSQL execution, a cloud health
check, a new equivalence certificate or customer production approval. The
published HMAC verification remains attributed to the original operator exporter.

## Start, pause, resume and verify

From the repository root:

```bash
export PYTHONPATH=src
python -m lightyear_workflow.execution run
python -m lightyear_workflow.execution verify
./live-control-tower.sh serve
```

For PowerShell, use `$env:PYTHONPATH = 'src'`, the same `python -m` commands,
and `.\live-control-tower.ps1 serve`.

To demonstrate a restart in a separate run directory:

```bash
python -m lightyear_workflow.execution run --run-dir work/workflow/restart-demo --max-steps 3
python -m lightyear_workflow.execution run --run-dir work/workflow/restart-demo
python -m lightyear_workflow.execution verify --run-dir work/workflow/restart-demo
python -m lightyear_workflow.execution export --run-dir work/workflow/restart-demo --output work/workflow/restart-demo/events.json
```

The same `run` command resumes unfinished work. Completed actions never run again
within the same journal. An interrupted attempt consumes its attempt budget and
may be retried; these workers are read-only, so a repeat cannot duplicate a
business mutation. A terminal run remains terminal. After changing inputs or
policy, use a new run directory, retaining the old record.

Default engine files live in `work/workflow/cloudbank`: `events.sqlite3` is the
authoritative event/receipt chain, `writer.lock` enforces one engine writer, and
`convergence.receipt.json` is the derived completion report. `verify` checks the
event chain and independently reconstructs each observation and transition. It
does not trust the derived report or a worker-supplied success flag. `export`
retains the complete event sequence for review.

The committed `control-tower/cloudbank-execution.example.json` is a recorded
demonstration. The Tower labels it as such and uses it only when no engine
journal exists. Current source/policy changes invalidate its projection rather
than refreshing the example's time.

## Limits and authority

`control-tower/execution-policy.json` declares the allowed adapter and scope,
with maxima of eight iterations, 32 total attempts, two attempts per action,
300 seconds from the initial start (including restart downtime), 15 seconds
per worker, 16 MiB of declared input files and 64 KiB of worker output.
Configuration can reduce these limits. Unknown fields, other adapters, model
access, network operations and increased limits are rejected. The worker
registry contains no network, SQL, shell, cloud-management or model operations;
this is an application-level capability boundary, not a general OS sandbox.

Workers receive a fixed Python entry point, a registered service and lane,
and a filtered environment without inherited provider/cloud credentials.
The controller independently checks results against the deterministic verifier.
Workers cannot submit commands, make decisions, apply normalizations, select
their own authority or promote a claim. Other catalog actions—including ledger
application—remain unavailable until their separate admission gates exist.
Changing an autonomous action to `always-ask` stops that work and exposes the
need for a human decision; the engine never approves it.

Input admission binds the complete declared CloudBank source/contract/publication
scope and controller implementation, rejects symbolic links and excess input,
and checks it again after each worker and during receipt reads. Budget, source
drift and raw mismatch stops are persistent. Missing or unreadable evidence stays
unavailable; it is not called a proven divergence. A mismatching observation is
retained in its receipt and halts further execution. Exhausted retries and
unavailable lanes remain unresolved.

The journal uses full-synchronous SQLite transactions and an ordered hash chain.
Receipt replay checks action order, budgets, input bindings, expected observation
content and monotonic state transitions, even when someone recomputes hashes.
This provides local content/transition verification; it is not a remote workload
signature or proof of process execution independent of the trusted engine host.

## Tower and browser inspection

`GET /api/workflow/execution` exposes a verified read-only projection. No
`POST /api/workflow/*` execution, resume or plan route exists. Source receipt
hashes, observed errors, budgets and original cloud run remain inspectable.
Recent journal activity is distinguished from completed history, a paused run
and interrupted/unobserved activity. Disconnection or invalid evidence clears
the verified cards. The old Oracle Customer action plan remains in a collapsed
section; it is not presented as the CloudBank executor's input.

CI's `browser-inspection` job uses pinned Playwright dependencies to run the app
and browser on the same runner, with the existing loopback boundary. It checks
Chromium and WebKit at desktop and mobile sizes, logo loading, eight services,
receipt column width, horizontal overflow, filters, invalid-evidence display,
JavaScript errors, absence of workflow writes, and unchanged journal bytes.
The `ms72-browser-inspection` artifact retains screenshots and a JSON report.
This follows [Playwright's CI setup](https://playwright.dev/docs/ci) and
[screenshot support](https://playwright.dev/docs/screenshots).

Run the same inspection locally with:

```bash
cd tests/browser
npm ci
npx playwright install --with-deps chromium webkit
npm test
```

No remote preview tunnel or network-bound decision service is needed. Screenshots
are captured from the live runner application and should be visually reviewed
alongside the automated geometry and interaction checks.

## Remaining later-step work

Exact signed terms and measured suppression radius for new decision proposals,
ledger application, additional fresh-runtime adapters, weekly owner reports,
agent drafting and customer SSO/OIDC remain separate work. Step 2 does not
silently grant those capabilities or replace the earlier signed CloudBank record.
