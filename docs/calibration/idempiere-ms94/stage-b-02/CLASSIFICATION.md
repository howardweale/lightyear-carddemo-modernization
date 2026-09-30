**Recorded cohort: 2/10 (20%); 95% Wilson interval 5.7%–51.0%. Both passes and Category A accepted by Howard; Category B retains a public-contract caveat.**

# Stage B 02: post-run classification

All 11 failures and both passes are indexed in [classification.json](classification.json),
including candidate/source hashes, gate hashes, stack locations, native run paths,
field names, empty diagnostic exports and costs. This is a post-run assessment,
not a replacement signed verdict. The frozen report and every outcome remain intact.
No candidate was repaired, rerun or supplied this analysis. All 13 archived
publications previously replayed successfully with the unchanged frozen verifier.
Replay establishes reproducibility, not that the acceptance policy is correct.
Classification describes the first observed blocking failure. Some crashed
candidates also contain the ARI override; an early abort masks later checks, so
fixing the crash alone is not a prediction of a passing result.

## Every failure

Line numbers below refer to each trial's assembled `LightyearOperationsTest.java`.
Category A and B assessments below apply individually to every row bearing that category.

| Trial | Recorded class | Failure stage and exception or divergent field | Root cause | Was the judge right? | Would a permitted diagnostic point to the fix? |
|---|---|---|---|---|---|
| pilot-01 | execution-failure | Credit/reversal allocation: `IllegalStateException: Missing accounting`; `accounting:90`, caller `operations:321` | A: invented nonempty-facts invariant | Yes for execution failure: both lanes abort | Current export empty; public smoke exception/stage would expose own assertion |
| pilot-02 | execution-failure | Credit/reversal allocation: `IllegalStateException: Missing accounting`; `accounting:77`, caller `lambda$16:474` | A | Yes for execution failure | Same as A |
| pilot-03 | business-failure | Invoice type override at line 206; `c_invoice.c_doctypetarget_id` and `c_doctype_id`, with propagated differences | B: unclear contract plus nondeterministic API selection | Mechanical difference correct; rejection policy unresolved | Current export empty; field + stage localizes, cannot settle contract |
| cohort-01 | execution-failure | Credit/reversal allocation: `AssertionError: Missing accounting`; `readAccounting:72`, caller `businessJourney:314` | A | Yes for execution failure | Same as A |
| cohort-02 | execution-failure | Credit/reversal allocation: `AssertionFailedError: Posted document must have accounting`; `readAccounting:65`, caller line 430 | A | Yes for execution failure | Same as A |
| cohort-03 | business-failure | Invoice type override at line 366; same eight field identities as B | B | Mechanical difference correct; rejection policy unresolved | Same as B |
| cohort-04 | execution-failure | Credit/reversal allocation: `AssertionFailedError: Posting must have accounting rows`; `post:67`, caller `lambda$7:441` | A | Yes for execution failure | Same as A |
| cohort-07 | business-failure | Invoice type override at line 351; same eight field identities as B | B | Mechanical difference correct; rejection policy unresolved | Same as B |
| cohort-08 | execution-failure | Credit/reversal allocation: `IllegalStateException: Accounting rows missing`; `checkAccounting:324`, caller `runJourney:272` | A | Yes for execution failure | Same as A |
| cohort-09 | business-failure | Invoice type override at line 367 using `DOCBASETYPE_ARInvoice`; same eight field identities as B | B | Mechanical difference correct; rejection policy unresolved | Same as B |
| cohort-10 | business-failure | Invoice type override at line 357; same eight field identities as B | B | Mechanical difference correct; rejection policy unresolved | Same as B |

### A — six candidate crashes (four cohort, two pilots)

Primary category: **plain business-logic error**, specifically a candidate-added
assertion that every posted allocation must have at least one accounting row.
Secondary cause: misunderstanding of the iDempiere API's reversal semantics.
The failure is after credit reversal, not the original payment allocation.
It is not established as a support-library, trace-formatting or timing defect.

Pinned application commit `731515dcdd5278b843db33b9d3109d155b881951`,
`org.adempiere.base/src/org/compiere/acct/Doc_AllocationHdr.java:197–214`,
explicitly returns an empty facts list for the two-line invoice/reversal allocation.
The after-state observations include a completed, posted allocation with zero facts
in both lanes. Both accepted candidates also exhibit that legitimate zero-fact
allocation, without rejecting it. The public shapes require completed allocations
and posted, balanced related accounting; they do not require nonempty facts for
every allocation. Credit and reversal document accounting is checked separately.
Pilot-02's failed transaction does not leave that reversal allocation in the final
capture; its diagnosis relies on its exception/stack, candidate transaction body
and pinned application behavior, rather than a claim that its missing final row
was directly observed. The per-trial index preserves the actual captured counts.

The native gate correctly records the candidate aborts as execution failures;
it does not claim completion of the unfinished journey. There is no evidence here
that a valid, completed candidate was falsely rejected in these six cases.
The recorded schema flag `IsPostIfClearingEqual` is Y: the separate clearing-account
suppression branch is **not** the explanation for these observations.

Current feedback exported no diagnostic in all six cases. A public smoke run could
return the candidate's own exception and stack/stage against a separate public
sample database, making this assumption discoverable without expected answers.
That is a repair opportunity, not evidence that the builder would repair it.

### B — five completed executions rejected on document-type differences

Primary category: **unclear public contract**; secondary technical mechanism:
**nondeterministic use of the iDempiere API**. Each candidate constructs the invoice
from the order, then replaces the inherited target type with the generic ARI
string setter. Both lanes finish successfully, public structure passes, both
transaction observers pass, and there are no unresolved trace differences.

The pinned `MInvoice.java:484–497` constructor resolves the order document type's
invoice type. The string setter at lines 804–822 instead orders eligible types by
`IsDefault DESC, AD_Org_ID DESC`, without a tie-breaker. The captured fixture has
two active ARI types tied on both keys: “AR Invoice” and “AR Invoice Indirect”.
The lanes select different types. Both passes retain the constructor's selection.

Each of these five cases has 16 unresolved row differences across eight fields:

| Field | Differences per trial |
|---|---:|
| `c_invoice.c_doctype_id` | 1 |
| `c_invoice.c_doctypetarget_id` | 1 |
| `c_invoice.documentno` | 1 |
| `ad_sequence.currentnext` | 2 |
| `ad_wf_activity.textmsg` | 2 |
| `ad_wf_eventaudit.textmsg` | 2 |
| `ad_wf_process.textmsg` | 1 |
| `fact_acct.description` | 6 |

These are consistent with document-type/numbering propagation; the workflow text
also contains a decimal-format difference. No monetary-result field is in this
unresolved set. This does not independently prove all possible business semantics.

**Judge assessment:** the paired comparator correctly reports unequal fields.
However, the builder-visible prompt/shapes do not explicitly select an invoice
type, require retention of the order-derived type, or explain whether these
alternative types are forbidden. Structural validity is insufficient to declare
either alternative semantically correct. Howard subsequently approved deterministic
retention as a rule **for the next run**, without identifying an existing frozen
clause. These five remain recorded business failures with a **public-contract
gap**, not five established model business-logic mistakes. His prospective approval
does not establish that the historical policy was fair or relabel old outcomes.

All five current diagnostic exports are empty. A closed diagnostic containing
only `invoice` plus `c_doctypetarget_id`/`c_doctype_id` would identify the location
without revealing values. It cannot tell the builder which policy the public
contract meant. Revealing field names is not a substitute for resolving ambiguity.

## Human review and next-run decision

[REVIEW.md](REVIEW.md) contains separate pass reviews and the contract adjudication
request. Howard Weale accepted cohort-05 and cohort-06 and confirmed all six
Category A execution failures on 29 September 2026. He clarified that Category B
approves a prospective retention rule. The original classification
JSON remains unchanged as the pre-review evidence index; [human-review.json](human-review.json)
records the subsequent human decisions against its exact hash.
The signed report says `cohort_void=false`, which remains unchanged. If human
review establishes a wrong judge, publish a separate adjudication invalidating
the measurement's interpretation and requalify the equipment before measuring
again. Never replace the old failure with a pass or silently recompute 7/10.

Six of eleven failures are runtime crashes (54.5%; the cohort alone is tied at
four crashes/four document-type cases). This initially favored a public smoke-run
tool. Howard's subsequent prospective contract approval gives the contract gap
precedence: the **single next change is the public order-derived invoice-type
retention rule and its matching structural acceptance rule**. See
[the exact requirement and qualification boundary](NEXT-CONTRACT.md).
Smoke-run work and diagnostic widening are deferred. Integrate and requalify the
changed acceptance boundary before measuring; these steps have not yet been run.

The next measurement will use **20 fresh cohort trials**, with any pilots excluded
and declared separately. The existing ten are not extended or pooled into it.
Freeze and publicly timestamp the exact intervention, plan, stopping rules and
budgets before the first new candidate call. Preserve the five-call/three-compile
per-trial limits; explicitly declare the aggregate budget for the larger cohort
and any smoke executions. No new campaign is authorized by this review document.
Do not stop after ten based on interim performance. Compute the same 95% Wilson
interval; at an illustrative 4/20 it would be approximately 8.1%–41.6%, not a
prediction of the next outcome. Runtime will depend on repairs and smoke calls.
