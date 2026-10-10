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

## Integration completed October 10

All five implementation PRs are merged into main. This closes the pending status
above; the dated publication record and original evidence remain preserved.

| PR | Verified implementation head | Hosted checks passed | Main merge commit |
|---|---|---:|---|
| #297 | `30270812cdf771b53f82c3c842539891745dd5e4` | 23 | `6ad6ef93bd55032ba1db04823038e142dea96742` |
| #298 | `e0d409e539292628fdd4e6c1a0c88e927053bb36` | 26 | `0512c05440e81367a44af8f1cffdcdcd89926b4d` |
| #299 | `45d4b55d2189ee59617fb60c28d351efc387c780` | 26 | `429bc8d0b46e9a45863368aba63d40ceec74d0a0` |
| #300 | `522e23ed4ad1104ed1e9ca53443c0318e3078ebf` | 25 | `6c45c790ce13c2cff767c99dc7bc98627b9c6cb1` |
| #301 | `f2235be508f250d8f2dbc33cc17cf4ea3f6a173f` | 29 | `85e355f863fe2cd3497e4ad4c1c2d4214e3b4037` |

The 129 checks include Linux and Windows differential verification. After #297
and #299 merged, #300 required a `.gitattributes` conflict resolution. Commit
`07d62103e9849bb7640930bcea06cd8db2794d97` retains both sets of exact-byte fixture
rules. Every incoming file was checked against the already verified main Git blob;
no implementation code was manually changed. Fifty focused rules, saved-evidence,
build-once and CI-wrapper tests passed in 5.515 seconds on the resolved tree.
The table's 25 hosted checks describe the pre-resolution #300 implementation head,
not the newly queued run on that integration commit. #301's clean integration was
likewise checked against exact main blobs and its fully green head.

The browser failure came from corrupted UTF-8 punctuation in the decision-console
JavaScript. Correcting those characters made the unchanged repeated-cause assertion
pass locally and in [hosted browser inspection](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38083945949).
The public fixture and evidence-strength classification were not weakened.

The earlier Docker exit 125 did not retain daemon stderr, so its initiating cause
remains unproven. Both PostgreSQL CI paths now explicitly acquire the same official
ECR digest, retry only recognized transient acquisition failures, and run with
`--pull=never`. Permanent failures, container startup and workload assertions are
not retried. The repaired [source-build and SQL-recovery jobs](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38084084989)
passed. No image pin or runtime/test semantics changed.

The completeness, diagnostic-only archive and engineering-boundary integrations
retain zero-credit behavior. All work used isolated integration checkouts. No
sealed B06 checkout, native capture, Tower decision or approval was changed, and
no Docker/native workload was launched locally. The native engineering adapter
remains unproven; merging it does not execute the separately approved October 11
engineering window. B07's prior preparation-only status is unchanged.
