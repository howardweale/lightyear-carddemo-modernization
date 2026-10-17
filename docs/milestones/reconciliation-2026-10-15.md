# Milestone reconciliation October 15 2026

The approved delivery queue is merged. PR #342 landed first; the remaining reviewed heads were combined in PR #352 so GitHub could validate the complete result against current main under its strict branch protection. Every original head remains an ancestor. The only manual integration conflict preserved both exact-byte rules in `.gitattributes`. Integration CI also exposed a stale POSTTRAN plan binding; the repair inspects the retained snapshot at its recorded commit while preserving strict current-file execution refusal.

The integration head was `a4c7c4880949156d64782e20bd0cdc94caa97113`. Its merge commit is `d03dd607624fef39b4dfe6c55ba8014f9df7fc1b`. All required integration checks passed before merge. The original data PRs passed their dedicated data workflows. PR #351 had a Windows broker connection-abort failure, then passed its single bounded Windows retry; its old required-gate rerun refused a changed-file count after the PR was retargeted. That obsolete event is not represented as green. The final combined integration checks are the merge acceptance evidence. The earlier individual release-fix heads had green checks.

## Canonical records

- [MS107 Release safeguards and evidence reconciliation](MS-107/MS-107.md) covers PRs #342 through #349.
- [MS108 CardDemo PostgreSQL data migration proof](MS-108/MS-108.md) covers PRs #350 and #351.

Both records have Markdown, Word and PDF companions. All four rendered pages were visually inspected. The regenerated searchable library contains 106 records and 318 document files. The existing MS71 and MS72 numbering gap is preserved.

## Merge record

| PR | Delivery | Original reviewed head |
|---|---|---|
| [#342](https://github.com/howardweale/lightyear-carddemo-modernization/pull/342) | Enforce threshold conditions before signing and consumption | `ae6fd7bb1f9a` |
| [#343](https://github.com/howardweale/lightyear-carddemo-modernization/pull/343) | Publish fresh INTCALC loader results and explicit release blockers | `a33be1027271` |
| [#344](https://github.com/howardweale/lightyear-carddemo-modernization/pull/344) | Derive Factory status and packets from current evidence | `cf7ea48ac628` |
| [#345](https://github.com/howardweale/lightyear-carddemo-modernization/pull/345) | Verify signed POSTTRAN approval and image before consuming attempt | `d63d1e8d3081` |
| [#346](https://github.com/howardweale/lightyear-carddemo-modernization/pull/346) | Use explicit claim scopes for independent zOS denominator checks | `4e97c85df838` |
| [#347](https://github.com/howardweale/lightyear-carddemo-modernization/pull/347) | Add pinned-download retries and explicit I/O exception basis | `03bffac80063` |
| [#348](https://github.com/howardweale/lightyear-carddemo-modernization/pull/348) | Record B06 evidence access block and read-only inventory helper | `0bffaa0cfe41` |
| [#349](https://github.com/howardweale/lightyear-carddemo-modernization/pull/349) | Propose explicit threshold3 exemptions for source-assigned constants | `37fe1310364a` |
| [#350](https://github.com/howardweale/lightyear-carddemo-modernization/pull/350) | Generate source-bound CardDemo PostgreSQL data mappings | `a8405b487d89` |
| [#351](https://github.com/howardweale/lightyear-carddemo-modernization/pull/351) | Prove CardDemo PostgreSQL data loading and EBCDIC browse order | `1527dfefe1c4` |

The [machine-readable reconciliation](reconciliation-2026-10-15.json) retains full commit IDs, merge timestamps and source hashes. [Integration PR #352](https://github.com/howardweale/lightyear-carddemo-modernization/pull/352) preserves the component history. The [October 14 reconciliation](reconciliation-2026-10-14.md) and its historical source map remain unchanged.

## Evidence and authority boundaries

INTCALC retains its measured 308/421 raw mutation result. Its projected twin denominator is 308, while its projected z/OS-facing denominator remains 421. The threshold/3 constant exemptions and I/O exception are unsigned proposals, and the revised six-request signing path is still outstanding. No POSTTRAN Phase 2 comparison or native B06 attempt was authorized or run by this closeout. The live Tower runtime and signing state were not changed.

CardDemo data gates passed for 210 records, all five reconciliations and 1560 browse comparisons. Generated IMS fixtures provide only a bounded six-segment result. The overall migration verdict remains indeterminate: public IMS unload, full DL/I, Java API, screens and real z/OS/customer behavior are not proved by these measurements. Original measurement runs and their hashes remain attached to their original source commits.

Large original receipts remain outside Git pending the designated retention store. The Windows B06 evidence folder remains unsearched from this Mac.

## Publication validation

The library manifest binds the source records and every generated document. The documentation PR runs the existing milestone tests in CI; local work is limited to document generation, rendering, source inspection and manifest verification.
