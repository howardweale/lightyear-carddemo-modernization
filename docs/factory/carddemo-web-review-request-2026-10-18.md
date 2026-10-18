# Unsigned CardDemo six-screen review request

The adjacent `factory-contract/1` request uses `equivalence-review`, program `factory`, and twin scope. It binds the [evidence packet](carddemo-web-review-evidence-2026-10-18.json) to the exact commit where that packet and its referenced receipt and complete CI archives exist. Its source SHA-256 and packet digest were verified against Git blobs.

CI run 39127778944 passed all 120 cases and 678 API/browser interactions across six programs. Strict mutation proof killed 701 of 768 mutants (91.28%), with 49 survivors, 17 uncovered mutants and one timeout retained in the denominator. The [October 18 receipt](../modernization/carddemo-slice-1-2026-10-18.md) includes measured source/tested identities, shared-reference dependencies, all quirks, archive hashes and the static review of remaining mutants.

This is an unsigned request for Howard to review bounded evidence and its limitations. It has not been signed, imported or activated. Native execution, production data, SQL-error screen equivalence, other maps/services and release acceptance remain unproved. Publication-head CI and Howard's exact-SHA merge approval are still required; no merge or Phase 2 authority is granted.
