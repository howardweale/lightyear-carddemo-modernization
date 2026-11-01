# AGENTS.md — read this first

LIGHTYEAR is a software dark factory: AI agents rewrite legacy code, and a deterministic verifier proves the new code behaves the same, with signed receipts. This repository holds the platform, the CardDemo work, the evidence and the records.

Keep work small and targeted. Most of this repository is evidence you never need to read.

## Current priority

- **Track B, the qualified run, is the only priority.** It covers 19 cases under eight strict gates, all unchanged. Planning basis: freeze on 13 November, run on 19 November or later. If the freeze slips past 13 November, the run moves to the week of 30 November, never 23–27 November.
- **Critical-path work comes first.** That means the #455 rebind, encryption of held-out answers, the run checkers' date fixes, and anything the run depends on. Backlog work happens only when a lane is idle.
- **Track A is retired.** Do not schedule it.

## Hard rules

- **Execution is CI-only.** Do not run test suites, apps, Docker, campaigns or compilers locally. Static checks are fine: `git diff --check`, `python -m py_compile`, reading files.
- **No model calls, signing, imports into a Tower, activation, key generation or key handling.** These are Howard's actions only. Private keys, decryption keys and credentials must never be reachable by the factory, CI, candidate code or agents.
- **No spend without Howard's explicit approval**, with a cap, for every model call, including drills.
- **Never open `work/mainframe/arrivals/`.** Never commit credentials, private keys, customer or partner material, or CMS source.
- **Never rewrite git history.** Never edit dated records (any file with a date in its name), retained receipts or preserved evidence. Supersede them with a new dated record.
- **Never weaken a gate.** Do not relax a fence, checker, threshold or required check to make something pass. Exceptions are exact, named and approved by Howard; there are no wildcards or expiry-free waivers.
- **Never merge #468 or #471.** #468 exists only to run the POSTTRAN comparison; #471 is scratch.
- **Authorization screens.** Do not write or change Java for COPAU00, COPAU01 or COPAUS2C. They are reserved for the factory.
- **Local machine.** Never use port 8768 (B06). Never create a second Factory root. Never do run-bound work in the OneDrive checkout.

## Approvals and decisions

- **Every merge into `main` needs Howard's approval of that exact commit.** Run-bound source, workflows, fences, manifests, Tower or authority code, and main repair PRs need exact-hash approval.
- **Any estimate over 2 days comes to Howard as a decision with options,** not as a plan already under way. The same goes for any date slip of more than 2 days.
- **Batch your questions.** Howard's time is the scarcest resource. Each request to him must be dated, decision-ready, and list what he must physically do.
- **Every Monday,** post a 14-day look-ahead of everything that depends on Howard:
  - decisions and approvals;
  - physical actions (YubiKey touches, private helpers, GitHub environment approvals);
  - purchases, accounts and installs;
  - anything with a lead time over 2 days;
  - calendar windows where he must be present;
  - anything that has never yet run for real, with its first real test date.

## How to work (this keeps runs cheap)

1. **One item per PR, at most about 1,500 changed lines,** not counting vendored source.
2. **Every PR targets `main`.** Do not stack PRs on other PR branches.
3. **Never edit generated status files in a PR.** `docs/factory/current-status.json` and `docs/factory/current-status.md` are rebuilt on `main` after each merge. If your change affects status, change the generator or the input record, not the output.
4. **Merge `main` into your branch at most once,** just before asking for approval, and only if there's a conflict.
5. **Don't wait on CI.** Push, write the PR body, and stop. A later task posts the approval comment.
6. **Read big files narrowly.** Use `jq` with a key path on JSON, and `rg` limited to a folder. Never print a whole file over 50 KB.
7. **Evidence goes to Release assets** with a small committed manifest, read back after upload. Never commit zips, full mutation reports or other large outputs. Copy anything you will cite out of CI artifacts before they expire.
8. **Keep PR bodies short:** what changed, why, the work-order item, what CI must show. No logs, no long history.
9. **Dates and times:** never hard-code a date window, month or UTC offset into a run-bound checker. Pacific time is UTC−08:00 from 1 November to 8 March and UTC−07:00 otherwise; validate real timestamps with their offset.

## Backlog lane

Work outside the critical path is drafts only. It touches no run-bound paths, uses `[skip ci]` for documentation-only commits, and never dispatches the manual milestone workflow (it deploys Pages). Nothing from the backlog lane merges before the run without Howard's explicit decision.

## Claims and public records

- **Operational claims need receipts.** Any new sentence in `docs/` that says something was installed, signed, approved, run or passed CI must link to a public receipt (`#sha256=`), or start with "Not yet" or "Planned". `tools/operational_claims.py` enforces this in CI.
- **State limits.** Every result says what it does not show: twin versus z/OS, synthetic versus real data, scripted versus real providers.
- **Keep business matters out of the repository.** The repository is public. Never write about fundraising, valuation, revenue, pricing (beyond published offers), use of funds, or partner and customer commercial status.

## Do not open (large and rarely needed)

| Path | Why |
|---|---|
| `docs/calibration/` | 569 MB of iDempiere evidence archives |
| `docs/factory/release-evidence-*/`, `docs/factory/equivalence-evidence-*/` | retained campaign outputs |
| `docs/modernization/*evidence*/` | proof archives and mutation reports |
| `brand/`, `docs/control-tower-screenshots/` | binary assets |
| `work/` | local scratch; never committed |
| `*releasability-*.json`, `carddemo-slice-*.json`, `current-status.json` | large generated records. Use `jq` for one key if you must |

## Where things live

| Area | Code | Tests and CI |
|---|---|---|
| Verifier and verdicts | `src/lightyear_judge`, `src/lightyear_evidence`, `src/lightyear_mainframe` | `factory-scenario-policy.yml`, `factory-systematic-review.yml` |
| Dark factory (agents, workspace, ledger) | `src/lightyear_factory` | `factory-systematic-review.yml`, `required-ci.yml` |
| COPAU run fence and policy | `tools/check_java_quality_fence.py`, `tools/check_f2_fence_exceptions.py`, `tools/check_f8_request.py` | `required-ci.yml` (via `tools/ci_gate.py`), `f8-request.yml` |
| Control Tower (signing, decisions) | `src/lightyear_control_tower` | `control-tower*.yml` |
| Knowledge graph and business rules | `src/lightyear_knowledge_graph`, `src/lightyear_business_rules` | `verify.yml` |
| CardDemo data (VSAM and IMS to PostgreSQL) | `src/lightyear_data/carddemo` | `carddemo-data.yml` |
| CardDemo web slice (Java, UI, proof) | `factory/carddemo-web/`, `src/lightyear_data/carddemo/reference_*` | `carddemo-web.yml` |
| INTCALC and POSTTRAN release path | `tools/*intcalc*`, `tools/*posttran*`, `docs/factory/` | `posttran-phase2.yml`, `posttran-handoff-deadline.yml` |
| T-SQL procedures | `src/lightyear_data/tsql_procedures`, `data-modernization/tsql-procedures/` | `verify.yml` |
| Status page and decision packet | `tools/build_factory_current_status.py`, `tools/release_status_records.py` | `review-projections.yml` |
| Operational claims | `tools/operational_claims.py`, `tools/check_record_commit_claims.py` | `required-ci.yml` |
| Pinned upstream sources | `spec/` | — |

Tests live in `tests/test_<area>*.py` and run with `PYTHONPATH=src:.:tests python -B -m unittest <module>`, in CI only. `verify.sh` runs the full discovery suite.

## Before asking for approval

- CI on the final head is green.
- Post one comment: `Final green head: <sha>, CI run <link>.` Post a new one after any later push.
- Every merge into `main` needs Howard's approval of that exact commit.

Work orders from Howard live outside the repository and are pasted into your task. Follow the one you were given, and nothing more.
