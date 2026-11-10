# Public CardDemo fixed-record dataset comparison

Planned draft utility for POSTTRAN, INTCALC and TRANREPT. It does not run those
programs or produce an equivalence, admission or P5 receipt.

The source binding is the public AWS CardDemo revision recorded in the
[fixture provenance manifest](../../tests/fixtures/carddemo-dataset-diff/public-data.json)
and enforced by the module UPSTREAM constant. That is an external repository
revision, not a commit in this factory repository. The manifest retains the full
upstream revision, original blob IDs, SHA256 hashes and slice boundaries.
The existing strict decoder and copybook/JCL bindings remain unchanged.
The new `lightyear_mainframe.public_dataset_diff` module provides:

- `decode_dataset(job, step, dd, raw_bytes, codec=...)`: fixed-record framing,
  exact decimal strings, field offsets, raw hex and hashes.
- `compare_dataset(job, step, dd, before_bytes, after_bytes, codec=...)`:
  added/deleted/changed keyed records, field values and raw-byte differences,
  order changes and separate whole-file byte identity.
- `compare_snapshots(job, before_map, after_map, codec=...)`: maps keyed by
  `(step, DD)`, with exactly the same explicitly supplied inventory on both sides.
  Missing input is refused; an explicitly empty byte string means an empty dataset.

For account records use POSTTRAN/STEP15/ACCTFILE or INTCALC/STEP15/ACCTFILE.
Daily transactions use POSTTRAN/STEP15/DALYTRAN; transaction outputs use
INTCALC/STEP15/TRANSACT. TRANREPT/STEP10R/TRANREPT is positional FB133 text.
Other public DD names come from the pinned binding table; no guessed aliases.
cp037, cp500 or cp1140 must be explicit. No RDW/BDW or line-separator guessing.
Filler, trailing blanks, timestamp bytes and zoned-sign encodings are retained.
A reorder can preserve keyed contents while changing byte identity. This is
reported, never silently treated as identical. Duplicate keys refuse comparison.
A detail cap omits detail rows explicitly while retaining complete counts.
Only supplied datasets are compared; this is not a complete job output inventory.

CI-only tests use unchanged public account/xref data already vendored with
provenance, five additional small pinned public files, and the first two
unchanged records of the public daily-transaction file. The fixture manifest
records original Git blobs, SHA256 hashes and the exact slice offset/length.
The public INIT transaction file contains invalid numeric business fields and
must be refused, not treated as a successful decode. Mutation tests alter public
fixture bytes only. The FB133 report test embeds a public transaction-type label
in an explicitly synthetic padded record; it is not an observed report output.
Upstream data licensing is retained in
`spec/modernization/carddemo-data/upstream/LICENSE`.

CI must verify known account values, all three job bindings, before/after field
changes, filler and sign representation changes, adds/deletes/reorders, duplicate
keys, truncated records, invalid digits, explicit codec/binding errors and
truncated detail reporting. No local tests, apps or compilers are authorized.
No Maintec data, private input or `work/mainframe/arrivals/` is needed or permitted
for this work. Real z/OS execution, program equivalence and qualification remain
outside this draft; `qualified=false` and `production_controller_receipt=false`.
