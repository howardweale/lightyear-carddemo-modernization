# Decidability instrument

The instrument answers **how much can this gate decide on this corpus, what prevents
it deciding the rest, and what would a proposed rule affect?** It runs locally,
reads source files or recorded observations, and produces a portable HTML report,
complete JSON evidence, a Markdown report and draft normalization proposals.

Decidability counts both equivalent and divergent results. A detected defect is a
decision. A high decision rate does not mean a high pass rate, whole-application
equivalence, production readiness or that an engagement should proceed.

## Quick start

From a checkout with `PYTHONPATH=src`, use `python -m lightyear_calibration`.
An installed package also provides `lightyear-calibrate`.

```bash
# An unfamiliar synthetic SQL corpus, including a missing target file.
python -m lightyear_calibration scan \
  --manifest spec/calibration/sql/corpus.json \
  --output work/calibration/orders-baseline

# Account for the real, retained iDempiere gate results.
# This imports prior evidence; it does not pretend to re-execute that estate.
python -m lightyear_calibration import-idempiere \
  --report factory/idempiere-divergence-audit/stage2-comparison.json \
  --pairing-manifest factory/idempiere-divergence-audit/pairing-manifest.json \
  --output work/calibration/idempiere-baseline
```

Open `index.html` in the output directory. `report.json` contains every unit-range
record, cause, disjoint cluster membership and proposal scope. `proposals.json`
contains editable draft entries. Reports contain file references, hashes, reason
codes and verdicts, not copies of SQL or customer observation values. File and
case names may themselves be sensitive, so use appropriate output storage.

## Point the gate at a new corpus

```bash
python -m lightyear_calibration discover \
  --source /customer/oracle-sql --target /customer/postgresql-sql \
  --adapter oracle-postgresql-sql --corpus-id customer-pilot \
  --output work/calibration/customer-corpus.json

python -m lightyear_calibration scan \
  --manifest work/calibration/customer-corpus.json \
  --minimum-decidability 0.70 \
  --output work/calibration/customer-baseline
```

The `0.70` value is an illustrative operator-selected threshold, not a recommended
acceptance standard. Without an explicit threshold, the report records
`not-configured`. An unmet threshold still produces the full report and returns
exit code 3, so an automated pilot-preparation process can stop and request work
before an external demonstration. Zero comparable units never become 100%.

Discovery pairs eligible files by relative path and retains unmatched files.
Inspect the generated manifest and change pairings when customer knowledge calls
for it. Scanning requires each eligible file in both roots exactly once. Dropping
an inconvenient case, duplicating a file, adding a file after discovery, unsafe
relative paths and symbolic links fail admission. Keep manifests and reports
outside input roots. Roots in a hand-authored manifest resolve relative to the
manifest file; generated manifests use absolute root paths.

The built-in adapters are:

| Adapter | Input | Actual comparison | Boundary |
| --- | --- | --- | --- |
| `oracle-postgresql-sql` | Paired UTF-8 `.sql` files | Existing ordered declared-effect comparator | Static SQL projection, not runtime behavior |
| `transfer-observations` | Paired captured `.json` files | Existing transfer qualification admission, normalization and comparison gate | Its documented accounts/operations/outcomes protocol only |
| `import-idempiere` command | Complete retained comparison and pairing manifest | Integrity and complete accounting of the prior gate run | No fresh source replay or evidence authentication |

The runtime adapter reads already captured files. It has no credentials or
invocation client. A new vendor's unsupported format stays indeterminate until
an explicit adapter or comparator change supports it. This feature does not infer
universal service, mainframe or database coverage from the two available adapters.

Other file extensions are explicitly inventoried as excluded. The 1.4-million-line
application estate is not the denominator for a scan of its SQL migration files.
Reports distinguish all input statements, administrative exclusions, in-scope
SQL statements and whole file pairs. Opaque procedural blocks count as a single
unsupported unit under the existing parser, not as individually understood lines.

## Cause accounting and priorities

Every unresolved record belongs to one disjoint cluster keyed by status,
construct kind and its complete set of reason codes. Every cluster retains all
member references. HTML shows up to five examples per cluster; JSON contains all
members with paths, line ranges and source hashes.

A second view groups by individual cause. A unit can appear under several causes,
so those counts must not be added as if independent. The report distinguishes:

- Representation/domain policies that merit a normalization proposal.
- Parser or adapter gaps that need implementation and conformance tests.
- Missing or unmatched source/target evidence.
- Alignment problems.
- Missing schema, session, trigger, catalog or runtime semantics.
- New, unrecognized causes requiring investigation.

No generative model runs. Proposal hypotheses come from a bounded cause catalog;
new reasons never inherit a permissive normalization. Ordering by affected units
helps find concentrated work, but does not estimate economic value or likely lift.

## Proposals and blast radius

Each proposed entry binds to the exact corpus and gate identity. It contains a
hypothesis, explicit construct/lane selectors, required evidence, unassigned owner
and review date, and `status: draft` / `executable: false`. It cannot be passed off
as an approved entry in an existing normalization ledger. This instrument neither
changes a ledger nor supplies the signed human authority required by existing
application paths.

For each proposal, the instrument computes:

- Every scoped record and case, including already decided and divergent units.
- The unresolved units that exhibit the addressed cause.
- Other unresolved units the same selector would touch.
- Co-occurring blockers that remain after considering the addressed cause.
- Units with no other **recorded** blocker, explicitly not a forecast of gain.

The default proposal selector includes every current case with the affected kinds
and lanes. This is deliberately visible as a broad draft. Narrow `case_ids` to a
reviewed set and reassess rather than assuming that all similarly shaped customer
fields have the same meaning. Unknown selector values and wildcards are refused.
All scopes are local to the bound corpus; no radius beyond that corpus is claimed.

```bash
# Extract one entry from proposals.json into proposed-entry.json, then edit its
# selector.case_ids, owner and review_after as appropriate. None of these fields
# constitutes approval.
python -m lightyear_calibration assess \
  --report work/calibration/customer-baseline/report.json \
  --proposal work/calibration/proposed-entry.json \
  --output work/calibration/proposed-entry-assessment.json
```

`assess` recomputes rather than trusts supplied counts. It rejects stale corpus or
gate bindings, executable/approved entries, rules purporting to solve parser or
missing-evidence gaps, and selectors with no matching unresolved evidence. It
never transforms inputs or predicts a new verdict.

## Close the calibration loop

1. Scan the complete pilot corpus before promising a useful decision rate.
2. Inspect the largest causes and representative source ranges.
3. Narrow a proposal, collect domain evidence and negative counterexamples, and
   obtain the required review through the applicable governance process.
4. Separately implement and qualify the comparator/parser/normalization change.
5. Rerun the same manifest into a new directory.
6. Compare the actual before/after reports.

```bash
python -m lightyear_calibration compare \
  --before work/calibration/customer-baseline/report.json \
  --after work/calibration/customer-rerun/report.json \
  --output work/calibration/customer-change.json
```

Comparison requires the identical corpus fingerprint and complete case set. A
changed customer corpus starts a new baseline. The result retains both summaries,
case and unit transitions, newly decided cases, decisions lost, and divergences no
longer reported. Losing a divergent unit triggers review even if another divergent
unit keeps the containing case's verdict unchanged.

Parser changes can alter statement boundaries. The comparison exposes denominator
and unit-partition changes and withholds a unit-fraction delta when unit identities
cannot be aligned. Case transitions remain available. A change in decision rate is
not automatically attributable to one normalization, and no report comparison
approves a rule or alters a verdict.

## Evidence and limits

Content hashes bind corpus contents, pairing, gate implementation/policy, proposal
terms and reports. They detect changes, not source authenticity or customer
approval. Retained imports preserve the original gate bindings. Both fresh and
retained reports say exactly what evidence mode produced them.

The CLI returns 0 for a completed report or valid comparison, 2 for admission or
validation failure, and 3 for a below-threshold/no-units result or a comparison
requiring regression review. A 0 exit status never means that all cases passed.

Inputs are bounded to 20,000 cases, 16 MiB per UTF-8 input file, 512 MiB per corpus,
500,000 range records and 5 million counted units. JSON documents and generated
JSON reports are bounded to 64 MiB. Exceeding a bound fails instead of publishing
silently truncated coverage. Output paths must be new, and original evidence and
customer inputs remain unchanged.

## Validation

```bash
PYTHONPATH=src python -m unittest tests.test_decidability -v
python -m lightyear_calibration validate work/calibration/customer-baseline/report.json
```

Tests exercise the retained 1,078-pair iDempiere baseline, an unfamiliar 5%-decidable
corpus, real SQL and recorded-runtime gates, missing files, overlapping blockers,
collateral decisions in proposal scopes, escaped HTML, stale proposals, forged
counts, unit partition changes and lost divergence detection. These are local
product tests and retained-evidence calibration, not a new customer or native
runtime qualification.
