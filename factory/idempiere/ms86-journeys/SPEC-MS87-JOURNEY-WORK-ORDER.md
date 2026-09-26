# MS-87 · MS-86 as one repeatable, unattended work order

For an agent with repository access. Checked against `6f560f0`.
Branch: `ms87-journey-work-order`.

The declaration is supplied at `factory/idempiere/ms86-journeys/work-order.json`,
pinned to MS-86's real values: image digests, harness hashes, source and seed
commits, and recorded outcomes. **Take it as given.** Change a value only if the
recorded evidence contradicts it, and say so in the PR.

---

## Why this milestone exists

MS-86's verdicts were deterministic, but **its live run was manual.** The README
gives native execution as prose steps: build the pinned checkout, copy the
harness into the test module, run Maven with `-Dtest=`, and supply properties and
`user.timezone=UTC`. Codex performed those steps one at a time, at a person's
direction.

This milestone turns that into one declared work order that the platform runs
unattended from start to finish. It prepares the databases, executes both sides,
verifies, records exceptions, stops where a person must decide, and cleans up.
It must stop only where it's designed to stop, and its journal must show that.

---

## Two modes, and why this milestone is only the first

**Replay** re-runs MS-86 exactly as declared. There is nothing to generate, so
**the builder agent is idle and the model budget is zero.** Planning and failure
analysis use the deterministic `LocalAgentSet`. That's correct, not a limitation:
a regression run needs no model. Its claim is "unattended run," not "dark factory
generated this."

**Extend** adds a new declared journey, for example partial invoicing. There the
builder writes the new harness journey inside `allowed_paths`, within the work
order's patch and model budgets, and the gates judge it. **That is the real dark
factory test**, and it's MS-88. Build replay first, because extend mode reuses
every stage below it.

---

## Stage map: reuse, not rebuild

| Stage | Existing component | New work |
|---|---|---|
| **Plan** | Factory `plan()` in `LocalAgentSet`; the headless agent's plan digest | Resolve the checkpoint and schema references to hashes, check images, memory and disk, and emit a plan listing everything that will be created and destroyed. A stale plan digest is refused at start. |
| **Prepare** | Campaign engine: detached runs, signed journal, signed authorization and recovery | A local lane runner: containers from pinned digests, an internal-only network, restore of the admitted checkpoint, the reviewed schema repairs, entry-state verification. |
| **Execute** | The two MS-86 Java harnesses, unchanged | Automate the README's manual steps: build the pinned checkout, place the harness, run it with Maven for each engine, capture readback, and retain every attempt. |
| **Verify** | `GateContract`, whose output is hidden from the builder by default | `lightyear_calibration.journey_order` with the six gate subcommands named in the declaration. |
| **Exceptions** | Factory `analyze_failure()` | Deterministic classification: environment (retryable), entry-state mismatch, unknown difference, known finding changed, cleanup failure. |
| **Decisions** | Workflow approval-required action kinds; the Control Tower queue | Routing, plus one new approval-required kind: `approve-declaration`. |
| **Clean up** | The campaign engine's recorded cleanup; `cleanup.json` in MS-86 | A guaranteed finalizer with a signed cleanup receipt. |
| **Publish** | `RunIndex.record()`; signed receipts | Record the count of human interventions outside the designed stops. |

---

## Rules the implementation must keep

**1 · Don't weaken the sandbox's `network_mode: none`.** `ExecutionPolicy` rightly
requires it for isolated compute, but a database lane needs the harness to reach
its database. Add a separate `internal-only` mode: a private network with no route
out. Keep `none` exactly as it is.

**2 · Clean up first, then wait.** When a decision is needed, the run records the
request, cleans up completely, and only then halts at `human-decision-required`.
It never holds containers while waiting for a person. `resume` re-runs only the
affected cases.

**3 · Cleanup always runs**: on success, failure, cancel, timeout and halt. It
removes containers and the network, destroys credentials, verifies nothing is
left running, and signs a cleanup receipt. Data is retained on failure, for
diagnosis. A cleanup failure is itself a recorded exception, and the run cannot
complete.

**4 · Known findings are expected, not failures.** The ShipDate precision loss and
the Oracle `firstOnly()` error must reproduce exactly on every run until a decision
is recorded. The success status is therefore `reproduced-with-known-findings`, not
`passed`, so nobody reads a green run as "no defects." **If a known finding
disappears, that's a decision too.** It may mean iDempiere fixed it, or it may mean
the harness broke. Route it to `classify-intentional-change`.

**5 · The run cannot change its own terms.** Expected outcomes, admitting rules and
harness hashes come from the declaration, which a person approves before its first
run. A run that meets anything unknown routes it to a decision and never admits it.

**6 · Credentials are generated per run** and never written to evidence.

**7 · Pairs run one at a time by default.** The earlier run used six containers.
`plan()` checks memory and disk and refuses to start rather than start and fail.

---

## Decision routing

| Situation | Action kind | Owner |
|---|---|---|
| First run of a declaration | `approve-declaration` *(new)* | business owner |
| A difference no admitting rule explains | `propose-normalization` | business owner |
| A known finding changed or disappeared | `classify-intentional-change` | business owner |
| The open timestamp contract | `accept-contract-equivalence` | business owner |
| Changing any claim flag | `promote-claim` | claim owner |

Adding `approve-declaration` is safe under the existing policy. It adds a stop for
a person, which reduces autonomy, and authority may only ever be reduced.

**Repeatability comes from the declaration hash.** Once a declaration is approved,
further runs of the same hash need no new approvals. Change anything and it needs
approval again.

---

## Acceptance

- **Two consecutive unattended replays** of the same declaration produce identical
  verdicts, identical business outcomes, and both known findings reproduced.
- **The journal records zero human interventions** outside the designed stops.
- **The first run raises the timestamp decision** as an approval-required request.
  It is not silently carried forward.
- **Cancel at every stage leaves nothing running**, with a test for each stage.
- **Injected failures** (a container killed mid-run, a timeout, a harness
  exception) are retried within the declared limits or recorded, and cleanup still
  completes.
- **An injected unknown difference** becomes a decision request and is never
  admitted automatically.
- **A stale plan digest is refused** at start.
- It runs on both Linux and Windows with Docker Desktop.
- MS-86's offline replay still passes.
- The full suite passes, and MS-87's milestone record is written in the same PR
  set.

---

## Delivery

About five PRs:

1. The declaration loader, validator, `plan()` and `approve-declaration`.
2. The local lane runner: internal-only network, pinned containers, checkpoint
   restore, schema repairs, entry-state verification, the cleanup finalizer.
3. Harness execution: automating the README's manual steps.
4. The gates, failure classification, decision routing and `resume`.
5. The journal metric, receipts, the run-index record, two unattended runs, and
   the MS-87 record.

**Cloud cost: $0**, since everything runs in local Docker. **Time: about two weeks
at the recent pace.** The longest items are the harness automation and making
cleanup robust on Windows.

---

## What MS-87 may claim

- An unattended replay of MS-86: zero human interventions outside the designed
  stops, with the journal as evidence.
- Bounded operations equivalence for the declared operations journey on the two
  pinned engines.

**It may not claim** application, schema or platform equivalence, independent
attestation, or bounded boundary equivalence while the timestamp decision is open.
**It may not describe itself as a dark factory generating anything.** That claim
belongs to extend mode, in MS-88.
