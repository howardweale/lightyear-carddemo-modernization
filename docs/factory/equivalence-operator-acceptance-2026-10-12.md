# Howard operator acceptance — October 12, 2026

Howard accepted the [supplied 47-item review](equivalence-review-47-claude-2026-10-12.md) in this chat as **AI-assisted operator review**, not independent human attestation. [Machine-readable binding](equivalence-operator-acceptance-2026-10-12.json).

This additive record contains **44 new acceptances and 3 references to existing acceptances**. Items **10, 33 and 38** are counted only in the October11 record. The historical decision file, raw campaign, review packet and signed-backfill inventory are unchanged. No new z/OS-facing acceptance is granted; the two existing October11 z/OS acceptances are unchanged. Host-only items **11–16, 19, 24, 37, 38 and 41** remain restricted to the pinned host compiler/runtime/adapter assumptions.

Items **20, 23 and 42** are accepted arguments but **not yet effective for individual-review exclusion**. Each requires its own 200 distinct case indices, 200 valid baseline/mutant executed comparisons, zero refusals/refutations, and verified complete shard aggregation from PR328 head `4cc7c1acda70249554938253004187ab8700dba4`, run `38296048295`. No satisfaction receipt is recorded. Old 2/200 evidence and results from other heads cannot satisfy this condition.

Item **30** depends on `CBACT04C-FINAL-ACCOUNT-EOF-ELSE`; **35 and 36** depend on `REWRITE-109`. Their exact register-entry hashes and current keep-by-default dispositions are bound. The offline validator rejects missing/changed entries or a fix authorization, requiring fresh review. All records also depend on their exact program/source and argument hashes.

These are operator decisions, not a cryptographic signature, runtime activation, threshold approval or release authorization. Existing threshold code is unchanged: this record must be consumed through validated bindings in a future evidence reconciliation; simply concatenating it into historical acceptances is prohibited. The duplicate-category proposal below is not effective and does not clear INTCALC evidence gaps. **All merges remain held until B06 cleanup is sealed.**

## Item mapping

| Item | Mutant | Record/status | Scope | Register dependency |
|---|---|---|---|---|
| 1 | `CBACT04C-CVACT03Y-receiving-scale-6-2` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 2 | `CBACT04C-CVACT03Y-receiving-scale-7-4` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 3 | `CBACT04C-CVACT03Y-receiving-size-6-1` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 4 | `CBACT04C-CVACT03Y-receiving-size-7-3` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 5 | `CBACT04C-constant-192-48` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 6 | `CBACT04C-constant-192-49` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 7 | `CBACT04C-constant-638-382` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 8 | `CBACT04C-constant-639-384` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 9 | `CBACT04C-constant-639-385` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 10 | `CBACT04C-delete-ADD-192-50` | Existing acceptance reference; no new count | Twin only; no new z/OS scope | — |
| 11 | `CBACT04C-delete-MOVE-491-264` | Accepted; source/register bindings apply | Twin, host-only | — |
| 12 | `CBACT04C-delete-MOVE-492-265` | Accepted; source/register bindings apply | Twin, host-only | — |
| 13 | `CBACT04C-delete-MOVE-493-266` | Accepted; source/register bindings apply | Twin, host-only | — |
| 14 | `CBACT04C-delete-MOVE-494-267` | Accepted; source/register bindings apply | Twin, host-only | — |
| 15 | `CBACT04C-delete-MOVE-630-373` | Accepted; source/register bindings apply | Twin, host-only | — |
| 16 | `CBACT04C-delete-MOVE-639-386` | Accepted; source/register bindings apply | Twin, host-only | — |
| 17 | `CBACT04C-delete-MOVE-644-389` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 18 | `CBACT04C-receiving-scale-133-20` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 19 | `CBACT04C-receiving-scale-139-24` | Accepted; source/register bindings apply | Twin, host-only | — |
| 20 | `CBACT04C-receiving-scale-164-26` | Accepted; waits for 200/200 receipt | Twin only; no new z/OS scope | — |
| 21 | `CBACT04C-receiving-scale-169-30` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 22 | `CBACT04C-receiving-scale-172-32` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 23 | `CBACT04C-receiving-scale-173-34` | Accepted; waits for 200/200 receipt | Twin only; no new z/OS scope | — |
| 24 | `CBACT04C-receiving-scale-72-6` | Accepted; source/register bindings apply | Twin, host-only | — |
| 25 | `CBACT04C-receiving-size-125-13` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 26 | `CBACT04C-receiving-size-138-21` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 27 | `CBACT04C-receiving-size-139-23` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 28 | `CBACT04C-receiving-size-172-31` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 29 | `CBACT04C-skip-PERFORM-216-74` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 30 | `CBACT04C-skip-PERFORM-220-75` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | CBACT04C-FINAL-ACCOUNT-EOF-ELSE |
| 31 | `CBTRN02C-CVACT03Y-receiving-scale-7-4` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 32 | `CBTRN02C-constant-717-443` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 33 | `CBTRN02C-constant-718-445` | Existing acceptance reference; no new count | Twin only; no new z/OS scope | — |
| 34 | `CBTRN02C-constant-718-446` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 35 | `CBTRN02C-delete-MOVE-209-47` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | REWRITE-109 |
| 36 | `CBTRN02C-delete-MOVE-557-314` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | REWRITE-109 |
| 37 | `CBTRN02C-delete-MOVE-709-434` | Accepted; source/register bindings apply | Twin, host-only | — |
| 38 | `CBTRN02C-delete-MOVE-718-447` | Existing acceptance reference; no new count | Twin, host-only | — |
| 39 | `CBTRN02C-delete-MOVE-723-450` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 40 | `CBTRN02C-receiving-scale-142-14` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 41 | `CBTRN02C-receiving-scale-148-18` | Accepted; source/register bindings apply | Twin, host-only | — |
| 42 | `CBTRN02C-receiving-scale-173-20` | Accepted; waits for 200/200 receipt | Twin only; no new z/OS scope | — |
| 43 | `CBTRN02C-receiving-scale-187-28` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 44 | `CBTRN02C-receiving-size-134-7` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 45 | `CBTRN02C-receiving-size-147-15` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 46 | `CBTRN02C-receiving-size-148-17` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |
| 47 | `CBTRN02C-rounded-403-196` | Accepted; source/register bindings apply | Twin only; no new z/OS scope | — |

## Seven accepted INTCALC constants

Each decision is invalidated by a source hash or bound-line change. Full line text and individual SHA-256s are in the JSON. The whole `spec/mainframe/public-source/CBACT04C.cbl` LF SHA-256 is `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`. Declared constants still participate in output comparisons: changing a literal remains detectable; acceptance does not waive mutation detection.

| Field | Source line | Constant | Reason |
|---|---:|---|---|
| `TRANSACT:TRAN-RECORD.TRAN-TYPE-CD` | 482 | `01` | Unconditional literal assignment for each generated interest transaction. |
| `TRANSACT:TRAN-RECORD.TRAN-CAT-CD` | 483 | `05` | Unconditional literal assignment for each generated interest transaction. |
| `TRANSACT:TRAN-RECORD.TRAN-SOURCE` | 484 | `System` | Unconditional literal assignment for each generated interest transaction. |
| `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID` | 491 | `0` | Unconditional literal assignment for each generated interest transaction. |
| `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME` | 492 | `SPACES` | Unconditional literal assignment for each generated interest transaction. |
| `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY` | 493 | `SPACES` | Unconditional literal assignment for each generated interest transaction. |
| `TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP` | 494 | `SPACES` | Unconditional literal assignment for each generated interest transaction. |

## Validation and conditional approval

`python -B tools/check_oct12_operator_review.py` validates attachment/packet/source/line hashes, unique IDs, historical references, pending evidence conditions, host-only scopes, register dependencies, constant bindings and the original proposal plus its conditional approval. Eight offline regression tests passed. The checker deliberately refuses to treat an unverified receipt or amended pending flag as effective; later evidence reconciliation must verify the actual case/shard bytes first.

[Duplicate-category scoped proposal](intcalc-duplicate-category-proposal-2026-10-12.md) was separately approved by Howard on October 12 ([approval record](intcalc-duplicate-category-approval-2026-10-12.json)). Its fresh-evidence conditions remain unmet; no classifier change is activated.
