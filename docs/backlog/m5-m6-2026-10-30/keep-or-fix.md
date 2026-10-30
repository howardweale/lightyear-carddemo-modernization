# M5 keep-or-fix review register

Backlog lane — additive draft, 30 October 2026.

The protected original register remains unchanged. This view adds traceability
to KF-005 without renumbering the four semantic IDs or counting one defect twice.
No behavior-change permission, promotion or gap closure follows from this view.

- [docs/factory/keep-or-fix-register.json](../../../docs/factory/keep-or-fix-register.json) — sha256=d92053ed3ba1d715df87c9a07e640c0f404bee2823a65c6bd9e38775c853a28a

Source default: preserve recorded legacy behavior. A behavior change needs a
separate decision and separately scoped verification.

| Existing semantic ID | Program | Recorded disposition | Behavior-change permission | Source |
| --- | --- | --- | --- | --- |
| REWRITE-109 | CBTRN02C | keep-by-default | fix_authorized=false | [docs/factory/fault-posttran-review311.json](../../../docs/factory/fault-posttran-review311.json) |
| CBACT04C-FINAL-ACCOUNT-EOF-ELSE | CBACT04C | keep-by-default | fix_authorized=false | [docs/factory/io-gap-arguments.json](../../../docs/factory/io-gap-arguments.json) |
| POSTTRAN-DUPLICATE-ID-NONATOMIC | CBTRN02C | keep | fix_authorized=false | [docs/factory/howard-decisions-2026-10-11b.json](../../../docs/factory/howard-decisions-2026-10-11b.json) |
| POSTTRAN-CYCLE-DEBIT-SIGN | CBTRN02C | keep | fix_authorized=false | [docs/factory/howard-decisions-2026-10-11b.json](../../../docs/factory/howard-decisions-2026-10-11b.json) |

## KF-005 — alias/addendum to REWRITE-109

Source: [operator-chat receipt](https://github.com/howardweale/lightyear-carddemo-modernization/issues/436#issuecomment-6449509273).
The public receipt carries operator-chat attribution, not independent identity authentication.

| Field | Recorded position |
| --- | --- |
| Conversion behavior | KEEP source-faithful: reason 109 on account REWRITE INVALID KEY, continue to transaction WRITE, persisted account unchanged, no reject and no abend for this path. |
| Required path comparison | Transaction written, TCATBAL updated, account unchanged, no reject record; twin and candidate must match under controlled fault injection. |
| Promotion blocker | OPEN: posttran-runtime-rewrite-109. The decision text is not fault-path coverage evidence. |
| Recommendation | FIX after cutover, with fatal handling analogous to 2700/2900, only as a separate behavior change with customer sign-off and verification. |
| Current implementation permission | None. No POSTTRAN source, runtime, frozen register or evidence is changed by this draft. |
| Design follow-up | Separate document-only KF-005 draft in the backlog lane; no injection, attempt, signature or run here. |

## Next review

Planned: preserve existing IDs, keep/fix authority and exact original evidence.
Record a new decision additively before any behavior change. A source-faithful
conversion and a post-cutover fix require different acceptance questions.
Planned: retain adverse observations and unresolved blockers in every program page.
Do not treat an argued equivalent mutant, compiler identity or existing scenario
comparison as controlled proof of this unobserved failure path.

Review disposition: [UNFILLED]

