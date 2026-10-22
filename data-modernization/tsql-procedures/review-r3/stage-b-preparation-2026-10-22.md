# R3 Stage B preparation — 22 October 2026

This is a preparation record, not a measurement. The original **86/86 expected
outcomes across 108 native pairs was measured with the earlier parser**. Whether
it holds under pglast 7.20 is not yet established. The 108 pairs are not 108
equivalence certificates.

The revision-9 source remains the retained export described in
[`docs/tsql-r9-export.md`](../../../docs/tsql-r9-export.md). Howard must publish
the reviewed export as public Release `tsql-r9-evidence-2026-10-21` and post its
tag, asset name `tsql-r9-evidence-2026-10-21.zip`, and full SHA-256 on
[PR423](https://github.com/howardweale/lightyear-carddemo-modernization/pull/423).
No export has been consumed for this preparation. No VM action is authorized
or performed by this job.

## Acquisition and immutable bindings

The workflow accepts Howard's PR423 comment ID and posted ZIP digest. Before
downloading it verifies the commenter, PR, tag, asset name and digest; requires
a public, non-prerelease Release; and records the exact asset IDs, URLs, sizes
and GitHub SHA-256 values. It downloads only the ZIP and `export-manifest.json`.
No download credentials are sent. A mismatched digest, incomplete upload or
ambiguous asset refuses acquisition.

The ZIP must contain exactly `revision-9/<original path>` entries: 1,889 signed
report files plus `report.json`, for 1,890 packaged files. Bounded sizes, regular
files, uncompressed members, unique safe paths and every individual digest are
verified before the existing export inspector authenticates all signatures,
file closure and pair links. The fixed bindings are:

- Report content SHA-256:
  `97116694c110465c639180a79b3ba3512d44566a49b529d8f24ce7713e69e2ef`.
- Recorder public-key SHA-256:
  `f65a408bc46828860fd140518486734879fa9c35aacf2366000e0b1477ae3864`.

These are the existing exporter's bindings, not new expected outcomes. The
original receipts, captured source and target observations, saved comparisons,
expected results and README remain unchanged. Archive code is never imported.

## Offline comparison and acceptance

The replay process requires exactly pglast 7.20. A process audit hook refuses
socket and subprocess operations during replay. It uses the existing revision-9
comparator and contract functions; it starts no database, container or model.

Each signed progress record, pair manifest, input hash, saved replay, original
outcome, coverage qualification and captured procedure/setup binding is checked.
Every authenticated pair gets a JSON report with its identity and manifest hash.
Successful recomputation retains both complete comparisons and all structural
differences, explicitly including outcome and contract changes. Parser or
comparator refusal is recorded for that pair, with any independently computed
contracts, and does not silently omit later pairs. Authentication failures abort
because unauthenticated inputs cannot support a comparison.

The summary requires 108 unique pairs and binds every report hash, source-file
hashes, checkout commit, CI run/attempt, acquisition receipt and UTC measurement
time. If any pair changes or refuses, the run fails acceptance while preserving
its reports. Only when every pair is unchanged does it invoke the original
comprehensive offline audit without modifying its expectations. That audit must
also reproduce the original M0 acceptance and qualification before the summary
may say that 86/86 holds under pglast 7.20.

Synthetic CI covers public-post refusal, exact signed archive round trips,
changed outer/inner hashes, extra/duplicate/linked/traversal members, bad
signatures, structural differences, actual pglast contract parsing, independent
contract/refusal reporting, all-108 continuation, original-audit refusal and
the network/process boundary. Synthetic signatures are disposable test evidence.
They confer no production authority. No tests ran locally for this preparation.

## After Howard posts the export

After this PR is merged with Howard's exact-head approval, dispatch
`.github/workflows/tsql-r9-reverification.yml` on protected `main`, supplying the
posted comment ID and digest. The dispatch guard allows retained replay only
on `main`; PR and push runs use synthetic fixtures only.

Review the actual run, all per-pair files and summary independently. Retain the
artifact's exact run/attempt, checkout, asset identities, ZIP and report hashes.
Publish an **additive, newly dated result** beside this preparation record in a
separate reviewed change. If anything differs, enumerate it pair by pair;
never edit expected outcomes to obtain a pass. Until that result exists, keep
the earlier-parser qualification on every 86/86 claim. Nothing here authorizes
signing, a fresh native run, installation, release approval or model spending.
