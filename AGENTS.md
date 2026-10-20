# AGENTS.md — read this first

LIGHTYEAR is a software dark factory: AI agents rewrite legacy code, and a deterministic verifier proves the new code behaves the same, with signed receipts. This repository holds the platform, the CardDemo work, the evidence and the records.

Keep work small and targeted. Most of this repository is evidence you never need to read.

## Hard rules

- **Execution is CI-only.** Do not run test suites, apps, Docker, campaigns or compilers locally. Static checks are fine: `git diff --check`, `python -m py_compile`, reading files.
- **No model calls, signing, imports into a Tower, activation or POSTTRAN Phase 2.** These are Howard's actions only.
- **Never open `work/mainframe/arrivals/`.** Never commit credentials, private keys or CMS source.
- **Never rewrite git history.** Never edit dated records (any file with a date in its name) or preserved evidence. Supersede them with a new dated record.
- **Frozen paths.** Until 2026-10-29 14:46 UTC, do not touch anything bound by the POSTTRAN plan: `docs/factory/posttran-phase2-*`, `tools/run_posttran_phase2.py`, `tools/posttran_phase2_authorization.py`, or the plan's bound files.
- **Authorization screens.** Do not write or change Java for COPAU00, COPAU01 or COPAUS2C. They are reserved for the factory.

## How to work (this keeps runs cheap)

1. **One item per PR, at most about 1,500 changed lines,** not counting vendored source.
2. **Every PR targets `main`.** Do not stack PRs on other PR branches.
3. **Never edit generated status files in a PR.** `docs/factory/current-status.json` and `docs/factory/current-status.md` are rebuilt on `main` after each merge. If your change affects status, change the generator or the input record, not the output.
4. **Merge `main` into your branch at most once,** just before asking for approval, and only if there's a conflict.
5. **Don't wait on CI.** Push, write the PR body, and stop. A later task posts the approval comment.
6. **Read big files narrowly.** Use `jq` with a key path on JSON, and `rg` limited to a folder. Never print a whole file over 50 KB.
7. **Evidence goes to Release assets** with a small committed manifest. Never commit zips, full mutation reports or other large outputs.
8. **Keep PR bodies short:** what changed, why, the work-order item, what CI must show. No logs, no long history.

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
| Control Tower (signing, decisions) | `src/lightyear_control_tower` | `control-tower*.yml` |
| Knowledge graph and business rules | `src/lightyear_knowledge_graph`, `src/lightyear_business_rules` | `verify.yml` |
| CardDemo data (VSAM and IMS to PostgreSQL) | `src/lightyear_data/carddemo` | `carddemo-data.yml` |
| CardDemo web slice (Java, UI, proof) | `factory/carddemo-web/`, `src/lightyear_data/carddemo/reference_*` | `carddemo-web.yml` |
| INTCALC and POSTTRAN release path | `tools/*intcalc*`, `tools/*posttran*`, `docs/factory/` | `posttran-phase2.yml`, `posttran-handoff-deadline.yml` |
| T-SQL procedures | `src/lightyear_data/tsql_procedures`, `data-modernization/tsql-procedures/` | `verify.yml` |
| Status page and decision packet | `tools/build_factory_current_status.py`, `tools/release_status_records.py` | `review-projections.yml` |
| Pinned upstream sources | `spec/` | — |

Tests live in `tests/test_<area>*.py` and run with `PYTHONPATH=src:.:tests python -B -m unittest <module>`, in CI only. `verify.sh` runs the full discovery suite.

## Before asking for approval

- CI on the final head is green.
- Post one comment: `Final green head: <sha>, CI run <link>.` Post a new one after any later push.
- Every merge into `main` needs Howard's approval of that exact commit.

Work orders from Howard live outside the repository and are pasted into your task. Follow the one you were given, and nothing more.
