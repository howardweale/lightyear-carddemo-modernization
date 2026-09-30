**Recorded Stage B 03: 12/20 (60%); 95% Wilson interval 38.7%–78.1%. Post-run assessment complete; operator adjudication pending.**

# Stage B 03 post-run classification and pass review

All ten failures (eight cohort, two pilots) and thirteen passes (twelve cohort,
one pilot) are assessed in [classification.json](classification.json). This is
an agent source/evidence assessment, not a human signature or replacement
verdict. Howard approved operator review and subsequently said “classification
may resume” after the support-origin stop. That authorized this evidence-only
investigation; adjudication of the completed packet remains pending.

No candidate was rerun, repaired or given this analysis. No model call or native
execution was made. Every source/gate hash was checked against the prior intake;
the unchanged frozen snapshot guard passed before and after analysis. Earlier
publication replay remains the integrity check; it was not repeated as a new
candidate execution. All original outcomes, costs and the nonvoid signed report
remain intact. Exception messages, captured rows, monetary values and candidate
source are not republished.

## Every failure

All ten fail at the same point in both database lanes, with failed partial
traces, exit 1 and empty existing diagnostic exports. Line numbers below refer
to each assembled `LightyearOperationsTest.java`; source, log, execution, trace
and gate hashes and paths are recorded separately for each trial in the JSON.

| Trial | Category / origin | Exception and first candidate frame | Assertion / journey caller | Judge assessment | B04 localization prediction |
|---|---|---|---|---|---|
| pilot-01 | A / candidate | `IllegalStateException`; `require:34` | 89 / 324 | Yes for recorded execution-failure; candidate-owned extra invariant | uncertain-generic-helper |
| pilot-03 | C / support | `IllegalStateException`; `post:72` | support 540 / 199 | Yes for recorded execution-failure; validity review required | suppressed-support-origin |
| cohort-01 | A / candidate | `AssertionFailedError`; `accounting:71` | 71 / 432 | Yes for recorded execution-failure; candidate-owned extra invariant | direct |
| cohort-07 | A / candidate | `AssertionFailedError`; `accounting:83` | 83 / 336 | Yes for recorded execution-failure; candidate-owned extra invariant | direct |
| cohort-08 | A / candidate | `IllegalStateException`; `require:30` | 71 / 452 | Yes for recorded execution-failure; candidate-owned extra invariant | uncertain-generic-helper |
| cohort-12 | A / candidate | `IllegalStateException`; `require:32` | 91 / 318 | Yes for recorded execution-failure; candidate-owned extra invariant | uncertain-generic-helper |
| cohort-13 | A / candidate | `AssertionFailedError`; `readBalancedAccounting:71` | 71 / 453 | Yes for recorded execution-failure; candidate-owned extra invariant | direct |
| cohort-14 | A / candidate | `AssertionFailedError`; `post:55` | 55 / 283 | Yes for recorded execution-failure; candidate-owned extra invariant | direct |
| cohort-18 | A / candidate | `IllegalStateException`; `require:33` | 68 / 316 | Yes for recorded execution-failure; candidate-owned extra invariant | uncertain-generic-helper |
| cohort-19 | A / candidate | `IllegalStateException`; `require:30` | 72 / 442 | Yes for recorded execution-failure; candidate-owned extra invariant | uncertain-generic-helper |

### Category A: all eight cohort failures and pilot-01

The first blocking defect is the same as B02 Category A: a candidate-added
assertion requires nonempty accounting rows for the credit/reversal allocation.
The stack and source caller identify the allocation reached after credit
reversal, not the original payment allocation. The pinned application's
`Doc_AllocationHdr.java:197–214` deliberately returns an empty facts list for
the invoice/reversal pair. The pin is
`731515dcdd5278b843db33b9d3109d155b881951`; source-file hashes are in the index.

Root-cause category is **plain business-logic error**, with an API-semantics
misunderstanding. These are candidate-owned assertions, not support throws:
`JourneySupport.transaction` lower in the stack only propagates the exception.
The gate correctly records an aborted journey. No valid completed alternative
was rejected by comparison in these cases.

The early abort masks later reversal-cancellation/final checks and the
recovery/retry and lock-interleaving paths; none of these partial traces has
recovery or concurrency fields. No distinct later defect is established here.
The order-derived invoice constructor is present with no later invoice target
override, but that source observation does not prove the unfinished journey
would pass after repairing the first crash.

### Category C: pilot-03, support wrapper around an application rejection

The original stop finding remains valid: `JourneySupport.postOnce:540` throws
in both lanes, called by candidate `post:72`, from opening inventory at
`businessJourney:199`. The preserved logs show a native inventory-costing error
before the posting-lock rejection, and final captures retain a posting-error
state. This is more specific than the initial lock/timing hypothesis.

The pinned `Doc_Inventory.java:319–334` rejects missing costs for a stocked item.
`Doc.java:591–608` admits only the declared unposted/deferred states when force
and repost are disabled. `DocManager.java:406–428` invokes that check and
propagates rejection. The public support wrapper at
`factory/idempiere/qualification-ms94-v3/public/JourneySupport.java:45` throws
on the returned error. It has not independently invented the rejection.

The candidate makes an extra explicit inventory-posting call at that point;
successful candidates complete opening inventory and continue. The public
journey says: “Post invoice, payment and allocations using the application APIs
without reposting already-posted documents.” It does not require this extra
opening-inventory post. The evidence therefore supports **misuse of the
iDempiere posting sequence**, with `thrown_by: support` retained as the literal
origin. No timing race or independently incorrect support implementation is
demonstrated. This is not a claim that every equipment defect has been excluded.

**Agent judge assessment: yes**, the run aborted on this additional call. The
support-origin trigger still requires operator measurement-validity adjudication
under the supplied spec; it does not automatically void or excuse the trial.
The excluded pilot is not counted in the cohort. B04's proposed rule would
suppress this diagnostic and route it to `halted-equipment-suspect`, even though
the underlying evidence points to candidate API sequencing. All later journey
checks are masked by the opening-inventory abort.

## Five required answers

1. **Two elapsed-time groups, two causes? No.** Both early cohort trials
   (01/07/08/18/19) and late trials (12/13/14) have the same Category A defect.
   The preserved evidence does not establish why their runtimes differ.
2. **How many cohort Category A? Eight of eight.** Pilot-01 is the ninth Category
   A failure; pilot-03 is Category C.
3. **Any support/equipment throw? Yes: pilot-03.** The mandatory stop was recorded
   before further work; Howard then authorized classification to resume. The
   wrapper origin is confirmed, while evidence favors candidate misuse as the
   underlying cause. Validity adjudication remains pending; no verdict changed.
4. **Did the public contract explicitly rule out the assumption? No.** It says
   “One payment settles the invoice; allocation headers are completed and all
   related accounting is posted and balanced.” It also separately requires
   credit/reversal accounting cancellation. Neither clause promises nonempty
   facts for every allocation, nor explicitly teaches the zero-fact reversal
   case. There is no builder-visible statement directly correcting that
   assumption. No new clarification was added.
5. **How many would the proposed diagnostic localize? Four of eight directly.**
   Cohort-01/07/13/14 expose their accounting assertion as the first candidate
   frame. Cohort-08/12/18/19 first expose a generic `require` helper; the caller
   that identifies the accounting assertion is not part of the proposed single
   frame. Stage information may help, but those four remain uncertain and are
   not included in the primary localization prediction. This is a preregistration
   input, not a prediction of repaired passes. Pilot-01 has the same helper
   limitation; pilot-03 receives no runtime diagnostic under the proposal.

Partial traces are Java `Properties` XML. Their entry order is not chronological:
the last entry is not necessarily the last executed stage. They also have no
separate allocation checkpoint. B04 must qualify a declared mapping over public
field presence and omit ambiguous stages; it must not label the last XML entry
as the active stage. A generic assertion/helper may likewise have no uniquely
resolvable API call on its throwing line. These are implementation/admission
issues for the supplied diagnostic spec, not changes made to the experiment.

## Every pass

The following dispositions are agent assessments for operator review. They do
not replace human adjudication. All use native models/workflow actions, one
aggregate order-linked invoice, the constructor's order-derived invoice type,
guarded explicit posting, explicit rollback/retry and primary-key lock paths.
No direct SQL business writes, posting outside `JourneySupport.postOnce`,
hardcoded generated invoice-type identifier or suppression of unexpected
exceptions was found in the reviewed paths. Existing gates independently pass
structure, both observers and all row/trace comparisons.

| Pass | Agent disposition | Invoice constructor line | Review note |
|---|---|---:|---|
| pilot-02 | accepted-with-note | 359 | Explicitly asserts both invoice type fields against the order relationship. Default-bank selection remains fixture-dependent. |
| cohort-02 | accepted-with-note | 370 | Uses the order constructor without overriding the derived invoice type. Default-bank selection remains fixture-dependent. |
| cohort-03 | accepted-with-note | 230 | Main-thread first lock and worker second lock; waited flag and Future readback checked. Default-bank selection remains fixture-dependent. |
| cohort-04 | accepted-with-note | 367 | Repeated-key lookup verifies singleton identity before taking the row. Default-bank selection remains fixture-dependent. |
| cohort-05 | accepted-with-note | 240 | Read-only PreparedStatement accounting scan; non-locking firstOnly rejects duplicate caller keys. Default-bank selection remains fixture-dependent. |
| cohort-06 | accepted-with-note | 371 | Rollback failures are attached as suppressed exceptions; primary failure is rethrown. Default-bank selection remains fixture-dependent. |
| cohort-09 | accepted-with-note | 352 | Initial credit-limit input is set on the created customer before the two lock transactions. Default-bank selection remains fixture-dependent. |
| cohort-10 | accepted-with-note | 358 | Two shipments are created by iterating declared quantities; both use the same order line. Default-bank selection remains fixture-dependent. |
| cohort-11 | accepted-with-note | 351 | Broad recovery catch suppresses only the exact injected exception object; others rethrow. Default-bank selection remains fixture-dependent. |
| cohort-15 | accepted-with-note | 222 | Invoice constructor derives type; both completed fields are checked against that derived value. Default-bank selection remains fixture-dependent. |
| cohort-16 | accepted-with-note | 182 | Invoice type checked against order relationship; retry and lock lookups enforce cardinality. Default-bank selection remains fixture-dependent. |
| cohort-17 | accepted-with-note | 228 | Shipments iterated from public quantities; repeated lookup requires the existing caller-key row. Default-bank selection remains fixture-dependent. |
| cohort-20 | accepted-with-note | 365 | Second connection allocated before announcing lock attempt; elapsed wait and Future results observed. Default-bank selection remains fixture-dependent. |

All thirteen are **accepted-with-note**; there are no demonstrated current-fixture
false passes in this review. The common notes are material scope limits:

- Fixed dates, logical keys, amounts, quantities, text, and dictionary references
  come from builder-visible scenario inputs/API. These are fixture-specific
  inputs, not evidence of deriving expected business answers from private data.
  Totals, payment amount, flags, generated IDs and accounting are read back.
- Each default-bank query uses `DB.getSQLValueEx` without uniqueness checking or
  an ordering rule. The pinned method returns the first row (`DB.java:1098–1122`).
  Both preserved lanes have a unique matching default for each reviewed pass.
  A different fixture with multiple defaults could silently choose another
  account. No new fixture was run to test that possibility.
- Template locations use the first active location returned by `getLocations`.
  The pinned API orders by `C_BPartner_Location_ID` (`MBPartner.java:515–517`),
  so this is a declared key order, but not a business-role selection guarantee.
- Credit memo selection remains the unchanged generic credit-type API. Multiple
  equally ranked eligible credit types in another fixture are not qualified.
- Recovery selections enforce singleton caller keys; cohort-05's non-locking
  `firstOnly` is valid for that purpose because `Query.java:411–439` rejects a
  second row. It is not used as the locking API. Expected injected failures are
  swallowed intentionally; unexpected failures and worker errors propagate.
  Cleanup can replace a primary exception on an exceptional path, which affects
  diagnostic attribution but does not manufacture a success.

This review supports the recorded passes on the admitted journey. It does not
establish production readiness, unfamiliar-fixture behavior, or an independent
human review. The exact per-pass locations and qualifications are in the JSON.

## Next-round boundary

The dominant observed cause remains a candidate runtime assertion, so the
proposed closed runtime diagnostic remains the candidate single intervention.
Do not teach the reversal-allocation rule or supply this analysis to builders.
The completed packet must be adjudicated before B04 implementation/freeze/run
continues under this task's current boundary. See [REVIEW.md](REVIEW.md).
