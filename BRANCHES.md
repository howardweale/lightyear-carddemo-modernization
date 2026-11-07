# Branches and pull-request disposition plan

Review snapshot: 2026-11-07T22:53:28.341Z. Public repository: howardweale/lightyear-carddemo-modernization. Main at inspection: `695e731db0e0dd80547b409f4179a273ad931d97`.

Close-only work order: Howard selected the fourteen listed drafts for closure on 7 November, after carrying useful #472/#466 material into DILIGENCE.md. Closure status is recorded separately. No branch/tag deletion, source move, merge, history rewrite or cancellation is part of this work order. Closing a PR must retain its branch, commits, discussion, diagnostics, dated records and evidence. Reopening remains possible. Do not infer that unfinished work was delivered or that an open finding was resolved.

The GitHub open-PR inventory contained 22 PRs in the requested range. Fourteen closure candidates are below. Staleness is a scope/schedule judgment, not a claim that the commits are already on main. Before each closure, refresh the exact head/state and check new human replies or dependencies. A changed head or disposition requires review.

## Selected close-only queue

| PR | Exact reviewed head | Last updated (UTC) | Reason and retained work |
|---|---|---|---|
| [#462](https://github.com/howardweale/lightyear-carddemo-modernization/pull/462) — status: rebuild after b9729cb16795d78865e7f92d5a5e92f9bde75180 | `453f2b6561f33057d380d49af7a1b8473b151d76` | 2026-10-25T04:05:11Z | Generated status snapshot for an old main; use the current generator rather than merge historical generated outputs. |
| [#464](https://github.com/howardweale/lightyear-carddemo-modernization/pull/464) — Draft 5 November run sheet and hybrid engagement-repository plan | `af81e2cd9710541b0925ed5be008abe8921ace39` | 2026-10-30T18:29:05Z | The 5 November run sheet is obsolete under the 20 November freeze plan. Preserve the separate repository-design ideas for a later scoped proposal. |
| [#465](https://github.com/howardweale/lightyear-carddemo-modernization/pull/465) — Draft source-cited posting and account-update rules with falsifiers | `59833122a98bb223ee789bd77a84870b68c84d1c` | 2026-10-26T23:30:03Z | Unexecuted posting/account-rule backlog, outside the present authorization/native critical path. Retain the source-cited proposal for later selection. |
| [#466](https://github.com/howardweale/lightyear-carddemo-modernization/pull/466) — Draft public ten-pair T-SQL readiness harness and receipt contract | `d2cb28bbba6bd1480370c91de03f2bfd8baa7172` | 2026-10-27T03:25:55Z | Unmeasured ten-pair T-SQL demo backlog; provision and execution boundaries remain unresolved. Close the queue item without claiming the work delivered. |
| [#467](https://github.com/howardweale/lightyear-carddemo-modernization/pull/467) — Draft milestone catch-up through 30 October; preserve run results | `2c8a86bd115265e7b644afd1732305d749588c78` | 2026-10-30T18:37:08Z | Historical milestone catch-up has unfilled 5 November result slots and an outdated delivery window. Preserve every dated draft as history. |
| [#472](https://github.com/howardweale/lightyear-carddemo-modernization/pull/472) — Draft P9 public diligence: proven results and exact receipts first | `de24bf682df2c245b24279f1ae2ab88c15468889` | 2026-10-30T18:30:04Z | Older public-diligence presentation overlaps the newly authorized README/DILIGENCE work. Reuse only independently checked receipt claims; no equivalence or supersession of evidence is asserted. |
| [#473](https://github.com/howardweale/lightyear-carddemo-modernization/pull/473) — backlog lane: D1 trust page and Thursday claims wording | `9a2a0dc439b2cb091cd9284ebccfb166f179e80f` | 2026-10-30T17:58:04Z | Claims wording is tied to the former 5 November run. Preserve approved wording and empty result slots; any current run claims need a fresh proposal. |
| [#474](https://github.com/howardweale/lightyear-carddemo-modernization/pull/474) — Draft M5 keep-or-fix and M6 program pages with milestone links | `69ba5c0fb67c5870ae57cd1a9ce44f7ac2472078` | 2026-10-30T19:04:16Z | Old milestone/program-page catch-up remains backlog. Preserve KF-005/KF-006 and native questions; closure does not close those findings. |
| [#475](https://github.com/howardweale/lightyear-carddemo-modernization/pull/475) — backlog lane: KF-005 fault-injection design only | `e92a2f1512f9f88ca1fe8035de9a4c44f2957a8c` | 2026-10-30T18:13:41Z | Deferred KF-005 fault-injection design, not an implemented fix. Preserve the design and open finding for a later explicit decision. |
| [#476](https://github.com/howardweale/lightyear-carddemo-modernization/pull/476) — Draft M2.1: clearly refuse ambiguous INTCALC account xrefs | `258bfc58297925aa370c22732e9e2d7580b7caf2` | 2026-10-30T18:51:13Z | INTCALC ambiguous-xref interim behavior remains outside Track B's current critical path and has an unresolved native question. Retain code/tests and KF-006. |
| [#477](https://github.com/howardweale/lightyear-carddemo-modernization/pull/477) — Draft M2.4: twin exit-12 convention pending z/OS confirmation | `0dee762ea14133be7d9ff0a4c899340926cdf083` | 2026-10-30T19:41:10Z | INTCALC exit-12 convention remains unverified on z/OS. Preserve the native-status question and its evidence; closure is not validation. |
| [#478](https://github.com/howardweale/lightyear-carddemo-modernization/pull/478) — Draft M2.5: bind INTCALC timestamp policy to exact comparison | `509f29e261009ace8d1a4976de17f42ce6198510` | 2026-10-30T19:04:12Z | INTCALC timestamp-policy backlog remains unqualified. Preserve the exact-comparison policy and discrepancy for later review. |
| [#502](https://github.com/howardweale/lightyear-carddemo-modernization/pull/502) — Retry complete pinned snapshot index refresh after transient failures | `c2695d8303bb643ae5ae639e509aeeea21a17c3f` | 2026-11-04T16:39:01Z | Blocked protected-Containerfile repair; no gate exception or merge authorized. Preserve its diagnostics and exact head; closing avoids an unmergeable repair queue item. |
| [#503](https://github.com/howardweale/lightyear-carddemo-modernization/pull/503) — Retry snapshot transport failure around the unchanged twin build | `d09e7102fbac06741e0727d9b0ff2a2a76a44eb4` | 2026-11-04T17:18:20Z | Older alternative transport-retry repair remains unqualified and unmerged. Preserve its diagnostics; any future adoption needs a fresh reviewed proposal. |

## Keep open or explicitly exclude

| PR | Disposition |
|---|---|
| [#455](https://github.com/howardweale/lightyear-carddemo-modernization/pull/455) | KEEP OPEN: active Track B integration overlay with unfinished F2/P5/native dependencies. Age is not grounds to discard the critical-path PR. |
| [#468](https://github.com/howardweale/lightyear-carddemo-modernization/pull/468) | EXCLUDED: never close or delete under this plan; retained POSTTRAN comparison PR, never merge. |
| [#471](https://github.com/howardweale/lightyear-carddemo-modernization/pull/471) | EXCLUDED: never close or delete under this plan; retained scratch PR, never merge. |
| [#483](https://github.com/howardweale/lightyear-carddemo-modernization/pull/483) | HOLD: archival-retrievability policy can still matter to qualification; no verified replacement established. |
| [#485](https://github.com/howardweale/lightyear-carddemo-modernization/pull/485) | HOLD: explicitly deferred until after the qualified run and GO/release inventory reconciliation; retain that disposition. |
| [#487](https://github.com/howardweale/lightyear-carddemo-modernization/pull/487) | HOLD: approved design, implementation explicitly deferred to post-run; retain the exact design and separate decision boundary. |
| [#488](https://github.com/howardweale/lightyear-carddemo-modernization/pull/488) | HOLD: canonical public-key documentation; no verified replacement or safe retirement established. No trust activation inferred. |
| [#489](https://github.com/howardweale/lightyear-carddemo-modernization/pull/489) | HOLD: synthetic-fixture labelling/public-proof refusal work; no verified equivalent on main established. |

## Boundaries

- Never close #468 or #471 under this cleanup. Never merge either PR.
- Keep #455 open until its remaining integration has an explicit replacement/disposition; preserve all merged extractions.
- #522/#523/#528 remain outside this list, held intact and unmerged. D1 has no renewal, activation or compatibility-repair authority.
- No remote branch, local branch, tag, dated file, retained receipt or evidence deletion is proposed.
- Drafts outside #455–#503 are outside this requested closure review. This document is not a complete branch ancestry/deletion audit.
- Close-only scope is distinct from merge approval. Current merge authority for #527 and completed #525 is unaffected.
