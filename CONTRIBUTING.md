# Contributing

## Review and execution

Use a codex-prefixed branch and an isolated checkout. Preserve work in progress.
Keep each PR to one item and about 1,500 changed lines, excluding retained evidence.
Structural changes preserve behavior; identify byte-identical relocation separately.

Every merge needs Howard's approval of the exact final green commit. Post the
head and CI run links in a PR comment and keep the body current. A changed head
requires fresh applicable CI, including reproduction checks, before approval.
Verify the actual target branch is an ancestor and mergeability is clean.
Never force-push, rewrite history, or squash existing history.

Tests, generators, compilers, application workloads and model workloads run in CI.
Local review may inspect Git, hashes, syntax and structured data. A CI pass is not
permission to sign, activate, consume an attempt or launch Phase 2. Model spend,
native runs and publication follow their scoped approval contracts.

## Evidence and compatibility

- Preserve dated records and original evidence bytes. Publish a new dated
  superseding record or forwarding note when a claim or location changes.
- Do not move or rename a path bound by a live plan, request or readiness receipt.
  The POSTTRAN sign-and-launch cutoff is 2026-10-29 14:46 UTC; follow the
  [current runbook](docs/factory/posttran-phase2-runbook.md).
- Leave compatibility shims for moved imports and commands. Retire a shim only
  after all citing dated receipts have been superseded and retirement is approved.
- Retain new large evidence as Release assets with committed SHA-256 inventories.
  Existing evidence stays intact. Moving decks to Drive needs Howard's separate
  destination decision.
- Keep secrets and customer arrivals out of public records. Never inspect the
  restricted arrival tree during repository maintenance.

## Adding an estate, tool or workflow

**Estate:** propose its layer and boundary using the
[architecture map](ARCHITECTURE.md). Keep pinned source, contracts, reference
behavior and candidate code distinct. Add full equivalence and refusal fixtures;
state public/synthetic/native scope. Existing mixed packages are not a model for
new dependencies.

**Tool:** prefer a thin CLI over reusable library code. Preserve existing commands
and update the [command catalog](SCRIPTS.md). Do not modify frozen entry points
to ease cleanup. Prove reproduction commands in CI before retiring or relocating.

**Workflow:** declare minimum permissions, bounded runtime, explicit triggers and
path coverage for imported code. Emit evidence and test results tied to the exact
head. Do not weaken a gate or count a conditional skip as a pass. Preserve full
failure logs and job metadata before repair.

## Documentation checks

The repository-map workflow checks local Markdown links in the README,
architecture, contribution guide and [documentation index](docs/index.md).
Use Markdown links for repository paths in those guides so CI can validate them.
Keep the README at most 150 lines and the architecture compact enough for two
pages. CI also proves that the archive equals the original source Git blob.
