# B06 observer-v2 five-path census: executable preparation

The new immutable snapshot and executable plan are prepared for **October 8,
20:00 to October 9, 07:00 PDT** (October 9, 03:00–14:00 UTC). The exact public
commit and a fresh Tower authorization are required before Docker. No native
pair, model call or new authorization was issued during this preparation.

| Binding | SHA-256 |
| --- | --- |
| Executable snapshot, 113,610 files | `fa7607b2c130660e3144398c5c464a1ed074c372fbf80e7e5ce88a852ad663f6` |
| Executable plan | `dea30b0b1b76ab24a7f1de660e06630179d6f9ad2735b90b10825335abd68f42` |
| Review schedule | `b5962b1643cbdb9c310f699611b4cb763d8248bf264ae6a9365af9b49bd6660e` |
| Frozen offline verification | `acb4e85331dfc153ae126c9b10f313a7c8bd3a232159bb5edcba2c42a46b6929` |

Implementation commit: `b8335c490bffae1c63add2a4079d4a71fc4aaee0`. The implementation bytes in the
snapshot match that public commit. Private class catalogues, references,
expectations, checkpoints and archive bytes remain local; these public records
contain hashes, counts and prospective expectations only.

## Schedule and limits

Five serial fresh Oracle/PostgreSQL pairs:

1. J1 retained reference: complete pass expected.
2. J1 duplicate invoice line: unchanged intended rejection expected.
3. J1 candidate null dereference: execution failure and direct closed diagnostic
   to the zero-model sink expected.
4. J2 retained reference: complete pass expected.
5. J3 retained reference: complete pass expected.

The executable plan's `slots[].plan_path` binds each actual fresh native owner.
The review schedule retains `prospective_native_run_id` from the earlier private
input-preparation record as provenance; it is not a launch path or authorization.

Each pair has **7,190 seconds**, including finalization, and a **1,800-second
candidate timeout**. The aggregate pair budget is **35,950 seconds**. A further
600 seconds is reserved before the 07:00 deadline; the prospective launcher must
refuse after **20:50:50 PDT**, or if the entire budget no longer fits. No deadline
extension, retry, resumed slot or replacement slot is authorized.

Application and databases use real clocks, October 1 scenario dates and the
period-boundary guard. The retained built runtime is
`sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`. Native launch uses its compiled outputs directly,
without a Maven rebuild. J1 predicates and expected outcomes are unchanged.
The ordinary class and generated-target observer-v2 rules remain fail-closed.
All generated records must be retained whatever the outcome. An unexpected
result stops the group and preserves its evidence before lengthy replay.

## Validation and remaining gates

All five offline native plan assemblies passed. The complete baseline manifest
validated 110,544 class bindings. The B06 suite passed 202 tests with 10 optional
local-evidence skips, and the focused manifest subset passed 15 tests. The
published implementation's 28 CI checks passed. Final frozen verification
rehashes every one of the 113,610 files, compares
766 Python/observer source files with the public
implementation commit, and runs the four focused test modules listed in
[frozen-verification.json](frozen-verification.json). Its elapsed time includes
waiting for the freeze; the freeze helper's 4675.703 seconds
also includes its preceding wait. Neither is a native runtime measurement.

This census gives **no journey qualification or measurement credit**. Native
observer provenance on both engines is still unproven. Journey qualification,
measurement preflight and measurement authorization remain separate subsequent
gates. Earlier failures stay failed; B04 remains void and B05 is untouched.

The earlier [preparation.json](preparation.json) is retained as historical
pre-freeze status. [executable-plan.json](executable-plan.json),
[snapshot-summary.json](snapshot-summary.json) and the frozen verification
supersede its pending fields. Operator review, not independent attestation.
