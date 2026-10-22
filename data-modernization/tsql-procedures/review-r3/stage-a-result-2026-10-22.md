# R3 Stage A verified public result — 2026-10-22 UTC

**PASS on Windows and Linux with pglast 7.20.** Each OS ran all 128 public regression tests with no failures, errors, skips or expected failures. The corpus contains 43 procedures and 86 correct/wrong target variants. Both parser modules produced 172 contracts per OS; the complete contracts agree across OS, with policy obligations retained in the original reports.

Measurement PR head: `b465240bcedcac9d59d16b6ca3929652d7d03b68`. CI checkout: `8e2b9369f5152b56657086dae70cba15047fc1cf`, the verified merge of that head with main `9dfffd96fd846ab8a5eb3957ab8469aaf6f26487`. [CI run 39696016782, attempt 1](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/39696016782) produced the reports on October 21–22 UTC. This dated result records those measurements; it does not claim that a later documentation commit was their source.

Both artifact ZIP digests, exact two-file inventories, report hashes, all 625 source input hashes, test identities and contract coverage were independently verified. Every measured input also matches the PR head. The adjacent JSON manifest gives each artifact name, ID, URL, ZIP SHA-256, report SHA-256 and note SHA-256. The artifacts retain the full contracts and source manifest for 90 days under the workflow's retention policy.

Stage B remains pending Howard's reviewed export of the retained historical capture archive. This run reverified **zero historical native pairs**. The earlier revision-9 result of **86/86 expected outcomes over 108 native pairs (55 matches, 53 divergences) was measured with the earlier parser**. It is not 108 equivalence certificates, and these public checks do not reissue those historical receipts. Native outcome or contract differences must still be reported pair by pair without adjusting expectations.

CI used no database connections or model calls. Local verification used inert ZIP inspection, Git metadata, static parsing and hashing only; no local tests, installation or startup.

Result manifest SHA-256: `a783afd0324a3dbd8d225ca9f53d1c703d0479cf7ae3991d4e2c783ed5ae8b70`.
