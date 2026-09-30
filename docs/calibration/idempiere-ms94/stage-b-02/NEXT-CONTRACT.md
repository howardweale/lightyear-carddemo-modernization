# Next-run public contract: retain the order-derived invoice type

Approved by Howard Weale on 29 September 2026 as a **prospective** requirement.
This addendum records the exact single proposed contract change. It has not been
inserted into a frozen campaign, and publication is not a new qualification result.

## Builder-visible requirement

For the original aggregate sales invoice, resolve the invoice document type from
the completed order's document type through its `C_DocTypeInvoice_ID` relationship.
Set and retain that order-derived invoice type as `C_DocTypeTarget_ID`; the completed
invoice's `C_DocType_ID` must also be that type. Using `new MInvoice(order, 0, date)`
and retaining its resolved target is one permitted implementation. Another API
sequence is permitted if it preserves the same relationship and native workflow.
Do not replace this selection with a generic ARI lookup or another invoice type,
including an otherwise active ARI type. Read the relationship from application
configuration; do not hardcode a document-type identifier or expected business value.
This requirement applies to the original sales invoice. Existing credit/reversal
requirements continue to apply to those documents.

## Qualification and measurement boundary

The one intervention is this public contract clarification and its matching
structural acceptance rule. Do not introduce a smoke-run tool, widen closed
diagnostics, change support behavior or otherwise repair candidates in this
condition. The previously provisional smoke-run intervention is deferred.

Before measuring, integrate the same clause into the actual builder-visible
contract and establish the structural check against the order's configured
relationship. Requalify the changed acceptance boundary with a valid retained-type
reference, a valid equivalent API implementation, and a deliberately different
eligible ARI type. Verify both engines, publications and required source reviews.
Passing a replay of old captures alone is not fresh native qualification.
This document does not assert that those integration/qualification steps are done.

Then freeze and publish a new plan for **20 fresh cohort trials**, with any pilots
separately declared and excluded. Keep the per-trial five-call/three-compilation
limits and declare the larger aggregate budget before execution. Do not extend,
replace or reuse Stage B 02 slots. Do not start generation before qualification
and the new plan's public timestamp. Retain the same interval method and preserve
all outcomes, including invalidity or stopping results.

## Effect on Stage B 02

None of the frozen inputs or verdicts changes. Its recorded result remains 2/10
with 95% Wilson interval 5.7%–51.0%. The five Category B outcomes remain paired
comparison rejections under an underspecified public contract. Approval of this
new rule does not prove the old builder was instructed to follow it, and does not
convert those outcomes into five established model business-logic failures or
five passes. The original signed report and the post-run assessment remain distinct.
