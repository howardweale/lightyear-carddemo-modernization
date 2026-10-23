# Factory current status — 2026-10-17

## Completed merges and main CI

CI snapshot checked at 2026-10-17T13:10:22+00:00. Evidence measurements below retain their dated scope (2026-10-17).

| PR | Merge commit | Merged at (UTC) |
| --- | --- | --- |
| [#353](https://github.com/howardweale/lightyear-carddemo-modernization/pull/353) | `62e705d959d34041eb42a20388bbbf06b2425cba` | 2026-10-17T00:25:34Z |
| [#341](https://github.com/howardweale/lightyear-carddemo-modernization/pull/341) | `0e5ea5f66fe42cd61205fcdce1810f5af0a64539` | 2026-10-17T02:03:57Z |
| [#357](https://github.com/howardweale/lightyear-carddemo-modernization/pull/357) | `f0ac25c338e96309803655d7e6d09f5b29b4e3c1` | 2026-10-17T03:33:50Z |
| [#358](https://github.com/howardweale/lightyear-carddemo-modernization/pull/358) | `7bbdac9112143b283ed2ea376797d42a1b86954d` | 2026-10-17T05:01:54Z |

Main `7bbdac9112143b283ed2ea376797d42a1b86954d`: all 21 observed push workflows and 60/60 check runs completed successfully, including `required-ci` and `documentation-and-lint`.
[Snapshot and full workflow links](delivery-snapshot-2026-10-17.json).
Observed push workflows on this exact main commit only. Equivalence automation and storage workflows are pull-request/manual workflows; their pre-merge results are separate. This snapshot grants no acceptance, signing, execution, release or z/OS authority.

## INTCALC evidence

Factory: activated locally (signed-only); threshold policy not effective.

INTCALC business outcomes 8/8; I/O 85/86; raw mutation kills 308/421.

| Scope | Raw | Projected, pending decisions |
| --- | --- | --- |
| twin | 308/421 | 308/308 |
| zos-facing | 308/421 | 308/421 |

Loader assessments: resolved-by-valid-comparisons: 113.

| Compared field | Distinct values |
| --- | --- |
| ACCTFILE:ACCOUNT-RECORD.ACCT-ACTIVE-STATUS | 2 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-ADDR-ZIP | 3 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CASH-CREDIT-LIMIT | 51 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CREDIT-LIMIT | 51 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CURR-BAL | 58 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CURR-CYC-CREDIT | 5 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-CURR-CYC-DEBIT | 5 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-EXPIRAION-DATE | 51 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-GROUP-ID | 5 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-ID | 50 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-OPEN-DATE | 51 |
| ACCTFILE:ACCOUNT-RECORD.ACCT-REISSUE-DATE | 51 |
| TRANSACT:TRAN-RECORD.TRAN-AMT | 13 |
| TRANSACT:TRAN-RECORD.TRAN-CARD-NUM | 54 |
| TRANSACT:TRAN-RECORD.TRAN-CAT-CD | 1 |
| TRANSACT:TRAN-RECORD.TRAN-DESC | 50 |
| TRANSACT:TRAN-RECORD.TRAN-ID | 52 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY | 1 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID | 1 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME | 1 |
| TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP | 1 |
| TRANSACT:TRAN-RECORD.TRAN-ORIG-TS | 3 |
| TRANSACT:TRAN-RECORD.TRAN-PROC-TS | 3 |
| TRANSACT:TRAN-RECORD.TRAN-SOURCE | 1 |
| TRANSACT:TRAN-RECORD.TRAN-TYPE-CD | 1 |

Diversity deficit: 7 fields.
- TRANSACT:TRAN-RECORD.TRAN-CAT-CD
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ID
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME
- TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP
- TRANSACT:TRAN-RECORD.TRAN-SOURCE
- TRANSACT:TRAN-RECORD.TRAN-TYPE-CD

## POSTTRAN

Not releasable: nine fresh-campaign gaps remain after the effective twin-only October 12 supplement; no new z/OS acceptances.
Business 24/24; I/O 85/86; diversity deficit 0 fields.
twin: 360/370 projected; 10 unresolved.
zos-facing: 360/390 projected; 30 unresolved.

| Phase 2 | Plan seal | Executable commit | Sign and launch by (UTC) | Days remaining |
|---|---|---|---|---:|
| POSTTRAN | `9b199d95ed391319ad45d5e316e95e927f9ad67ccb0a5cd1a53b39d189896f13` | `65bd4cd549067dd3695f4197e495cc15c9473417` | 2026-10-29T14:46:00+00:00 | 12.066 |

Evaluated at 2026-10-17T13:10:22+00:00. Request: [posttran-phase2-authorization-request-2026-10-16.json](posttran-phase2-authorization-request-2026-10-16.json).
More than five days remain before sign-and-launch deadline at snapshot time.
[Operator runbook](posttran-phase2-runbook.md). The window end applies to the reserve launch check as well as signing. The daily deadline workflow uses the real UTC clock; this page is a dated snapshot. Preparation and rehearsal do not authorize execution.

## Durable public evidence

Current retention manifest: [evidence-retention-2026-10-16-posttran.json](evidence-retention-2026-10-16-posttran.json); scheduled download/hash verification applies. Local deletion remains unauthorized.
Current retention manifest: [evidence-retention-2026-10-16.json](evidence-retention-2026-10-16.json); scheduled download/hash verification applies. Local deletion remains unauthorized.
Current retention manifest: [evidence-retention-2026-10-18-intcalc.json](evidence-retention-2026-10-18-intcalc.json); scheduled download/hash verification applies. Local deletion remains unauthorized.
Dated October 14/15 retention statements remain historical; use these manifests for current storage status. [October 17 verification and deletion addendum](retention-inventory-2026-10-17.json); local deletion remains unauthorized.

## CardDemo data slice

500,000 generated records; 372/372 volume browse comparisons; 58/58 byte-key edge comparisons. Migrated IMS adapter: 27/40 corpus cases matched, 13 unsupported. At that data measurement, screen API/browser sessions: 0/0; handler mutation proof and Compose acceptance remain unfinished. [Dated receipt and durable archive](../modernization/carddemo-slice-1-2026-10-17.md). Overall incomplete; no signing, activation, Phase 2 or release authority.

## CardDemo six-screen proof

CI run 39127778944: 120/120 cases and 678/678 API/browser interactions across six programs (666 BMS interactions). Strict mutation: 701/768 KILLED (91.28%); 49 survivors, 17 uncovered and 1 timeout remain in the denominator. [Unsigned receipt and complete retained artifacts](../modernization/carddemo-slice-1-2026-10-18.md). Bounded raw-source reference and disclosed synthetic fixtures; native execution and SQL-error screen equivalence remain unproved. Final publication-head CI and Howard merge approval are separate. No signing, import, activation, Phase 2 or release authority. Acceptance scope: The six recorded work-order proof gates only; not complete platform, error-path, independence, or release acceptance. Open evidence gaps: Missing-detail screen equivalence is not established. SQL error-path screen equivalence is not established. Native CICS, IMS and DB2 behavior is not established. The original reference and candidate share the BMS parser and data-layout codec. Independent readers now cross-check 50 public and 950 disclosed synthetic rows per layout; this does not establish independent end-to-end or native-platform equivalence. IMS authorization rows and the no-change account pair are disclosed synthetic fixtures, not production evidence. Surviving and uncovered mutants remain open; timeouts receive no killed credit. 49 SURVIVED, 17 NO_COVERAGE, 1 TIMED_OUT. [Dated gap addendum](../modernization/carddemo-slice-gaps-2026-10-21.md).

## B06 access

Windows metadata accessible: True. Cleanup records verified: 2/2. Supported preregistered criteria: none. Public-key verification of signed terminal, cleanup and inventory metadata plus four report files. Raw execution artifacts were not reread; their full inventory-byte verification remains the October 13 record. No fresh process or container absence check performed.

## Equivalence evidence still outstanding

#341: merged; #357: merged; #358: merged. Implementation delivery does not import acceptances or complete evidence gates.

Resolved now: **8/227**. **185/227 (81.5%)** is conditional on the two pending class signatures, below the 95% target. Fresh E1 repeats reproduce the preserved totals; they do not add resolutions. [E1 evidence and remaining gates](equivalence-scale-2026-10-16/README.md).

TRANREPT has two compiler identities in 413 sites and zero class matches; generality and reviewer person-minutes remain unmeasured.

Byte storage support is implemented, but whole-program acceptance remains incomplete: zero unsupported constructs, whole-program control/effects, and 1,000 byte-exact differential inputs per program are still required. Storage inspection alone earns no differential credit.

E3 equivalence and all-killed-mutant rejection checks, E4 build comparisons and measured speedup, E5 held-out campaigns, and E6 policy approval remain separate gates. E7 residual grouping does not resolve evidence.

## Other unfinished work

CMS [PR #360](https://github.com/howardweale/lightyear-carddemo-modernization/pull/360) remains a draft F0 feasibility investigation. Same-revision equivalence is not established; publication/merge and F1–F4 need separate authorization.

The Phase 2 request remains unsigned and unexecuted. Final reviewed-checkout readiness verification is still required before any future signing. Public retention verification does not authorize local evidence deletion.

Typed condition support: True. Threshold/3 support: True. Presence of code is not effective policy approval.

## Selected APPL-RESULT contracts

APPL-RESULT selection as of 2026-10-18. Unsigned; no authority inferred.

| Program | Selected contract | Members | Template queue ID | Class proof | Re-review required |
|---|---|---:|---|---|---|
| INTCALC | [intcalc-02-appl-result-class-request-2026-10-17.json](intcalc-02-appl-result-class-request-2026-10-17.json) | 81 | `factory-550f6ed38a9e8863b959b294af3c61cc91c97f11eff17e324a3476d39bed237e` | `e054defd96b168cc73a154fec1492f96c001c91f8c277737c3db78d08ae584a8` | True |
| POSTTRAN | [contract.json](appl-result-signing-2026-10-16/POSTTRAN/contract.json) | 96 | `factory-92c9dab92dfa6db53c1cf72a4784775377a886d81026b67850cbd19f14e806c1` | `13aca947966f508c373d9a1269e4729b744549c6e1fbb32f205a6543dd38a242` | False |

INTCALC position 2 is a template: binding the verified position-1 decision changes its final queue hash. The final bound hash must be checked before import.

INTCALC: Ordered position 2 is the only class request that contributes to request 06; its retained reference census has a different binding from the October 16 human sample packet.
POSTTRAN: No ordered POSTTRAN APPL-RESULT request exists in the inspected committed signing inventories; retain the existing 96-member contract unchanged.

[Current signing guide](appl-result-signing-2026-10-18.md) · [Contract decision addendum](howard-decision-packet-2026-10-18-appl-selection.md)

## Idiomatic Java screen groups

As of 2026-10-18, COSGN00C idiomatic Java passed CI run 39147604819: 120 journeys and 678/678 API/browser interactions. Strict full-scope KILLED/all-generated: 702/769 (91.29%); historical baseline 701/768 (91.28%). SignonService: 19/21 (90.48%); SignonRules: 15/15 (100.00%). Remaining statement-engine programs: COACTVWC, COACTUPC, COPAUS0C, COPAUS1C. Other existing hand-written orchestration: COMEN01C. Open gaps: Missing-detail and SQL-error screen equivalence; Native CICS, IMS and DB2 behavior; Shared BMS parser and data-layout codec; Disclosed synthetic IMS rows and account pair; All surviving, uncovered and timed-out mutants remain in the denominator. No survivor, uncovered mutant or timeout is waived. Final publication CI and merge approval are separate. Unsigned; no signing, import, activation, Phase 2 or release authority.

## Account validation groups

COACTUPC: 12 validation paragraphs in 4 groups; 120 journeys and 678 interactions per API, browser and mutation-reference run. Strict mutation result 882/950 (92.84210526%), KILLED only. Measured source fb6154ae1568a0a67a69861f6ca8d51b1e010a72, run 39293036087; publication 2026-10-19. Whole account screen remains incomplete. Statement engines remain for COACTVWC, COACTUPC, COPAUS0C, COPAUS1C. No merge or execution authority.

Not releasable: Fresh complete caught-mutant evidence required for: TRANSACT:TRAN-RECORD.TRAN-MERCHANT-NAME, TRANSACT:TRAN-RECORD.TRAN-MERCHANT-CITY, TRANSACT:TRAN-RECORD.TRAN-MERCHANT-ZIP. Retained campaign index does not certify complete durable retention. Ordered effective decisions are not recorded in these unsigned inputs. Non-provisional release evidence is not established by this retained engineering campaign.

This is recorded local activation and twin-scoped evidence; it grants no execution, release, or z/OS authority.

[Measured verdict](intcalc-releasability-2026-10-17.md) · [Decision packet](howard-decision-packet-2026-10-17-handoff-refresh.md)
