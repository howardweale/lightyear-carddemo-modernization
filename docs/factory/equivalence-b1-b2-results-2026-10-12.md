# B1/B2 completed results — October 12, 2026

Exact head `2dd787642e66176f78dbf749ec2659e82672cd3e`, [run 38198096890](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38198096890). Both this report and its [compact JSON](equivalence-b1-b2-results-2026-10-12.json) bind the artifact IDs and archive hashes below. Publication does not substitute its own head for the measured head. Raw records remain unchanged.

POSTTRAN corrected raw kills: **360/483** (185 failure, 175 divergent); the nine execution refusals formerly credited as kills receive no kill credit. INTCALC: **308/421** (162 failure, 146 divergent). No threshold or release credit.

## INTCALC

Fresh campaign: 421 sites; counts `{"evidence-gap": 113, "killed-divergent": 146, "killed-failure": 162}`; compiler refusals `[]`; generator avoided 5 invalid mutants.

113 arguments: compiler-proven 2, class-proof 81, individually argued 30, refuted 0. Evidence-gap overlap: 113; overlaps proof categories, not a disjoint fifth category.

Targeted scheduled cases 6000; valid comparisons 5604; refutations 0. Every gap and any witness is in JSON target_details; targeted gap IDs: CBACT04C-receiving-scale-164-26, CBACT04C-receiving-scale-173-34.

Business 8/8; I/O 85/86. Howard accepted source-unreachable EOF false edges on 2026-10-11; that acceptance does not fabricate observed coverage.

Accepted I/O gaps: `[{"classification": "io-handling", "id": "legacy:cobol-decision:CBACT04C:189:671", "line": 189, "outcome": "false", "reason": "not-observed; no unreachability claim"}]`.

Fields below two observed values:

- `ACCTFILE:ACCOUNT-RECORD.ACCT-ACTIVE-STATUS`: 1
- `TRANSACT:TRAN-RECORD.TRAN-CAT-CD`: 1
- `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY`: 1
- `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID`: 1
- `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME`: 1
- `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP`: 1
- `TRANSACT:TRAN-RECORD.TRAN-ORIG-TS`: 1
- `TRANSACT:TRAN-RECORD.TRAN-PROC-TS`: 1
- `TRANSACT:TRAN-RECORD.TRAN-SOURCE`: 1
- `TRANSACT:TRAN-RECORD.TRAN-TYPE-CD`: 1

| Scope | Eligible | Kills | Rate | >=90% | All conditions met |
|---|---:|---:|---|---|---|
| twin | 421 | 308 | 308/421 | False | False |
| zos-facing | 421 | 308 | 308/421 | False | False |

Blockers: output-fields-below-two-values, mutation-or-individual-review-conditions-unmet, required-targeted-experiment-evidence-incomplete. All scope-specific unresolved IDs remain in JSON.

Fresh execution gap IDs: CBACT04C-receiving-scale-72-6, CBACT04C-receiving-size-125-13, CBACT04C-receiving-scale-125-14, CBACT04C-receiving-size-133-19, CBACT04C-receiving-scale-133-20, CBACT04C-receiving-size-138-21, CBACT04C-receiving-size-139-23, CBACT04C-receiving-scale-139-24, CBACT04C-receiving-scale-164-26, CBACT04C-receiving-scale-169-30, CBACT04C-receiving-size-172-31, CBACT04C-receiving-scale-172-32, CBACT04C-receiving-scale-173-34, CBACT04C-receiving-size-177-35, CBACT04C-constant-192-48, CBACT04C-constant-192-49, CBACT04C-delete-ADD-192-50, CBACT04C-constant-214-70, CBACT04C-constant-214-71, CBACT04C-skip-PERFORM-216-74, CBACT04C-skip-PERFORM-220-75, CBACT04C-constant-235-81, CBACT04C-constant-235-82, CBACT04C-delete-MOVE-235-83, CBACT04C-constant-240-89, CBACT04C-constant-240-90, CBACT04C-delete-MOVE-240-91, CBACT04C-delete-MOVE-246-93, CBACT04C-skip-PERFORM-247-94, CBACT04C-skip-PERFORM-248-95, CBACT04C-constant-253-96, CBACT04C-constant-253-97, CBACT04C-delete-MOVE-253-98, CBACT04C-constant-258-104, CBACT04C-constant-258-105, CBACT04C-delete-MOVE-258-106, CBACT04C-delete-MOVE-264-108, CBACT04C-skip-PERFORM-265-109, CBACT04C-skip-PERFORM-266-110, CBACT04C-constant-271-111, CBACT04C-constant-271-112, CBACT04C-delete-MOVE-271-113, CBACT04C-constant-276-119, CBACT04C-constant-276-120, CBACT04C-delete-MOVE-276-121, CBACT04C-delete-MOVE-282-123, CBACT04C-skip-PERFORM-283-124, CBACT04C-skip-PERFORM-284-125, CBACT04C-constant-290-126, CBACT04C-constant-290-127, CBACT04C-delete-MOVE-290-128, CBACT04C-constant-295-134, CBACT04C-constant-295-135, CBACT04C-delete-MOVE-295-136, CBACT04C-delete-MOVE-301-138, CBACT04C-skip-PERFORM-302-139, CBACT04C-skip-PERFORM-303-140, CBACT04C-constant-308-141, CBACT04C-constant-308-142, CBACT04C-delete-MOVE-308-143, CBACT04C-constant-313-149, CBACT04C-constant-313-150, CBACT04C-delete-MOVE-313-151, CBACT04C-delete-MOVE-319-153, CBACT04C-skip-PERFORM-320-154, CBACT04C-skip-PERFORM-321-155, CBACT04C-delete-MOVE-328-160, CBACT04C-constant-333-166, CBACT04C-constant-333-167, CBACT04C-delete-MOVE-333-168, CBACT04C-delete-MOVE-343-172, CBACT04C-skip-PERFORM-344-173, CBACT04C-skip-PERFORM-345-174, CBACT04C-delete-MOVE-358-187, CBACT04C-constant-360-188, CBACT04C-constant-360-189, CBACT04C-delete-MOVE-360-190, CBACT04C-delete-MOVE-366-192, CBACT04C-skip-PERFORM-367-193, CBACT04C-skip-PERFORM-368-194, CBACT04C-delete-MOVE-379-199, CBACT04C-constant-381-200, CBACT04C-constant-381-201, CBACT04C-delete-MOVE-401-211, CBACT04C-constant-403-212, CBACT04C-constant-403-213, CBACT04C-relational-422-219, CBACT04C-delete-MOVE-423-223, CBACT04C-constant-425-224, CBACT04C-constant-425-225, CBACT04C-delete-MOVE-425-226, CBACT04C-delete-MOVE-432-228, CBACT04C-skip-PERFORM-433-229, CBACT04C-skip-PERFORM-434-230, CBACT04C-delete-MOVE-447-239, CBACT04C-constant-449-240, CBACT04C-constant-449-241, CBACT04C-delete-MOVE-491-264, CBACT04C-delete-MOVE-492-265, CBACT04C-delete-MOVE-493-266, CBACT04C-delete-MOVE-494-267, CBACT04C-delete-MOVE-502-277, CBACT04C-constant-504-278, CBACT04C-constant-504-279, CBACT04C-delete-MOVE-504-280, CBACT04C-delete-MOVE-511-282, CBACT04C-skip-PERFORM-512-283, CBACT04C-skip-PERFORM-513-284, CBACT04C-constant-523-285, CBACT04C-constant-523-286, CBACT04C-delete-MOVE-523-287, CBACT04C-constant-528-293, CBACT04C-constant-528-294, CBACT04C-delete-MOVE-528-295, CBACT04C-delete-MOVE-534-297, CBACT04C-skip-PERFORM-535-298, CBACT04C-skip-PERFORM-536-299, CBACT04C-constant-542-300, CBACT04C-constant-542-301, CBACT04C-delete-MOVE-542-302, CBACT04C-constant-547-308, CBACT04C-constant-547-309, CBACT04C-delete-MOVE-547-310, CBACT04C-delete-MOVE-553-312, CBACT04C-skip-PERFORM-554-313, CBACT04C-skip-PERFORM-555-314, CBACT04C-constant-560-315, CBACT04C-constant-560-316, CBACT04C-delete-MOVE-560-317, CBACT04C-constant-565-323, CBACT04C-constant-565-324, CBACT04C-delete-MOVE-565-325, CBACT04C-delete-MOVE-571-327, CBACT04C-skip-PERFORM-572-328, CBACT04C-skip-PERFORM-573-329, CBACT04C-constant-578-330, CBACT04C-constant-578-331, CBACT04C-delete-MOVE-578-332, CBACT04C-constant-583-338, CBACT04C-constant-583-339, CBACT04C-delete-MOVE-583-340, CBACT04C-delete-MOVE-589-342, CBACT04C-skip-PERFORM-590-343, CBACT04C-skip-PERFORM-591-344, CBACT04C-constant-596-345, CBACT04C-constant-596-346, CBACT04C-delete-MOVE-596-347, CBACT04C-constant-601-353, CBACT04C-constant-601-354, CBACT04C-delete-MOVE-601-355, CBACT04C-delete-MOVE-607-357, CBACT04C-skip-PERFORM-608-358, CBACT04C-skip-PERFORM-609-359, CBACT04C-delete-MOVE-630-373, CBACT04C-constant-638-380, CBACT04C-constant-638-382, CBACT04C-delete-MOVE-638-383, CBACT04C-constant-639-384, CBACT04C-constant-639-385, CBACT04C-delete-MOVE-639-386, CBACT04C-delete-MOVE-640-387, CBACT04C-delete-MOVE-641-388, CBACT04C-delete-MOVE-644-389, CBACT04C-CVACT03Y-receiving-size-6-1, CBACT04C-CVACT03Y-receiving-scale-6-2, CBACT04C-CVACT03Y-receiving-size-7-3, CBACT04C-CVACT03Y-receiving-scale-7-4.

## POSTTRAN

Fresh campaign: 483 sites; counts `{"equivalent (argued, listed)": 111, "evidence-gap": 9, "killed-divergent": 175, "killed-failure": 185, "survived": 3}`; compiler refusals `[]`; generator avoided 6 invalid mutants.

114 arguments: compiler-proven 1, class-proof 96, individually argued 17, refuted 0. Evidence-gap overlap: 1; overlaps proof categories, not a disjoint fifth category.

Targeted scheduled cases 3400; valid comparisons 3202; refutations 0. Every gap and any witness is in JSON target_details; targeted gap IDs: CBTRN02C-receiving-scale-173-20.

Business 24/24; I/O 85/86. Howard accepted source-unreachable EOF false edges on 2026-10-11; that acceptance does not fabricate observed coverage.

Accepted I/O gaps: `[{"classification": "io-handling", "id": "legacy:cobol-decision:CBTRN02C:203:684", "line": 203, "outcome": "false", "reason": "not-observed; no unreachability claim"}]`.

Fields below two observed values:

- `ACCTFILE:ACCOUNT-RECORD.ACCT-ACTIVE-STATUS`: 1
- `ACCTFILE:ACCOUNT-RECORD.ACCT-GROUP-ID`: 1
- `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-CAT-CD`: 1
- `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-MERCHANT-ID`: 1
- `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-PROC-TS`: 1
- `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-SOURCE`: 1
- `DALYREJS:REJECT-RECORD.DALYTRAN-RECORD.DALYTRAN-TYPE-CD`: 1
- `TRANFILE:TRAN-RECORD.TRAN-MERCHANT-ID`: 1
- `TRANFILE:TRAN-RECORD.TRAN-PROC-TS`: 1

| Scope | Eligible | Kills | Rate | >=90% | All conditions met |
|---|---:|---:|---|---|---|
| twin | 384 | 360 | 360/384 | True | False |
| zos-facing | 390 | 360 | 360/390 | True | False |

Blockers: output-fields-below-two-values, mutation-or-individual-review-conditions-unmet, required-targeted-experiment-evidence-incomplete. All scope-specific unresolved IDs remain in JSON.

Fresh execution gap IDs: CBTRN02C-receiving-scale-94-4, CBTRN02C-receiving-scale-96-6, CBTRN02C-relational-203-36, CBTRN02C-negate-condition-203-37, CBTRN02C-skip-PERFORM-204-38, CBTRN02C-constant-230-68, CBTRN02C-constant-230-69, CBTRN02C-delete-MOVE-354-173, CBTRN02C-skip-PERFORM-366-179.

## Artifact bindings

| ID | Artifact | Archive SHA-256 |
|---|---|---|
| 11726200857 | factory-review-records-POSTTRAN-1 | `196f90a03bf959741cbb48dc932e91a888e8286daf4c1bab0addc1ef44aae27e` |
| 11726130123 | factory-review-records-POSTTRAN-2 | `8868d9a4fa2b736f83899da8d3ac7d043967821a6368b8c0032bd4b8dbbe5fa4` |
| 11726077543 | factory-review-records-POSTTRAN-3 | `e14596811326771ec3272255aa66bc4a08f00b40449085a395cbef1789cc173f` |
| 11725723427 | equivalence-aggregate | `db0730cdb516290c58b13991e0d7cfb33f746541baf4c2c64fc6fef4cf71a1bb` |
| 11725625830 | factory-review-records-POSTTRAN-0 | `3d680aa4e6c519994866c0661c992862083ab88fdc70471b32bbb58467e1ad79` |
| 11725177809 | factory-review-records-INTCALC-0 | `492608bd8c041a0ea81fd7206ca3923cb55539f18a61b4bc0f4a3d06d80dcff0` |
| 11724924915 | factory-review-records-INTCALC-1 | `e3b51ca22958df061aaa6cdf051347dcb6b201b5107cf3bb452402f20f938211` |

The compact JSON includes measured per-job times, separate fresh/target disk bytes, logical/compressed bytes per run and preflight headroom. Original failed run 38190468540 remains failed; no guard increase or cross-head resume. [47-mutant review packet](equivalence-individual-review-2026-10-12.md). Operator review, not independent attestation.
