# CMS F0 fresh CI observation — 17 October 2026

**NO-GO for cross-language payment equivalence.** This observation closes only the fresh-harness-evidence item in [the retained feasibility report](feasibility-ipps-fy2021.md). Its historical measurements, field-name inventory and estimates are unchanged.

Authorized by Howard; performed by Codex. [CI run 39047679905](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/39047679905) ran evidence head `b700a8740c6a5595a523efb787fdcfc6e2dd9fda`. These measurements belong to that head; a later publication commit must earn its own CI result.

| Gate | Observed result |
|---|---|
| Program inventory | 59 programs, inventory matched |
| Compiled | 51/59 |
| Known compile limitations | 8; not successful compilations |
| Unexpected failures | 0 |
| Dialect attempts | 75 |
| Completed generated calls | 5/5 |
| Captured fields | 377 per case |
| Input-byte checks | 225/225 |
| Source, raw logs and payment values uploaded | None |

The [paired JSON](feasibility-ipps-fy2021-ci-2026-10-17.json) preserves the already-public count/hash receipt so it outlives the artifact expiry on 2026-10-31T16:18:17Z. Artifact ZIP SHA-256: `4b868153ec4e3f905b91aab26a6a04d22baaa81c13d4c68f47bd3507b54f89fd`. Original receipt SHA-256: `d86502b0a0a2f5975871f7f2dc78173cae524ccb744325ae03428a778a24a665`. The JSON includes the exact source/driver/layout hashes, compile-limit identities and diagnostic hashes, without their source text or pricing output.

The COBOL FY2021.5 / Java FY2021.6 gap remains unresolved. The retained five comparisons still have seven differences, twenty-seven Java nulls and four unmapped outputs per case. There was no new matched-version comparison in this run. F1–F4 remain required; their original estimates and scope are in the retained report.

No local suite, CMS execution, real signing, activation, attempt consumption or Phase 2 execution was performed while preparing this observation. All reported execution occurred in CI. This record grants no release authority.
