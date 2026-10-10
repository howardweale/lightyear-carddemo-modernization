# Verify smoke fixture audit and proposed v2

Report only, October 10, 2026. No kit, inventory, candidate artifact or recorded result changed.

`tools/verify_smoke/provision.py` pins exactly `tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-2026-10-05`. Its 50 category balances are zero; the public rule records show the 15% DEFAULT fallback and zero emitted interest. Arithmetic is reached but no nonzero balance product is tested. `good.jar` equivalence therefore exercises record plumbing, grouping, formatting, timestamps and this degenerate arithmetic path, not nonzero financial arithmetic or Maintec equivalence.

`tools/verify_smoke/build_candidates.py` names a mutant `rounding.jar`, but it adds a cent after the calculation; it does not change the rounding mode. A zero fixture can kill that mutant. `skipped.jar` removes an account and `date.jar` changes both timestamps. The existing reported divergent outcomes remain valid within that scope; this audit is not a new VM smoke run or a verification of unsupplied historical receipts.

Proposed v2, subject to Howard's separate approval: create a new immutable attempt inventory using the new synthetic reference-model matrix, include direct/fallback/zero rates, negative and large balances, rounding boundaries and final-account cases. Keep v1 and its receipts unchanged. Include distinct HALF_UP and scale mutations; explicitly disclose any surviving scale-plus-one case after two-decimal rendering. New VM attempts and candidate artifacts would require a separately reviewed inventory and authorization. Nothing in this PR authorizes that change or a run.
