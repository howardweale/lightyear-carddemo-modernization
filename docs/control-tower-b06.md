# B06 Control Tower integration

This is the zero-model Tower integration for MS94 B06, separate from CardDemo.
It supplies producer hooks, an immutable-status observer, review requests and a
verified decision consumer. It does **not** contain the multi-journey measurement
worker, qualify J2/J3, authorize a launch or satisfy the full native preflight.
B05 remains frozen and B04 remains void. Operator review; not independent.

## Producer boundary

`lightyear_control_tower.b06.B06TowerBoundary` is called by the future frozen B06
controller. The controller owns its signing key; Tower receives only that public
key. Tower has its own external authority and journal. No private key is copied
or placed in exports.

The producer receives the hashes of the exact canonical review artifact bytes:
campaign, plan, declaration, limits, public commit, executable, template and
amendment. These file hashes are distinct from any embedded content hashes;
both must be checked during full B06 admission. `write_request` creates a
`campaign-authorization` inbox item binding all eight artifacts, and the normal
Tower request digest binds the whole request. Only public review artifacts belong
in that request, never J3's private work order or hidden values.

The required controller call sequence is:

1. Construct one `StatusWriter` and `B06TowerBoundary` per new campaign. Emit the
   ready state. A writer refuses an already populated export directory.
2. Read the launch proof from a fresh authenticated Tower journal. Pass its head
   and the exact request bindings to `launch`. Its admission callback must check
   the pinned interpreter, packages, CLI, tool runtime, client, qualification,
   executable and preflight, and return true only after every check passes.
   Only then may the controller write `started.json` and invoke its supervisor.
3. Call `start_trial` before each slot; call `record_usage` after each model call,
   compilation or other state change. Counters cannot decrease. Call `emit` for
   additional state changes. Time includes operator/provider pauses.
4. Feed a verified completed trial receipt to `finish_and_review`. The method
   exports its unchanged verdict, locks the next-slot boundary if review is
   required, signs a pause and creates the corresponding Tower queue request.
5. While paused, call `poll_pause` with a `DecisionReader` using a scoped agent
   credential. An unanswered request returns no decision. The reader only uses
   authenticated reads; it has no approval operation. Missing, wrong-pause,
   superseded, expired, wrong-scope or invalid proofs cannot lift the pause.
6. `continue` allows the next fresh slot; `stop` and `void` close the boundary.
   Neither outcome changes prior trial verdicts. The boundary cannot reopen a
   terminal state. Existing supervisor hard deadlines still govern execution and
   finalization; this component does not replace them.

Repeated fingerprints are deduplicated within each trial and compared only within
the same journey across different trials. Equipment-suspect and provider-unavailable
outcomes require whole-campaign review. `request_pause` also supports the sealed
harness-defect reason; the final J3 amendment rules remain a controller prerequisite.
Provider-unavailable records are excluded from candidate pass-rate denominators.
The eventual controller must enforce the three permitted pre-evaluation provider
retries, schedule, receipt verification and journey-level void policy; the Tower
does not invent replacement slots or rewrite results.

## Windows-safe status channel

B06 is the first producer of the generic [`tower-status-export/1` protocol](control-tower-status-export.md). Its profile adds B06 journey and budget validation without changing the common reader.

After each state change, the producer signs `tower-export/000001.json`, then the
next numbered file, chaining each to the preceding content hash. It writes and
flushes a uniquely named pending file, closes it, and renames it exactly once into
the final name using an OS-enforced no-replace operation. Existing files are never
replaced. The rename removes the pending name.
The observer opens only numbered completed files. It never opens `active.json`,
`progress.json`, journals or other mutable controller files.

The adapter checks producer signatures, consecutive sequence numbers, chain,
campaign bindings, closed schemas, nondecreasing timestamps/budgets and unchanged
prior verdicts. Tampering or a gap makes the view unavailable. This proves the
visible signed prefix; it does not prove that a withheld tail does not exist.
Staleness is shown at 45 minutes without an export while a trial is active.
No private archive replay is claimed by status verification.

The cockpit shows J1/J2/J3 separately, pilots excluded, interim Wilson intervals,
active slot, pause and queue request, budget alerts at 80% and 100%, latest-launch
expiry and period-boundary risk. It distinguishes fixture rehearsals from actual
measurements. B06 decisions are labelled operator review, not independent.

## Local configuration and startup

Use a separate B06 Tower data root and authority outside the engine root. Do not
point a legacy adapter at B05 or label mutable files as an immutable export.
The generic `tower-status-export` adapter uses producer profile `ms94-b06`, scope
`ms94-b06` and read mode `write-once-status`.

Once the B06 freeze supplies a first signed ready export, its public key and
`tower-bindings.json`, register it explicitly:

```powershell
python -m lightyear_control_tower.b06 --root $B06TowerRoot --exports $B06ExportDirectory --producer-public-key $B06ProducerPublicKey --bindings $B06TowerBindings
```

The command verifies the stream before creating `control-tower/campaigns.json`.
It refuses to overwrite an existing registry, grants no roles and starts nothing.
Use the existing `provision`, `grant-roles` and `add-identity` commands from the
[Console guide](control-tower-decision-console.md): scope `ms94-b06`, Howard with
`operator campaign-authorizer`, controller reader with only `agent`. Keep the
authority and credentials outside both engine-writable roots and exports.

Start the **decision service**, not the older Graph Explorer wrapper:

```powershell
python -m lightyear_control_tower serve --root $B06TowerRoot --authority $B06TowerAuthority --port 8768
```

Open `http://127.0.0.1:8768/` and sign in with Howard's individual credential.
Port 8768 avoids replacing the existing dashboard on 8766. Review the launch
request in Work queue; when paused, review the named `b06-pause` item and choose
`continue`, `stop` or `void`, with a reason. The controller reads the signed
decision; Tower never starts or kills a process. No operational B06 identity or
approval is created by the integration tests.

## Validation and remaining gate

`tests.test_b06_tower` runs real signed Tower decisions and HTTP/SSE/MCP reads with
disposable, distinct producer and Tower keys. Its Windows regression repeatedly
replaces a simulated controller file while a concurrent observer reads exports,
checking bytes and timestamps and requiring no failed replacement. It also covers
wrong pause, admission failure, deadline, scoped repeated causes, provider pause,
terminal-state refusal, disclosure schema, signature tampering and sequence holes.

`tests/browser/b06.mjs` checks all three journey panels, fixture marking, decision
consumer wording, pause alerts, launch time and exactly the three pause choices.
It submits no browser decision and uses no models, databases or Docker.

Local validation on Windows after the generic transport revision: 70 tests passed,
with two existing platform/optional-SDK skips (72 total). This includes the 13 B06
and five generic transport tests. Both real producer/reader concurrency tests and
the competing-writers no-overwrite test passed. The Chromium rehearsal passed for
a generic stale campaign and the B06 cockpit and pause choices, with no page
errors or external requests. Its first attempt timed out during Chromium startup;
a retry after the unit suite finished passed. These are software integration
results, not native qualification or measurement evidence. CI includes the tests
on Windows, Linux and macOS and the browser rehearsal on Linux; remote CI has not
run for this local change.

The full B06 executable must still run the required native zero-model preflight
for all three journeys, under supervision, with archive replay, cleanup and this
Tower round-trip. No production launch command or latest safe launch timestamp is
claimed until that executable and its calendar-relative plan are frozen and approved.

The B05 terminal audit passed before this protocol revision: all 31 archives
replayed, 279 owned resources absent and 1,879 protected files unchanged. See the
[B05 results](calibration/idempiere-ms94/stage-b-05/results/README.md). The audit
was not rerun during this change.
