# Oracle evidence roadmap and operator notes

Reporting clarified 2026-09-22. **The published native Oracle 26ai–AlloyDB campaign
passed 260/260 case pairs across 13 datatype families and 65 bounded behaviours.**
CloudBank's application journeys and platform qualification remain separate valid
evidence. The behaviour catalog has 500 bounded-model verified behaviours and
2,000 cases. Its MS51 readiness snapshot does not aggregate the paired receipts;
its zero is not a project-wide native execution count. See the
[evidence and count-scope guide](oracle-native-evidence.md).

The implementation and validation notes below record the earlier 2026-09-17
catalog/readiness increment, not the results of the separate paired campaign.

## Reporting

All five catalog coverage receipt builders now compute `coverage_statement` from
`catalogued_behavior_count`, `bounded_model_verified_behavior_count`, and
`native_oracle_verified_behavior_count`. The field is included in the receipt hash,
required by its schema, printed by the build/verify command, and shown in the generated
coverage matrix. Missing, negative, boolean, or out-of-catalog counts are rejected.

For the latest cumulative catalog result, use:

```powershell
$env:PYTHONPATH = 'src'
py -3.12 -m lightyear_data verify-oracle-schema-structured-coverage --project-root .
```

The resulting sentence describes that bounded-model catalog receipt only:

> This catalog receipt covers 500 catalogued behaviours: 500/500 bounded-model verified and 0/500 native-Oracle verified. These counts exclude separate application-level evidence such as CloudBank runs; they do not establish target equivalence or production readiness.

The foundation receipt still describes its historical eight behaviours. Its new sentence
is scoped to that receipt; use the final schema/structured tranche for current cumulative
bounded coverage. No CloudBank execution receipt was rewritten or re-signed.

## First native family: types/number

The repository now contains 20 case-specific SQL harnesses for each of the two version
lanes: **40 materialized harnesses, one topic family, five behaviours**. The existing
manifest counts case/version harnesses, not family generators. The remaining materialization
scope is 3,960 case/version harnesses. This MS51 readiness snapshot records **0**
native executions; materializing 20 or 40 harnesses does not record a database run.

The implementation probes NUMBER arithmetic, NULL propagation, scale rounding, precision
limits, overflow diagnostics, recovery, and numeric formatting under both NLS decimal
separators. Each case selects the probes required by its catalog focus and dimension.
This is bounded native testing of those concrete examples, not a universal proof of
all NUMBER semantics. One lane's execution cannot establish cross-version agreement.

The SQL emits actual values and SQLCODE, never a hardcoded passed result. The runner
compares them with independent literals, hashes the actual observations and exact SQL,
and binds the result to the existing bounded expectation. All four cases of a behaviour
must pass before that behaviour counts as verified. Missing or duplicate case markers,
changed harnesses, wrong database versions, missing signatures, and mismatched observations
are rejected. A 20-case receipt never claims whole-lane conformance or target equivalence.

The implementation has mock-client and local materialization tests. **Its SQL has not
been executed against Oracle in this change.** At the environment check on 2026-09-17,
Docker Desktop's Linux engine was stopped and the existing `cloudbank-ms67` Kubernetes
namespace returned no pods. The previous 17-feature source-qualification receipt is
bounded synthetic evidence, not evidence that a database is running today.

### Local checks

```powershell
$env:PYTHONPATH = 'src'
py -3.12 -m lightyear_data.oracle_number_native verify --root .
py -3.12 -m lightyear_data verify-oracle-native-execution-gate --project-root .
```

Regenerate the reviewed SQL only when intentionally changing the implementation:

```powershell
py -3.12 -m lightyear_data.oracle_number_native materialize --root .
py -3.12 -m lightyear_data build-oracle-native-execution-gate --project-root .
```

### Authorized database execution

Use an existing authorized Oracle environment, SQL*Plus, a configured external-wallet
alias, and an external `LIGHTYEAR_ORACLE_NATIVE_EVIDENCE_KEY`. Do not put the key or
database credentials in a command, repository file, or receipt. The wallet user needs
SELECT access to `V$INSTANCE`, `V$VERSION`, `V$DATABASE`, `V$OPTION`, NLS parameter views,
and permission to alter its own session. The pilot uses DUAL and anonymous PL/SQL;
it creates no application tables and submits no CloudBank workloads.

```powershell
py -3.12 -m lightyear_data.oracle_number_native run --root . --lane 26ai --wallet-alias NUMBER_PILOT --runner operator-number-pilot --output work/oracle-native/number-26ai.receipt.json
```

Use `--lane 19c` and the corresponding wallet alias for the other version. The runner
publishes a signed receipt only after validating its complete observations. A failed
numeric assertion produces a failed case and a nonzero exit code. Client/identity/marker
failures produce no execution receipt. Existing output receipts are never overwritten.
The runner starts no cloud resources, creates no container, and does not restart GCP.

Oracle 26ai uses `VERSION_FULL` values such as `23.26.1.0.0`; the prior `startswith("26")`
check was incorrect. The pilot requires a 26ai banner and the supported `23.26.x` version
shape, while 19c requires `19.x`. Other releases require an explicit contract review.
See [Oracle release-number documentation](https://docs.oracle.com/en/database/oracle/oracle-database/26/upgrd/oracle-database-release-numbers.html)
and [Oracle NUMBER precision diagnostics](https://docs.oracle.com/en/error-help/db/ora-01438/).

The committed gate is a materialization/readiness snapshot. It does not scan arbitrary
local receipt files or rewrite historical bounded-model receipts. Publish and verify a
real pilot receipt separately; catalog-wide run aggregation and multi-run deduplication
remain future work. Measure actual setup time and case execution time after the first
live run before estimating the other 99 families.

## Planner blast radius and run history

The headless planner reads optional `control-tower/normalization-proposals.json`.
No file means no exact proposal and therefore no measured radius. A proposal must identify
an existing `propose-normalization` action by entity and kind, contain exact human-readable
terms, and explicitly use `comparison-reasons-and-construct-kinds` as its matching basis.

Illustrative format, **not an approved policy or measured result**:

```json
[
  {
    "entity_id": "pair:REPLACE_WITH_AN_ADMITTED_PAIR_ID",
    "kind": "propose-normalization",
    "pattern": "datetime-precision-range-and-zone-policy",
    "match_basis": "comparison-reasons-and-construct-kinds",
    "terms": "Describe the exact proposed normalization and its limits here."
  }
]
```

Run `py -3.12 -m lightyear_workflow emit --root .` to publish a plan. The planner resolves
comparison records against their source pairs before calling `blast_radius`, counts each
pair once across both dialects, and reports both source files. It binds the proposal and
resolved register hashes to the plan. Editing proposals invalidates a previous snapshot.
Patterns match admitted reason codes and construct kinds, not arbitrary SQL text.

The result measures **pattern reach**, not actual suppression or a changed verdict. The
legacy field `suppressed_comparisons` carries that potential pair count only when measured;
it is null when unmeasured. Invalid patterns, invalid registers, empty registers, and a
measured zero remain distinct. Signing stays disabled: a measured radius is one prerequisite,
not authorization. No proposed terms are fabricated from a generic planner question.

MS74 already calls `RunIndex.record()` from the verified halt/history path. No duplicate
recording hook was added. Convergence still reads the index, so journal pruning does not
erase the trend.

## Evidence-floor audit

An evidence class is provenance, not a verdict. A real observation can fail a comparison.
Combining evidence must not promote a simulated or missing input, and different class
vocabularies must not be ranked by alphabetical order or by an invented universal scale.

| Combination boundary inspected | Outcome |
|---|---|
| Batch source/target receipts | Uses shared runtime-class floor; preserves both lane classes; missing reader class remains simulated. |
| Runtime capture envelope and child observations | Explicit child class cannot exceed its capture envelope. An unlabelled envelope defaults to simulated. Labelled producer envelopes remain the default for their own observations, preserving the qualified z/OSMF adapter contract. |
| Runtime graph projections | Mixed evidence uses the weakest confidence, with contradictions still dominant. Snapshot validation re-derives projections so a rehashed inflated confidence is rejected. |
| Runtime mainframe policy | Every required entity needs z/OS-observed evidence and cannot combine a weaker observation for that entity into the same passing claim. |
| CICS/VSAM, IMS, HLASM differential comparisons | Preserve both lane classes and add their floor to comparison/readiness receipts. Invalid captures produce simulated combined provenance and fail comparison. |
| Multi-target data receipt aggregator | Rejects missing/unsupported classes, invalid input hashes and duplicate targets. Never manufactures live provenance from a weaker input; a live failed comparison remains live evidence with a failed verdict. |
| CloudBank whole-application comparison | Already validates both signed observations, pinned runtime/image bindings, complete service/scenario sets and prerequisite receipts before issuing its result. No blanket class relabelling. |
| AlloyDB platform publication | Already verifies its qualification receipt and complete passing scenario set; retained evidence is unchanged. |
| Audit event collections | Preserve the set of per-event classes; no strongest-class reduction. |
| Audit release promotion | A passing mainframe or execution decision can no longer mask another blocked decision in the combined scope. Mainframe decisions also recheck the event-class floor. |
| Graph static/reference paths | Explicitly remain non-runtime and non-customer evidence. Static path descriptions do not become execution qualification. |

This audit covers the combination sites found in the runtime, workflow, readiness, data,
graph and audit modules. It does not assert that a textual provenance label authenticates
an observation: domain-specific identity, signature and admission checks remain necessary.
`src/lightyear_runtime/zosmf.py` is unchanged.

## Validation of this increment

- Full local suite: 1,338 passed, 23 skipped, 673 subtests passed; one Windows
  `WinError 1314` symlink-privilege failure. The same test and failure are present
  in the retained MS77 baseline (1,324 passed, 23 skipped).
- Regenerated CICS/VSAM, IMS, and HLASM reference receipts plus their dependent
  unsigned audit and pilot fixtures. All five readiness/audit/pilot verifiers and
  the source-only rehearsal byte comparisons passed.
- Final focused regression after audit hardening: 69 passed, 24 subtests passed.
  This includes all 18 new roadmap tests.
- UI rendering checks: measured zero, measured nonzero, and invalid/unmeasured
  radius states passed; JavaScript syntax check passed.
- Catalog and native gate verification, planning snapshot verification, runtime
  snapshot verification, milestone documentation verification (210 artifacts),
  and whitespace checks passed.

No native Oracle pilot execution, infrastructure restart, or new platform qualification
is claimed by these local tests.
