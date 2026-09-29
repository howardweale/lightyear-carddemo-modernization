# MS-94 review packet · technical pre-review

Packet `64a9df9c…fd20`, reviewed against `main` at `34b9641`.

**This is not the required human review.** The packet requires human reviewers,
and for purchasing, one other than the author. This pre-review is written for
that person to work from. Neither review should be marked complete on the strength
of it.

---

## Integrity

- All seven packet files match `main` byte for byte.
- The packet's `content_sha256` recomputes correctly (sorted keys, compact JSON).
- Tests covering these files: 14 pass. One failure is an environment `mcp` version
  in my sandbox, not the code.

---

## Process findings

**P1 · Who can review.** MS-93 was AI-developed at the operator's direction. For
the purchasing review, "a human other than the author" should mean someone who
did not direct or accept MS-93's purchasing work, ideally with iDempiere
costing experience. Record the reviewer's identity and relationship to the work.

**P2 · The proposal register reuses a frozen version name.** It is labelled
`idempiere-declared-comparison-v3`, the same as MS-91's register, but its content
differs: three rules' scopes are widened (application clock 76→90 columns, fresh
UUID 38→45, processed epoch 6→8). Owners, effective dates and review dates are
unchanged. Widening scope is a new decision. Give it a new version identifier and
a fresh owner approval with its own dates.

---

## `JourneySupport.java` · approve after two small fixes

Verified against iDempiere at `731515dc`:

- `DocManager.postDocument(ass, tableId, recordId, force, repost, trxName)` exists;
  it's called with `force=false, repost=false`.
- `PO.get_ValueAsBoolean` returns false for a missing column, so `postOnce` then
  throws "Document remains unposted". It fails safe.
- The copy embedded in the operations reference is identical to the public file.

| # | Severity | Finding | Fix |
|---|---|---|---|
| S1 | **Fix** | In `transaction()`, if the body throws and `rollback()` then returns false, the `finally` block throws "Rollback failed" and **the original exception is lost**. The judge and the builder's diagnostics depend on the real failure. | Catch the body's exception, attempt rollback, and attach any rollback failure with `addSuppressed` before rethrowing the original. |
| S2 | **Fix** | `text()` gives plain formatting only to `BigDecimal`. A `Double` or `Float` falls through to `String.valueOf`, which can produce exponent notation (`1.0E10`), which judge v3 refuses. | Refuse `Double` and `Float` outright, or format through `BigDecimal`. |
| S3 | Minor | `"SQL-NULL"` can't be distinguished from a real string with that value. `postOnce` ignores `load()`'s return value, where the reference's own `post()` asserts it. "Posting failed" drops iDempiere's error text. | Keep the error text in the private log; assert `load()`. |
| S4 | Note | The operations reference wraps `fact()` so a duplicate key is silently **replaced**, bypassing the library's duplicate-key guard. The positive control never exercises that guard, and MS-92 failures included duplicate trace entries. | Add a negative control for a duplicate trace key. |
| S5 | Limit | Already disclosed: the posting guard doesn't stop iDempiere's own costing from reposting. | Keep it in the declared limits. |

---

## Purchasing rule and reference · not ready for approval

**What's sound:**

- Costs and quantities are not normalized. The register only adds UUID, clock and
  processed-time columns for the new tables. Cost values must still match exactly
  across the two engines.
- Existing costing and history rows must be unchanged, and history must balance.
- The hardcoded table `472` is `M_MatchInv` at the pinned commit.
- The reference posts only the invoice, payment and allocation, with
  `repost=false`, and never posts the `MatchInv` itself.

**Blocking findings:**

| # | Finding | Fix |
|---|---|---|
| R1 | **The rule can't tell iDempiere's own reposting from a candidate's.** Adding `t_fact_acct_history` to the footprint is safe only if history comes from native matching. The scope check accepts any balanced history for this journey's `MatchInv` records with the right vendor. A candidate that calls `postDocument(..., repost=true)` on a `MatchInv` produces the same history on both engines, and it passes. That is MS-88's protection, lost for this table. The existing test covers only an *unrelated* document. | Add a static check on the candidate refusing `repost=true`, `force=true` and `postImmediate`. Bound history to the generations native behaviour actually produces, measured from reference runs. Add a "candidate reposts its own `MatchInv`" mutant to the MS-94 suite. |
| R2 | **Row ownership is checked for only three tables.** The footprint is table-level. Other products' `m_costdetail` rows, `m_matchpo` and `m_product_po` aren't ownership-checked, so a write outside the journey that is identical on both engines goes unseen. | Every added or changed row in a table added for purchasing must belong to the journey. The vendor-product row update in `m_product_po` is legitimate and should be named explicitly. |
| R3 | **A candidate defect would be classified as an equipment failure.** Scope-check messages ("Side effect escaped journey product/client", "Reposting history is unbalanced", and others) aren't on the judge's business-failure list, so they become `judge-error`. Under MS-94's rule, a judge error voids the cohort. Classification is also done by message prefix, so renaming a message silently reclassifies it. | Replace prefix matching with typed exceptions: business failure versus equipment failure. |

**For the human reviewer to confirm:**

- **R4 · Where the rule came from.** The reference derives from an MS-92 candidate,
  and the rule was written after seeing those candidates' side effects. Confirm
  from iDempiere's matching and costing source that reposting on match is native
  behaviour, independent of any candidate.
- **R5 · Contract shape.** The scope check requires exactly one order line, one
  receipt line and one invoice line. State that in the purchasing public contract,
  which is the MS-92 ambiguity lesson.
- **R6 · Support library in purchasing.** The purchasing reference doesn't use
  `JourneySupport`; it has its own `post()` and `fact()`. Either migrate it, or
  state that the library is qualified for operations only.
- **R7 · A pre-existing question.** `c_acctschema`, the accounting schema
  configuration, is in both footprints. Why would a journey write accounting
  configuration?

---

## Recommendation

**Decouple the two reviews.** MS-94 stage B measures the operations journey only,
so it needs the support review and not the purchasing one.

1. Fix S1 and S2, then do the human support review. That unblocks MS-94.
2. Keep purchasing out of MS-94. Fix R1 to R3, add the R1 mutant, then do the
   independent purchasing review before any procure-to-pay cohort.
