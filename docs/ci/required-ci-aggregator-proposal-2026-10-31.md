# Required CI runner reduction proposal

Proposal only. No workflow, gate implementation, permission, branch protection or required context changes in this PR.

## Existing requirement and exact set preservation

Main source revision: `626979a423004518b616de03b6de02a31a236cb5`.
Current branch protection contexts: `documentation-and-lint` and `required-ci`, both restricted to GitHub Actions app ID 15368. Keep these contexts, their producer identity, administrator enforcement and all other protection settings.

The gate is dynamic. For a complete changed-file inventory F and exact PR head E, let W(E,F) be every `.github/workflows/*.yml` at E except `required-ci.yml` whose pull_request rule selects F using the existing `selected` function. Workflow identity is its path, not its display name or individual matrix job label. Missing, queued, in-progress, failed, cancelled or skipped selected workflows never satisfy the gate.

Proposed aggregator requirement: W_new(E,F) = W_existing(E,F), using the exact same selection algorithm and all rules from E as inert YAML data. Lint remains an independent prerequisite. Keep complete paginated file inventory, live head/base/ref/count identity, PR number and pull_request event matching, latest run ID/attempt, direct latest-attempt reads, final list reread and a stable terminal snapshot for at least 60 seconds. Compare the live PR identity again immediately before any success update.

The nightly systematic-review and handoff-schedule proposals preserve every pull_request selector, job, assertion and gate rule. Therefore their W(E,F) sets are equal for every F, not just the health-change paths. Systematic-review artifact retention incorporates the existing #482 five-upload 90-day postimage. This does not alter selection or evaluation. This documentation PR leaves all selectors unchanged.

## Options

| Option | Same dynamic requirement set? | Decision |
|---|---|---|
| Replace gate with a fixed subset of named jobs | No: drops conditional workflow selection, workflow completion and current identity/attempt rules | Reject |
| Require every possible named job | No: path-filtered workflows may never appear; matrix names and skipped jobs differ from whole-workflow success | Reject as a drop-in replacement |
| Short event-driven aggregator preserving W and the terminal algorithm | Intended equality, contingent on native proof of event handling and check identity | Preferred proposal; no implementation yet |

## Proposed event-driven shape

Use a trusted-main workflow and a fixed read-only evaluator. Treat PR head workflow YAML as data; never execute candidate code, artifacts or modules with check-writing permissions. Observe PR synchronization/reopening/base changes and relevant workflow lifecycle events. An event is a wake-up hint, never evidence of completion.

Read the current PR identity and complete selected-run inventory once per wake. If anything is missing or active, leave the exact-head gate check incomplete and exit promptly. Do not create success, neutral or skipped acceptance to release a runner. When all required workflows are terminal, use a bounded verification job for the existing 60-second stability window and direct rereads. The long 12,600-second polling loop is removed only in a future implementation after parity proof.

Write the gate check explicitly to the PR head SHA, not the workflow_run default-branch SHA. Verify that the check producer matches existing app ID 15368. Use per-PR serialization plus a monotonic generation bound to head/base/ref/file-count and latest attempts so delayed events cannot overwrite a newer incomplete/failure state with success. An event for an older head cannot affect a newer head.

Reruns are a critical boundary: workflow_run requested does not fire for reruns. Completion-only notifications are insufficient. The future design must invalidate prior success on rerun/start, preserve latest-attempt ordering, and handle dropped, duplicate, delayed and out-of-order events. Supplementary event sources or reconciliation must fail closed, and must not create success while any evidence is unknown. Exact event transport and check-writer capability remain unresolved until a native prototype demonstrates the same refusal behavior.

Preserve the stranded-work report separately from gate waiting; it is an observational step, not an extra member of W. Keep lint behavior on main pushes; the existing gate does not confer PR merge authority on a main-push event. No automatic merge belongs in this design.

## Before switching

Planned parity validation: compare old and proposed decisions for every selected path and event fixture, including omitted pagination, changed head/base/count, wrong PR, wrong event, missing run, each non-success conclusion, matrix failure, duplicate names, reruns, new run IDs during direct reads, terminal snapshot changes, writer failure and delayed events. Preserve all existing tests and negative assertions. Use native shadow mode with no authoritative success output, then obtain a separate exact implementation-head and configuration approval. Never remove the existing gate or relax protection during bootstrap.

Planned promotion: land only inert code first with existing required checks intact, prove exact PR-head/app attribution, and review the complete switch/rollback packet. The mechanism that avoids duplicate competing `required-ci` producers must be part of that packet. Without it, keep the current gate. This proposal establishes set equality as a requirement and source-level selector invariant; it is not evidence of implementation or runtime equivalence.

## Current selected-workflow universe

The following 63 workflows can enter W. Their complete path-filter mappings and job definitions remain in source; applicability is evaluated per PR, not globally required on every PR.

- `.github/workflows/b06-host-review.yml`
- `.github/workflows/b06-provenance-offline.yml`
- `.github/workflows/business-rules.yml`
- `.github/workflows/carddemo-account-view.yml`
- `.github/workflows/carddemo-data.yml`
- `.github/workflows/carddemo-feedback.yml`
- `.github/workflows/carddemo-gap-proof.yml`
- `.github/workflows/carddemo-map.yml`
- `.github/workflows/carddemo-menu-annotations.yml`
- `.github/workflows/carddemo-paragraph-scope.yml`
- `.github/workflows/carddemo-phone-date.yml`
- `.github/workflows/carddemo-render.yml`
- `.github/workflows/carddemo-web.yml`
- `.github/workflows/carddemo-zos-intake.yml`
- `.github/workflows/ci-import-paths.yml`
- `.github/workflows/cloud-runner-offline.yml`
- `.github/workflows/control-tower-decisions.yml`
- `.github/workflows/copau-heldout-helper.yml`
- `.github/workflows/copau-private-prerequisites.yml`
- `.github/workflows/copau-run-boundary.yml`
- `.github/workflows/decidability.yml`
- `.github/workflows/equivalence-automation.yml`
- `.github/workflows/equivalence-storage.yml`
- `.github/workflows/evidence-roadmap.yml`
- `.github/workflows/f8-request.yml`
- `.github/workflows/f8-worker-bundle.yml`
- `.github/workflows/factory-allowlist-feedback.yml`
- `.github/workflows/factory-first-install.yml`
- `.github/workflows/factory-generated-scenarios.yml`
- `.github/workflows/factory-legacy-twin.yml`
- `.github/workflows/factory-reconciliation.yml`
- `.github/workflows/factory-scenario-coverage.yml`
- `.github/workflows/factory-scenario-policy.yml`
- `.github/workflows/factory-systematic-review.yml`
- `.github/workflows/factory-twin-reproducibility.yml`
- `.github/workflows/intcalc-m1-triage.yml`
- `.github/workflows/intcalc-retained-verdict.yml`
- `.github/workflows/intcalc-review-packet.yml`
- `.github/workflows/java-unfenced-format.yml`
- `.github/workflows/judge-qualification.yml`
- `.github/workflows/lightyear-verify-mcp.yml`
- `.github/workflows/local-agent.yml`
- `.github/workflows/mainframe-arrival.yml`
- `.github/workflows/milestone-documentation-pages.yml`
- `.github/workflows/ms71-alloydb.yml`
- `.github/workflows/ms77-batch.yml`
- `.github/workflows/p3-operational-claims.yml`
- `.github/workflows/posttran-attempt1-phase1.yml`
- `.github/workflows/posttran-handoff-deadline.yml`
- `.github/workflows/posttran-key-change-proof.yml`
- `.github/workflows/posttran-phase2.yml`
- `.github/workflows/posttran-review.yml`
- `.github/workflows/posttran-second-opinion.yml`
- `.github/workflows/public-evidence-retention.yml`
- `.github/workflows/repository-map.yml`
- `.github/workflows/review-projections.yml`
- `.github/workflows/service-packs.yml`
- `.github/workflows/tsql-procedures.yml`
- `.github/workflows/tsql-r9-reverification.yml`
- `.github/workflows/twin-index-order.yml`
- `.github/workflows/verifier-qualification.yml`
- `.github/workflows/verify-graph-context.yml`
- `.github/workflows/verify.yml`

## GitHub platform constraints

Path-filtered required workflows can remain pending; a skipped job can report success. These behaviors differ from the current whole-workflow rule. See [required-check troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks) and [status checks](https://docs.github.com/en/pull-requests/reference/status-checks).

workflow_run operates from the default branch and its requested event excludes reruns. See [workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run). Future check output must explicitly bind the PR head and must retain trusted-code isolation.
