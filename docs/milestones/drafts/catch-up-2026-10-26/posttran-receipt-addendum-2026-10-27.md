# POSTTRAN receipt addendum — draft, 27 October 2026

This adds evidence received after the [26 October reconciliation](reconciliation-2026-10-26.md). It leaves that historical cutoff, [proposed MS-116](MS-116/MS-116.md), the proposed numbering, the canonical catalog, status pages and documentation manifests unchanged. It is not a merge or release authorization. Merge remains held until after the Friday run and requires Howard's approval of the exact final green commit.

## Reconciliation entry

| Topic | Earlier draft position | New retained evidence | Bounded disposition |
| --- | --- | --- | --- |
| POSTTRAN attempt 1 | Key change and packaged-installation handoff recorded; execution evidence separate | [Receipt on #436](https://github.com/howardweale/lightyear-carddemo-modernization/issues/436#issuecomment-6446592776), [run 40532820863](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/40532820863), execution-only [#468](https://github.com/howardweale/lightyear-carddemo-modernization/pull/468) at 227560cb3da580cdaa9c5a8c0dcfcb2f81e13a07 | Comparison complete; provisional oracle, no release authorization or z/OS confirmation; original artifacts retained |

The receipt records pull_request event, attempt 1, reserve and compare success, and compare completion at 2026-10-27 15:39 UTC. It was posted at 15:49 UTC. Reservation verification bound the plan, exact head, run ID, attempt 1 and consumed_before_execution=true. The consumed tag and execution base remain retained; #468 never merges. [Receipt](https://github.com/howardweale/lightyear-carddemo-modernization/issues/436#issuecomment-6446592776)

The results report complete=true. They have no top-level scenario_count field; the 29 enumerated scenarios match the sealed plan. Outcomes are 29 equivalent, 0 divergent and 0 indeterminate. An empty top-level unresolved list does not remove the nested promotion blocker: posttran-runtime-rewrite-109 is repeated 58 times across candidate/twin outputs. release_authorized=false, zos_confirmation=false, oracle_status=provisional, model_calls=0 and candidate_edited=false. [Receipt](https://github.com/howardweale/lightyear-carddemo-modernization/issues/436#issuecomment-6446592776)

Independent digest checks matched the results ZIP SHA-256 2e93bacd2141cafb9e9168a589f35526ea001f064d2fc66cedddc1ef6594192b and reservation ZIP SHA-256 29747ad8b0a51ba4175cea14840a4613434250c343b941abc8b37daf3aad7f02. The receipt records 232 output-file hash checks and 29 twin-receipt hash checks. Frozen-judge is recorded as not applied, not passed. These are the retained comparison's observations, not broader application or production-equivalence claims. [Receipt](https://github.com/howardweale/lightyear-carddemo-modernization/issues/436#issuecomment-6446592776)

## New wording for Friday's claim review only

| Claim ID | Proposed customer sentence | Exact source | Wording decision |
| --- | --- | --- | --- |
| C116A | The retained POSTTRAN comparison reports 29 equivalent scenarios, with provisional oracle status and a nested unresolved promotion blocker; it does not authorize release or confirm z/OS behavior. | [Receipt comment 6446592776](https://github.com/howardweale/lightyear-carddemo-modernization/issues/436#issuecomment-6446592776) | Pending Friday 30 October batch; customer publication=false |

This single proposed sentence must be reviewed with its limitations intact. No wording approval is inferred from successful CI or from approval to publish this draft. The original [Friday claims register](friday-claims.md) remains historical; C116A supplements its pending review set.

## Preserved milestone and run boundaries

- [MS94 disposition](proposed-ms94-disposition.json) remains closed by Howard's decision to move on, with no completion claim.
- [MS-122](MS-122/MS-122.md) remains the placeholder for the first judged COPAU factory run. This POSTTRAN result does not populate its status or result.
- POSTTRAN-bound paths remain frozen through 2026-10-29 14:46 UTC. No rerun, cancellation, merge of #468, deletion of its base ref/tag, new signature or additional attempt follows from this addendum.
- This file is draft documentation only; it changes no original receipt, source, policy, workflow, required gate or canonical milestone state.
