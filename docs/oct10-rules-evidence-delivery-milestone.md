# October 10, 2026 delivery milestone: rules and reusable evidence

Howard authorized publication and merging of the recent PRs on October 10. This
record distinguishes implemented behavior, focused validation, CI and native proof.
It does not grant a new execution window or change historical evidence.

| PR | Delivered behavior | Focused validation | Implementation milestone |
|---|---|---|---|
| [297](https://github.com/howardweale/lightyear-carddemo-modernization/pull/297) | Public rule agreement is separated from discriminating evidence; rule-owned mutations and honest weak/not-assessed labels | 24 tests; two rules discriminating, four weak, four not-assessed | [Rules evidence strength](https://github.com/howardweale/lightyear-carddemo-modernization/blob/c56b17488663e97a0f229083d65db221718cc9e9/docs/business-rules/evidence-strength-milestone.md) |
| [298](https://github.com/howardweale/lightyear-carddemo-modernization/pull/298) | Pure missing-stage and cleanup classification; successful cleanup cannot erase execution failure | 5 generic and 11 unchanged B06 tests | [Evidence completeness](https://github.com/howardweale/lightyear-carddemo-modernization/blob/420d45110b30bb1f1708c62a4580a5676fb031fe/docs/evidence-completeness-milestone.md) |
| [299](https://github.com/howardweale/lightyear-carddemo-modernization/pull/299) | Generic tree/archive identity and per-pass read cache, including standalone worker packaging | 40 focused tests; observer-v2 8 passed / 10 optional evidence skips | [Content identity](https://github.com/howardweale/lightyear-carddemo-modernization/blob/26d9c188798f445d111c2b2e0f8375ef9e110735/docs/evidence-content-identity-milestone.md) |
| [300](https://github.com/howardweale/lightyear-carddemo-modernization/pull/300) | Digest-bound shared build and permitted consumer replacement; saved-output replay without Java | 16 tests; tiny public JVM consumers returned 21 and 35 | [Build once](https://github.com/howardweale/lightyear-carddemo-modernization/blob/c11b135a77ab6f75413f05abad2f3361ce0bdefa/docs/evidence-build-once-milestone.md) |
| [301](https://github.com/howardweale/lightyear-carddemo-modernization/pull/301) | Isolated Oracle-only engineering admission, ten-attempt ledger, bounded lifecycle and rejection from qualification/measurement | 41 mocked/pure focused tests, 2.203 seconds; native adapter not yet proven | [Engineering approval update](b06-engineering-approval-milestone.md) |

The generic contracts provide reusable platform behavior, not retrospective credit
for failed B06 runs. The named next adopters (T-SQL saved execution, Oracle package
inventory and CardDemo build consumers) are proposals; adoption is not included.
The rules fixture is a public reference model, not customer COBOL execution or
independent attestation. Original fixtures, signed receipts and private captures
are preserved. No private intake, raw runtime archive or signing material is published.

## Integration status at publication

PR #291 merged as `ffdd18f018d76f16216046e72cfcfb642451d846` after 25 green checks.
PR #293's implementation had 28 green checks. Its status-document conflict after
#291 was resolved by preserving both dated records, in isolated integration commit
`cad8c466ed768ab73b4850c5b56b8488475a5ebd`; new CI is pending. Sealed execution
checkouts and the historical public commit references remain unchanged.

The newer PRs are published and open. Their exact reviewed commits appear in the
links above. CI is not being reported as wholly green: #297's browser inspection
hit a locator timeout and was rerun; #300's customer-startup Docker command exited
125, and GitHub refused a job rerun while the parent workflow remained active.
Differential-verification jobs are still running on several heads. No failed check
was waived or weakened. The live PR status is authoritative for later merges.

B07 remains preparation-only. Its pinned upstream commit was checked against the
current B06 declaration. Graph coverage proof, runtime coverage, audit and sealing
are not complete; no B07 model or native run is authorized by this milestone.
