**Recorded Stage B 03: 12/20 (60%); 95% Wilson interval 38.7%–78.1%. Classification stopped for a support-origin finding; validity review pending.**

# Post-run classification intake — incomplete

The adopted `TASK-MS94-B03-CLASSIFICATION.md`, Part 1 question 3, says:
“Is any failure thrown by `support` or `equipment`? **If yes, stop.**”
Pilot-03 meets that condition in both lanes. This record flags Stage B 03 for
measurement-validity review before further work. No signed report, receipt,
candidate, gate or frozen input has changed. No candidate was rerun or repaired,
no model or native execution was started, and no analysis was supplied to a builder.

[classification.json](classification.json) indexes all 23 recorded outcomes,
candidate and assembled-source hashes, native paths, gate hashes, costs and
existing diagnostic exports. Its status is explicitly incomplete. The index is
an evidence intake, not a completed failure classification or pass review.

## Stop finding

| Trial | Recorded class | First blocking stage | Exception and location | Origin | Lanes | Assessment |
|---|---|---|---|---|---|---|
| pilot-03 (excluded pilot) | execution-failure | Opening inventory posting, before order/invoice creation | `IllegalStateException`; `JourneySupport.postOnce`, assembled `LightyearOperationsTest.java:540`; candidate `post:72`, caller `businessJourney:199` | support | Both exit 1 at the same point | Equipment-suspect under the supplied stop rule; root-cause attribution and measurement validity unresolved |

The candidate calls the public posting helper on the opening inventory. The
helper calls `DocManager.postDocument`, receives a rejection and throws its
wrapper exception. The nested application failure concerns posting-lock
acquisition. The exception class is recorded, but exception messages and private
trace values are deliberately omitted. The partial traces contain the
`openingInventory.id`, `openingInventory.status` and `openingInventory.quantity`
fields and failed status, with no invoice fields. The existing analyst export
is exactly `{"diagnostics":[]}`.

The public support library is unchanged from the frozen snapshot. Its wrapper
is at `factory/idempiere/qualification-ms94-v3/public/JourneySupport.java:45`.
The native input hash matches the assembled source and the signed native receipt.
Report, trial and native receipt signatures were verified during this intake.

**Thrown by support is not yet proof that the support implementation is wrong.**
The application rejection could involve candidate call sequencing, application
posting behavior or a support/timing issue. This intake does not resolve that
causality. The gate accurately records interrupted execution; whether that is a
candidate-attributable failure requires adjudication. Being an excluded pilot
does not establish that the cohort is unaffected, nor does it automatically
invalidate the cohort. The signed nonvoid result is preserved.

The proposed B04 policy would suppress a support-origin runtime diagnostic and
route this case to `halted-equipment-suspect`; it would not provide a builder
repair diagnostic. That is a prospective policy assessment, not a relabeling.
The early abort masks later order, shipment, invoice, payment/allocation,
credit/reversal, rollback/retry and lock-interleaving checks.

## Required five answers at this stop

1. **Timing groups:** not adjudicated. Initial stack inspection found accounting
   assertion/helper frames in both cohort timing groups; elapsed time alone is
   not evidence of two causes. Full source/trace classification stopped.
2. **Category A count:** not established. Eight cohort failures have accounting
   frames, but this intake does not label them all Category A without completing
   the required source and stage review.
3. **Support/equipment origin:** yes, pilot-03 is support-origin in both lanes.
   The mandated stop is in effect. Underlying responsibility remains unresolved.
4. **Builder-visible contrary guidance:** not adjudicated. The public posting
   helper is identified above; its existence alone does not settle whether the
   candidate's use was valid. No new contract clarification has been added.
5. **Diagnostic localization prediction:** not established for the eight cohort
   failures. Pilot-03 would receive no runtime diagnostic under the proposed rule.

## Pass review and human review

All 12 cohort passes and the one pilot pass remain **not reviewed in this intake**,
rather than being assigned unsupported `accepted` labels. Prior mechanical
replay is not substituted for source review. [REVIEW.md](REVIEW.md) identifies
the specific validity decision needed to resume classification.

Howard's statement “operator approved” is preserved in
[operator-review-intake.json](operator-review-intake.json). It is operator
approval, not an independent review or a cryptographic human signature. No
independent reviewer has been identified. The statement answered reviewer
selection; it contains no explicit adjudication of this newly identified
pilot-03 failure. B04 implementation, qualification, freeze and generation have
not started.
