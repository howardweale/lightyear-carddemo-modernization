# Public CardDemo evidence retention

E3 retains proof bytes in GitHub Releases. Existing dated evidence stays intact.
`required-ci` refuses new or changed files over 5,000,000 bytes and new ZIP or
`mutations.xml` blobs outside `docs/milestones/`. The size ceiling also applies
inside milestones. Unchanged historical blobs are grandfathered. Eight exact
pre-policy PR402 blobs have a path/blob/size inventory bound to commit
`37332f3d9d694387960ca0595acf7fdb2918224a`; this is not a future path exemption.

After a successful **CardDemo web slice** run, the trusted default-branch
`carddemo-proof-retention.yml` workflow verifies the six jobs and seven declared
public artifacts. It preserves the original ZIP bytes and separately retains
`pit-reports/mutations.xml` from the mutation archive. It never checks out the
proof PR or executes artifact contents. Fork/private/non-CardDemo runs are refused.

The prerelease tag is `evidence-<measurement-date>-carddemo-run<run-id>`, bound to
the source head. Existing names must match exact bytes; there is no clobber or
retag operation. Completed releases are reverified using small metadata and
GitHub digests without downloading the original archives again.

The publication artifact contains only two JSON files, each under 50 KB:
- `evidence-retention-<date>-carddemo-run<id>.json`, using the existing INTCALC
  `public-evidence-retention/1` schema: asset names, bytes, SHA-256s and URLs;
- `carddemo-proof-summary-<date>-run<id>.json`, bound to the manifest and run,
  including raw mutation totals with no timeout credit.

Copy those exact CI-generated files into `docs/factory/` and `docs/modernization/`
respectively in the next receipt PR. Commit no ZIP or full mutation report.
The workflow opens no PR and writes no main commit, preserving the WIP limit and
exact-head approval process. Retention is unsigned and grants no merge, signing,
activation or execution authority. First deployed retention and the next receipt
publication remain acceptance checks after this workflow is approved and merged.
