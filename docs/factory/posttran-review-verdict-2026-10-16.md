# POSTTRAN review verdict — 2026-10-16

Not releasable: nine fresh-campaign gaps remain after the effective twin-only October 12 supplement; no new z/OS acceptances.

Measured head `f343925026bee705ed3c16a734dc5bae4b24c588`, run 38763552148. This is a new analysis of retained evidence, not a new campaign.

| Scope | Before supplement | Projected | Unresolved |
| --- | --- | --- | --- |
| twin | 360/384 | 360/370 | 10 |
| zos-facing | 360/390 | 360/390 | 30 |

Diversity: 0 fields below two values.


## CBTRN02C-receiving-scale-94-4

TCATBALF dump helper refused with rc66 after the application; changed receiving scale is not the INTCALC duplicate-key loader case.

Preserve the mutant indexed bytes; add a bounded raw-record dumper that records invalid numeric representation rather than refusing before comparison. Fresh exact-head CI evidence is required.

Scenarios: posttran-zero, posttran-positive, posttran-negative, posttran-credit-equal, posttran-expiry-equal, posttran-duplicate-id, posttran-new-category, posttran-cycle-debit, posttran-invalid-then-valid, posttran-new-then-existing, posttran-expiry-equal-dash, posttran-solver-credit-true, posttran-diversity-0, posttran-diversity-1, fault:528-rewrite-error:posttran-positive

## CBTRN02C-receiving-scale-96-6

TCATBALF dump helper refused with rc66 after the application; changed receiving scale is not the INTCALC duplicate-key loader case.

Preserve the mutant indexed bytes; add a bounded raw-record dumper that records invalid numeric representation rather than refusing before comparison. Fresh exact-head CI evidence is required.

Scenarios: posttran-zero, posttran-positive, posttran-negative, posttran-credit-equal, posttran-expiry-equal, posttran-duplicate-id, posttran-new-category, posttran-cycle-debit, posttran-invalid-then-valid, posttran-new-then-existing, posttran-expiry-equal-dash, posttran-solver-credit-true, posttran-diversity-0, posttran-diversity-1, fault:528-rewrite-error:posttran-positive

## CBTRN02C-relational-203-36

The four-second application timeout fired; the mutated control flow removes read/EOF/abend progress.

Keep as a gap. A bounded progress or termination witness and an explicitly reviewed timeout classification are required; raising the timeout or treating a refusal as a kill is not justified.

Scenarios: posttran-zero, posttran-positive, posttran-negative, posttran-credit-equal, posttran-credit-above, posttran-expiry-equal, posttran-expiry-before, posttran-missing-card, posttran-missing-account, posttran-empty, posttran-duplicate-id, posttran-new-category, posttran-large-amount, posttran-cycle-debit, posttran-invalid-then-valid, posttran-new-then-existing, posttran-expiry-next-day, posttran-expiry-equal-dash, posttran-cycle-debit-sign, posttran-solver-credit-false, posttran-solver-credit-true, posttran-diversity-0, posttran-diversity-reject-0, posttran-diversity-1, posttran-diversity-reject-1, fault:346-extended-read-error:posttran-positive, fault:528-rewrite-error:posttran-positive

## CBTRN02C-negate-condition-203-37

The four-second application timeout fired; the mutated control flow removes read/EOF/abend progress.

Keep as a gap. A bounded progress or termination witness and an explicitly reviewed timeout classification are required; raising the timeout or treating a refusal as a kill is not justified.

Scenarios: posttran-zero, posttran-positive, posttran-negative, posttran-credit-equal, posttran-credit-above, posttran-expiry-equal, posttran-expiry-before, posttran-missing-card, posttran-missing-account, posttran-empty, posttran-duplicate-id, posttran-new-category, posttran-large-amount, posttran-cycle-debit, posttran-invalid-then-valid, posttran-new-then-existing, posttran-expiry-next-day, posttran-expiry-equal-dash, posttran-cycle-debit-sign, posttran-solver-credit-false, posttran-solver-credit-true, posttran-diversity-0, posttran-diversity-reject-0, posttran-diversity-1, posttran-diversity-reject-1, fault:346-extended-read-error:posttran-positive, fault:528-rewrite-error:posttran-positive

## CBTRN02C-skip-PERFORM-204-38

The four-second application timeout fired; the mutated control flow removes read/EOF/abend progress.

Keep as a gap. A bounded progress or termination witness and an explicitly reviewed timeout classification are required; raising the timeout or treating a refusal as a kill is not justified.

Scenarios: posttran-zero, posttran-positive, posttran-negative, posttran-credit-equal, posttran-credit-above, posttran-expiry-equal, posttran-expiry-before, posttran-missing-card, posttran-missing-account, posttran-empty, posttran-duplicate-id, posttran-new-category, posttran-large-amount, posttran-cycle-debit, posttran-invalid-then-valid, posttran-new-then-existing, posttran-expiry-next-day, posttran-expiry-equal-dash, posttran-cycle-debit-sign, posttran-solver-credit-false, posttran-solver-credit-true, posttran-diversity-0, posttran-diversity-reject-0, posttran-diversity-1, posttran-diversity-reject-1, fault:346-read-error:posttran-positive, fault:346-premature-eof:posttran-positive, fault:346-extended-read-error:posttran-positive

## CBTRN02C-constant-230-68

Mutated return code 3 or 5 was rejected by the harness before a complete comparison receipt.

Record every completed process return code and all complete after-images, then compare the codes. Do not broaden the candidate allowed-code contract or credit these old refusals as kills.

Scenarios: posttran-credit-above, posttran-expiry-before, posttran-missing-card, posttran-missing-account, posttran-large-amount, posttran-invalid-then-valid, posttran-expiry-next-day, posttran-cycle-debit-sign, posttran-solver-credit-false, posttran-diversity-reject-0, posttran-diversity-reject-1

## CBTRN02C-constant-230-69

Mutated return code 3 or 5 was rejected by the harness before a complete comparison receipt.

Record every completed process return code and all complete after-images, then compare the codes. Do not broaden the candidate allowed-code contract or credit these old refusals as kills.

Scenarios: posttran-credit-above, posttran-expiry-before, posttran-missing-card, posttran-missing-account, posttran-large-amount, posttran-invalid-then-valid, posttran-expiry-next-day, posttran-cycle-debit-sign, posttran-solver-credit-false, posttran-diversity-reject-0, posttran-diversity-reject-1

## CBTRN02C-delete-MOVE-354-173

The four-second application timeout fired; the mutated control flow removes read/EOF/abend progress.

Keep as a gap. A bounded progress or termination witness and an explicitly reviewed timeout classification are required; raising the timeout or treating a refusal as a kill is not justified.

Scenarios: fault:346-read-error:posttran-positive, fault:346-extended-read-error:posttran-positive

## CBTRN02C-skip-PERFORM-366-179

The four-second application timeout fired; the mutated control flow removes read/EOF/abend progress.

Keep as a gap. A bounded progress or termination witness and an explicitly reviewed timeout classification are required; raising the timeout or treating a refusal as a kill is not justified.

Scenarios: fault:346-read-error:posttran-positive, fault:346-extended-read-error:posttran-positive
