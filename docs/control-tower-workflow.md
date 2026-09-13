# MS #72 — Control Tower workflow

The headless engine turns admitted verdicts into a source-bound action plan. The
Control Tower reads and verifies that plan and records human decisions. It does not
publish plans, execute actions, accept differences, or promote claims on the operator's
behalf.

This is MS #72, based on `main` at
`fb9f136a73510938fa5bdedc3ad90b23e8e1c780`. MS #71 is assigned to AlloyDB work.
MS68–70 already cover the iDempiere inventory, comparison, and bounded triage.
The signed decision service described in `ms68-control-tower-decisions.md` is reused.

Step 1 emits actions from the existing comparison evidence, as documented below.
Step 2 adds bounded execution in the headless engine and uses CloudBank as the
test estate. Step 2 is implemented for service-contract and retained-execution
integrity checks, with durable restart, bounded workers and measured completion
within that scope. Browser inspection runs beside the app in CI. See the
[Step 2 runbook](control-tower-execution.md). Step 1 evidence still establishes
neither execution nor convergence; the two evidence streams stay separate.

## The boundary

> An autonomous action may only produce more evidence. It may never make a
> difference acceptable.

| Responsibility | Headless engine | Control Tower |
|---|---|---|
| Verdicts and comparison receipts | Deterministic authority | Read |
| Action plan and parser backlog | Emit and persist | Read, filter, inspect |
| Human decisions | Consume independently verified decisions | Authenticated operator intent, countersigned by the service |
| Action execution | Bounded CloudBank evidence workers in Step 2 | No execution route |
| Claim promotion | Requires a separate signed decision and evidence gate | No promotion command in this release |
| Convergence | Measured within the Step 2 evidence scope | Read verified journal; Step 1 remains a preview |

The engine runs without a web server or operator session. Stopping the Tower does
not remove the plan or its proposals. An absent plan is unavailable; a plan older
than 24 hours is stale. Changed source evidence, implementation, policy, or plan
content makes it invalid. Reopening the browser never makes evidence fresh.
Snapshot recency is not engine liveness: the view explicitly says that no executor
is deployed. A disconnected browser labels previously displayed data as unverified.

## Delivered behavior

Every source pair has an action-plan result carrying its original verdict and
receipt identity, `sub_verdict`, all applicable `sub_verdicts`, and `actions[]`.
This is an additive sidecar to the content-addressed comparison evidence. Original MS69/MS70
artifacts and their hashes are unchanged.

| Sub-verdict | Next work | Accountable role |
|---|---|---|
| `no-output` | Diagnose failed comparable output; propose rerun | Engineering |
| `unparsed` | Grammar, expression analysis or ordered alignment work | LIGHTYEAR parser engineering |
| `undecidable` | Establish the business domain and any acceptable difference | Business owner |
| `uncovered` | Obtain missing schema, trigger, domain or path observations | Corpus/customer risk owner |
| `unauthorised` | Obtain the named baseline, authorization or provider | Baseline/customer risk/provider owner |

Classification uses exact reason codes. An unknown code becomes our analysis
backlog rather than a customer limitation or implicit waiver. An entity can have
several causes. SQL units use one primary cause in the published order:
`no-output`, `unparsed`, `undecidable`, `uncovered`, `unauthorised`. All causes and
source ranges remain on the actions. Administrative exclusions stay excluded.
The new parser/analysis bucket includes opaque expressions and alignment work;
it must not be confused with the comparator's narrower grammar-only count.

No individual customer owner is invented. Missing assignments are explicit.
Policy can assign accountable names or teams to known roles. The default assigns
our parser work to LIGHTYEAR parser engineering.

## Immutable action authority

The code-owned action catalog includes all fifteen actions in the supplied
workflow. Policy may reduce autonomous execution to `always-ask`, but cannot
raise authority. All five human actions remain `always-ask`:

- `propose-normalization`
- `classify-intentional-change`
- `accept-contract-equivalence`
- `promote-claim`
- `widen-scope`

Blocked actions cannot be made autonomous. `extend-corpus` cannot lose its scope
condition; `apply-ledger-entry` cannot lose its expiry condition. Unknown actions,
missing locks, duplicate JSON keys, unsupported modes, invalid owners, boolean or
out-of-range iteration caps, and removed halt conditions fail at policy parsing.
The Step 1 policy remains `emit-only`. Step 2 uses a separate execution policy
that can only reduce code-owned bounds and also honors this policy's autonomy
reductions and iteration cap. Step 1 still runs zero iterations.

Applying a prior human approval is distinct from creating one. The catalog
requires a trusted signature and journal, current nonrevoked decision, exact
entry/ledger/scope match and expiry checked at application time. It also requires
the raw divergence and the approving human's provenance to remain visible. This
adapter has no admitted iDempiere application receipt, so it emits no claimed
ledger applications. The future executor must implement those gates before that
action can run.

The deterministic verdict code takes no model provider. This planner also has no
provider or process runner. A proposal does not enter the verdict function and
cannot alter its result. A later observation can resolve `indeterminate` either
way; accepting an observed difference always needs the human decision. Even then,
the original divergence is retained and any normalized conclusion is separately
bound to that decision.

## Queue preview and provenance

`GET /api/workflow/plan` projects the engine snapshot with filters and bounded
pagination. The existing authenticated `GET /api/decisions/queue` also includes
`workflow_proposals`, derived from approval-required engine actions. The new
work-plan view renders the same proposals. Existing scoped CardDemo ledger
decisions retain their supported signing workflow.

New engine proposals are **not signable yet**. They show the question, owner,
original verdict hash, source paths/ranges/hashes, affected units and files, and
what approval or refusal would mean. Exact normalization terms and a measured
suppression count are still required before signing. Observed scope is not a
suppression estimate: `suppressed_comparisons` is zero and the proposed blast
radius is explicitly `not-assessed`.

Approval alone would not establish equivalence. Refusing an exception would not
turn an indeterminate into a proven divergence. Those consequences correct the
overly strong wording in the supplied illustrative action.

No example approver, date, entry number, or verdict transition is presented as
real provenance. Future application receipts must name the actual approving
identity, signed record, scope, application time and expiry.

## UI write paths removed

The Tower no longer exposes proof dispatch or qualification receipt generation.
`POST /api/decisions/proof-runs` and `GET /api/decisions/gate` are unavailable. The
old UI buttons now show historical proof state. The legacy headless qualification
command remains available for recorded runs and verifies current decisions.

The default decision service is decision-only. It does not dispatch proofs,
generate qualification receipts, or mark old engine runs interrupted when the UI
starts. A historical `running` record is displayed as historical journal state,
not proof that an engine is alive.

The Tower also no longer starts `OperationalMonitor` or calls `scan()` from the
status endpoint. Its default observation store is read-only and cannot initialize
or append engine evidence. SSE tails independently persisted records. The
existing observer library remains available to a headless service; this increment
does not deploy that service. Until a producer runs, observation freshness is
unavailable or stale, rather than refreshed by a viewer.

## Identity and customer deployment gate

The existing implementation already requires individual local credentials,
registered operator identity, role checks, expiring sessions, loopback clients,
recognized Host, JSON and exact same-origin requests. The same-session review,
Ed25519 countersignature and hash-chain requirements remain. The server constructor
now also rejects a network-bound decision service, closing the direct-construction
path in addition to the launcher check.

Customer SSO/OIDC is **not implemented**. Customer decision deployment remains
blocked until approved SSO/OIDC, issuer/audience/signature validation, role mapping,
credential revocation, session controls and appropriate retention are implemented
and tested. The discovery network override never enables network decision writes;
forwarded user headers are not trusted. A reverse proxy alone is not completion
of this gate. The local reference authority is not customer production approval.

## Run and verify

From the repository root, with its selected Python interpreter:

```bash
PYTHONPATH=src python -m lightyear_workflow emit --report work/workflow/action-plan.md
PYTHONPATH=src python -m lightyear_workflow verify
./live-control-tower.sh serve
```

For Windows PowerShell, set `$env:PYTHONPATH = 'src'`, run the same `python -m`
commands, then `.\live-control-tower.ps1 serve`. The default output is
`work/workflow/action-plan.snapshot.json.gz`; the Tower prefers that engine output
to the committed example. Both are verified against current admitted inputs.
The writer atomically replaces snapshots, so a reader cannot see a partial file.

The [generated action report](control-tower-action-plan.md) and committed
`control-tower/action-plan.snapshot.json.gz` demonstrate the current corpus.
Verification reconstructs the expected sidecar without writing it and rejects
even resealed changes to action classes, verdicts or resolution counts.

## Remaining customer-funded work

1. Extend the implemented Step 2 contract/retained-evidence lane to additional
   specifically admitted actions and fresh customer runtime observations. The
   bounded executor, restart, retry, monotonicity and tamper checks are delivered;
   arbitrary commands and cloud mutations are not admitted by this lane.
2. Bind engine proposals with exact terms and blast radius to signed decisions;
   retain reviewed-before-approved, expiry, rejection and identity checks.
3. Extend Step 2's measured per-run completion receipts with weekly owner-level
   changes. A completed evidence-integrity check is not a claim that nothing
   more can be learned about the application.
4. Add agent drafting after the typed contracts exist. Agents may draft content,
   never select action authority, issue verdicts or approve their proposals.

Step 1 is complete without those later services. It makes the coverage report a
reviewable work plan while recording zero execution, resolution and promotion.
