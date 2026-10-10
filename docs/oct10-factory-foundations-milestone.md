# October 10, 2026: factory foundations delivery

This milestone records the B07 design selection, public GnuCOBOL twin and
INTCALC three-way reconciliation delivered from SPEC-factory-sota-upgrades.
Howard authorized pushing, opening and merging these reviewed deliverables.
This is an engineering milestone; no qualification, measurement or production
release credit is claimed.

## Delivered scope

| PR | Deliverable | Verified result |
|---|---|---|
| [304](https://github.com/howardweale/lightyear-carddemo-modernization/pull/304) | B07 graph and plain-search draft | Two new arms, each compared with historical B06; no fresh curated-context arm selected |
| [305](https://github.com/howardweale/lightyear-carddemo-modernization/pull/305) | Public GnuCOBOL executable twin | Ten binaries identical across two clean builds; five public scenarios executed |
| [306](https://github.com/howardweale/lightyear-carddemo-modernization/pull/306) | INTCALC COBOL/Python/Java reconciliation | Eighteen exact pair/dataset comparisons across three successful scenarios; matching expected refusal for missing default disclosure |

The twin executes unchanged public AWS CardDemo INTCALC and POSTTRAN source at
commit `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`. Original business source,
copybooks and license are retained and hash checked. Linux adapters provide
indexed-file loading, linkage and controlled clocks. Receipts bind source,
compiler, flags, helper and binary hashes. Their engineering classification
prevents admission as qualification evidence.

The reconciliation executes the actual Python reference and Java service against
the same before-images as COBOL. Both keyed field comparisons and raw output
hashes must match; timestamps, signs, filler and record order are not ignored.
The Java harness uses an inert Service annotation and does not test Spring wiring.
POSTTRAN currently has no independent Python/Java implementations: its 262 posted
and 38 rejected records (RC4) are twin-only observations.

## Acceptance evidence

- [Twin acceptance 38089424966](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38089424966): Ubuntu 24.04, eight focused tests, two clean builds and five public executions. Tested implementation `cfe6df2266e1da2c64e6b9332f5ec89f24106828`; acceptance seal `69bb7ed864d478cb4adb21b4968d60b7405e591c9abe45a63ede482f54806ca5`.
- [Reconciliation acceptance 38089428759](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38089428759): eight focused tests, actual COBOL/Python/Java executions, twelve scalar platform assertions and exact signed packed-decimal bytes. Tested implementation `413014469a75bc927d89f105ae72a0f3fb06b4da`; report seal `64da40dfba1d61c358f64b152644058c75cf6845435804e31872491712d18592`.

The final implementation PR heads add milestone/results documents to those tested
code bytes. Detailed receipts and source/output hashes are in
[the twin result](factory/gnucobol-twin-result.json) and
[the reconciliation result](factory/three-way-reconciliation-result.json).

## Failures retained and corrected

Initial clean builds differed because GnuCOBOL 3.1.2 included compilation time;
SOURCE_DATE_EPOCH alone was insufficient. Compiler-only libfaketime fixed that
clock. An intermediate build still differed in GNU build IDs, resolved using
`-Wl,--build-id=none` at link time. Final binary equality compares raw files;
there is no after-build normalization.

The first reconciliation found transaction timestamp differences because the
fixture clock omitted fractional seconds. Pinning the complete clock fixed the
adapter; neither the business source nor comparison policy was weakened.
A separate probe confused numeric DISPLAY rendering with zoned storage; it now
asserts both independently. Original failed hosted runs and their artifacts are
retained and linked in the implementation milestones.

## Boundaries and remaining milestones

- INTCALC decision coverage: prior baseline 16/47 (34.04%); no new coverage measurement is claimed. Instrumentation and generators remain next work.
- Twin versus reference: zero remaining differences in the three exercised INTCALC success cases, plus matching expected missing-disclosure refusal. This does not establish agreement on unexercised paths.
- Legacy mutant kill rate: not newly measured by this delivery.
- Multipass acceptance is outstanding because the runtime was unavailable. Reproducibility is established within the recorded Ubuntu toolchain, not across arbitrary toolchains.
- z/OS equivalence remains unknown for every platform probe; no authorized Enterprise COBOL baseline was executed.
- POSTTRAN independent implementations, CICS harness, oracle promotion, coverage thresholds, parallel candidates, production and shadow modes remain outside this delivery.
- The selected B07 draft still requires complete B06 evidence, coverage/audit and sealing gates, plus explicit model/native budget authorization. Its full serial run budget exceeds the older 96-hour cap; that discrepancy is explicit and unresolved, with no implicit extension.

B06 sealed checkouts, signed evidence, historical failures and execution approvals
were untouched. No local Docker, model calls, private intake or machine changes
were needed for this delivery. This report is operator review, not independent
attestation.

## Merge record

All three PRs were merged into main on October 10, 2026. PR #306 was retargeted
from the twin branch to main after #305 merged; its approved head was unchanged.

| PR | Approved head | Main merge commit | Merged UTC |
|---|---|---|---|
| #304 | `aa517d666a993008a97894341802c7fcd29b9a28` | `37e06a64f3ee8b63323dbd652ccb0fd7ac45c0cc` | 22:05:24 |
| #305 | `43803a37f919d2fbf07f94b6d40f4c6b00229d72` | `6a86be0829756c3cd2ad1d83e8d787a5843957b2` | 22:05:27 |
| #306 | `dad67415f2f70cac26b5c6ecb4ae6d4c25a62eaf` | `f52db5eed5aac70d94833dad5e9e96546a9fd169` | 22:05:40 |

Dedicated acceptance also passed on the final heads:
[twin run 38089657503](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38089657503)
and [reconciliation run 38089659887](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38089659887).
Broader repository checks were still queued or running when these merges were
performed; no completed failing check was observed. This record does not claim
that every repository workflow had finished or passed. No branch rule or check
configuration was bypassed or weakened.

Post-merge verification matched all 14 delivered files to their approved Git blobs.
All 16 focused twin/reconciliation tests passed on the merged tree in 0.126 seconds.
