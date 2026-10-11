# Factory review follow-up for PRs #311–317 — 2026-10-11

## Howard decision update — 2026-10-11

The [dated decision milestone](howard-decisions-2026-10-11-milestone.md) supersedes the compiler-refusal blocker and unaccepted-EOF conclusions below: listed compiler refusals are excluded, and Howard accepted the two source-bound EOF false edges. REWRITE-109 and the unreachable final-account update are legacy defects to preserve by default. Raw campaign records remain historical. The [20-mutant independent review](equivalence-review-sample-2026-10-11.md) is pending; scenario-threshold/2 is not approved.


The compiled public host campaign covers every inventoried business outcome. Declared I/O faults improve the operational coverage; one source-bound EOF edge in each program remains unobserved and unaccepted.

| Program | Business outcomes | I/O before faults | I/O after faults | Combined after faults | Declared faults matched |
|---|---:|---:|---:|---:|---:|
| INTCALC | 8/8 | 56/86 | 85/86 | 93/94 | 24/24 |
| POSTTRAN | 24/24 | 49/86 | 85/86 | 109/110 | 29/29 |

The systematic campaign attempts compilation at every generated site and executes the compiled mutants; failure and divergent kills are distinct. Compiler refusals remain in both denominators. Only individually listed argued equivalents are excluded from the second denominator.

| Program | Sites | Failure kills | Divergent kills | Argued equivalents | Survivors | Compiler refusals | Raw kills | Kills after listed exclusions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| INTCALC | 426 | 162 | 146 | 113 | 0 | 5 | 308/426 (72.3%) | 308/313 (98.4%) |
| POSTTRAN | 489 | 194 | 175 | 111 | 3 | 6 | 369/489 (75.5%) | 369/378 (97.6%) |

| Program | Additional individually argued survivors | Remaining unexplained | Kill rate after both listed argument sets |
|---|---:|---:|---:|
| INTCALC | 0 | 0 | 308/313 (98.4%) |
| POSTTRAN | 3 | 0 | 369/375 (98.4%) |

The [three post-campaign arguments](post-campaign-equivalence-review311.json) bind each actual surviving site to its source and, for the receiving-scale case, the verified runtime bytes. Two are unconsumed validation-description stores; the third truncates an unused fractional byte on every account-ID consumer. These are listed arguments for Howard’s review, not additional measured kills or accepted policy exceptions.


Raw campaign survival is retained above. The separate post-campaign source/runtime review can list a survivor as argued equivalent without rewriting that observation. Unexplained survivors and compiler refusals still block adequacy, even if a numerical kill threshold is met. [Every mutant and its disposition](systematic-review311-summary.json), [INTCALC detail](systematic-intcalc-review311.json), [POSTTRAN detail](systematic-posttran-review311.json), and [survivor review and compiler refusals](systematic-survivors-review311.md) preserve the actual results. No unexplained survivor is relabeled equivalent to improve a percentage.

The revised POSTTRAN preregistration awaits a new decision; the old budget approval does not cover it.

- Plan: `97b105a5f9e1c26b378be927b7fc74e947a051a6ef0c49f03b5ac4ddcfa1d95e` ([full proposal](posttran-second-opinion/revised-plan.json)).
- Installed client provenance: Codex 0.160.0, SHA-256 `4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01`; actual bytes checked.
- Proposed broker: `40697064deeea86bfd85ff8d924049f0d1624fe42040743a07832e34b2d7e5c0`; explicitly supplied Responses API transport, **not CLI dispatch**.
- Phase 1 proposal: three calls/attempts/compilations, 750,000 input tokens, 192,000 output tokens, 64,000 maximum output tokens per call including reasoning, two hours, $36 API-equivalent with conservative reservations above dated verified Standard rates.
- Phase 2: two calls and $24 API-equivalent, still blocked on adjudication and separate approval.

Fresh approval must cover the transport change as well as the client provenance, tokens and budget. The broker sends `max_output_tokens=64000`, disables truncation, verifies exact public packet/client bytes and approval, and rejects incomplete/missing-usage/over-cap responses. Official [reasoning documentation](https://developers.openai.com/api/docs/guides/reasoning) states this cap includes reasoning and non-visible output tokens. Tests use a fake transport only.

Official model, pricing and Responses contracts were checked 2026-10-11. Standard input/cached/cache-write/output prices are $10/$1/$12.50/$50 per million. The exact-input counting endpoint refuses more than 250,000 tokens before generation, below the 272,000 long-context threshold; service_tier default selects Standard. Maximum token-cost estimates are $18.975/$12.65 for phases 1/2; conservative reservations stay $33.15/$22.10 beneath the proposed $36/$24 caps. No tools or regional/higher-tier transport is proposed. The live transport is unexercised; all tests use fakes and fresh approval remains required. The broker atomically reserves the next attempt and full allowance in a fixed plan-bound ledger before any callback; failures consume reservations without refund. Live HTTP timeout enforcement remains the supplied transport contract; none is connected here. The verified Codex binary is provenance only; no claim is made that it executes or enforces the Responses cap. Prior public evidence has 89,246 aggregate output tokens over 10 calls (mean 8,924.6), with neither a reasoning split nor per-call tail measurement. 64,000 is proposed headroom, not a measured percentile. Zero model calls, model-output compilations or candidates were produced.

## Source classification and I/O limits

`decision-classification.json` binds all 102 decisions/204 outcomes to reviewed source hashes and data flow. Missing tariff selects business fallback; missing card/account selects business rejection. File traversal, EOF and operational failure paths are I/O handling. Source changes refuse reuse of classification and equivalence arguments.

Prospective lexical-overlap corrections are in `docs/oct10-factory-foundations-milestone.md` and `docs/business-rules/milestone-2026-10-10.md`; the instrumentation milestone already labels 16/47 correctly. No other literal 16/47 coverage claim was found in docs, catalogues or views. Signed historical receipts remain unchanged.

[INTCALC fault mappings](fault-intcalc-review311.json) and [POSTTRAN mappings](fault-posttran-review311.json) bind each declared status/display/RC to observed outcomes. Missing/permission OPEN, READ, WRITE, REWRITE, CLOSE and premature EOF are derived engineering seams. They do not recreate RACF, VSAM, devices or z/OS allocation; the limits register marks that equivalence unknown. Most abend paths return RC 12. POSTTRAN account REWRITE reason 109 actually returns RC 0: the original failure-propagation gap is visible and unchanged.

The first EOF IF false edge is source-unreachable under the enclosing TEST BEFORE loop, as detailed in [the exact source arguments](io-gap-arguments.json). It remains in the coverage denominator; Howard has not accepted an exception. INTCALC final-account update inside that unreachable ELSE is not silently repaired.

## Mutation evidence and retained witnesses

INTCALC observed source head `3283265d71e268b3dc66b09fb2808e72a18b19ac`, [run](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38154818763), receipt seal `8c26a427392e7a43eade0f4e5e53652fc6709ee12cd2a54bf3e384d7b55abf31`.

POSTTRAN observed source head `3283265d71e268b3dc66b09fb2808e72a18b19ac`, [run](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38154818763), receipt seal `18efe77ba378eb2dd38aebb10ec92751bf9364d861f6b5e270fa6d5ba1615cd3`.

Every killed mutant retains its exact normal scenario or scenario-plus-fault witness. Up to three declared fault challenges target the surviving mutant’s operation/callee or diagnostic path. Incompatible derived seams are recorded as unavailable, never counted as kills. Raw outputs, RC, stdout (excluding probes) and actual abend stderr parameters are compared. The CEE3ABD shim records code/timing and stops; it does not simulate z/OS timing.

False generator sites involving numeric paragraph labels and COMPUTE assignment equals signs were corrected; prior results were preserved. Whole multiline predicates are negated together. The old 8/8 hand-picked result is regression-only and cannot populate the systematic adequacy denominator. Earlier corrected 427/490-site results were 292/427 and 337/490 raw; neither was presented as 90%.

Narrow listed arguments identify dead/overwritten stores, unused fields or source-bound control-flow invariants. Binary arguments require a recorded compiler LENGTH probe; storage arguments additionally require the exact measured default/overlay probe. Otherwise the case stays unresolved. These are pinned host arguments for review, never blanket equivalence, operator acceptance or z/OS proof.

## Reconciliation, policy and human review

ASCII and opt-in physical cp037 key modes matched **54/54** public/generated cases (**no regression from cp037 key mode**, all decimal-key cases; this does not establish general EBCDIC order) at `3283265d71e268b3dc66b09fb2808e72a18b19ac` ([receipt](cp037-twin-review311-reconciliation.json)). Logical record bytes stay unchanged. Decimal-only production restrictions remain; no general alphanumeric z/OS key-order claim follows.

The expanded **46**-case [generated receipt](generated-review311-classification.json) separates source-specific missing disclosure/account/xref expected-failure agreement from duplicate indexed-key adapter refusal before execution. The POSTTRAN duplicate-ID invariant remains unresolved. No customer data or handwritten POSTTRAN answer key was used.

The unsigned scenario-threshold/2 proposal requires 100% business outcomes; I/O outcomes covered or individually accepted by Howard; at least 90% systematic kills over at least 50 eligible mutants with only listed equivalents excluded; and two distinct values per compared output field. Compiler refusals and unexplained survivors remain separate blockers. It is not approved.

The [POSTTRAN human review HTML](posttran-human-review.html) is a standalone file: download and open it locally, enter your name and each decision/reason, download the unsigned JSON, and return it in chat. No GitHub Pages deployment or automatic operator signature is claimed.

Focused host validation passed 25 tests plus lint. Final-head CI must complete green before merge, followed by Howard’s exact-commit approval. Public compiled campaign receipts bind their observed algorithm head; broker and documentation updates do not alter the measured mutation algorithms or rewrite their receipts. No B06 native work, engineering hold, customer data, machine configuration or private key was changed.
