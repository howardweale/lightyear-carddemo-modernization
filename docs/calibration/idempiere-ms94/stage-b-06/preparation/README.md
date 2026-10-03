# B06 preparation decisions

Howard confirmed the following in the task on October 3, 2026. This is operator
review, not independent review, qualification, preregistration or launch approval.
The exact preparation record is [operator-decisions.json](operator-decisions.json).

## Headline rule

Every journey, including J3, must achieve at least **21 final passes out of 24
cohort trials**. The two pilots per journey are excluded. If any journey falls
below that threshold, report the results per journey with no cross-journey claim.
J3 always counts; a missing or void J3 cannot support the three-journey claim.

At 21/24 the two-sided Wilson 95% interval has a lower bound of
0.6899611872949993, displayed as **69.0%** to one decimal place. The operative
pass-count threshold is 21/24; rounding does not silently raise it to 22/24.

## J3 choice and judge requirements

J3 is **materials: movement → internal use → physical count**. Its judge must
verify inventory costing and valuation, and the accounting facts for internal use
and physical-count differences, on both Oracle and PostgreSQL. Quantity checks
alone do not qualify the judge. Qualification must include mutants for:

- Wrong cost.
- Wrong account.
- Wrong quantity sign.

Selection is confirmed; novelty verification, sealing and qualification are still
pending. The generic builder template must be frozen before the J3 work order is
written, and the hidden expected values must remain outside builder inputs.

## Previously confirmed limits and audit authorization

Preparation uses 390 calls, 234 compilations and 96 hours including pauses, with
5 calls, 3 compilations and 7,190 seconds including finalization per trial.
Howard also explicitly authorized continuing the zero-model B05 terminal audit.
New audit files belong outside frozen B05; B05 is not rerun or modified, and B04
remains void. This record authorizes no model calls or public publication.
