# iDempiere Oracle/PostgreSQL divergence audit (IDDA)

IDDA is the MS #68–#70 project stream inside the existing LIGHTYEAR repository. It audits the paired
Oracle and PostgreSQL migration scripts in the already-pinned iDempiere release 13 estate.

| Milestone | Scope | Status |
|---|---|---|
| MS #68 | Inventory, pairing and premise check | Complete |
| MS #69 | Deterministic semantic comparison | Complete bounded baseline; unresolved semantics reported |
| MS #70 | Bounded triage and evidence assembly | Complete bounded safe-floor package; live model run gated |

Customer production readiness, governed cutover and continuous assurance remain future unnumbered
work. Reassigning these milestone numbers does not change earlier signed CloudBank evidence.

The governing execution rule is **deterministic sweep first; models only on the bounded set that
the comparator cannot resolve**. Stages 1 and 2 use no model calls. MS #69's baseline leaves most
SQL unresolved; it does not unlock an unattended model sweep or a whole-migration equivalence claim.

## What Stage 1 established

The exact MS #48 pin, `731515dcdd5278b843db33b9d3109d155b881951`, contains 1,078 current
Oracle migration scripts and 1,078 current PostgreSQL migration scripts: 1,078 candidate pairs,
not 1,078 total files.

- 1,077 pairs match by release segment and filename.
- One pair, `IDEMPIERE-5963`, matches uniquely by release segment and ticket id because its two
  filenames use timestamps one day apart.
- Pairing coverage is 100%; there are no unpaired scripts at this pin.
- 93 pairs lexically reference at least one of the nine tables in the existing order-to-cash slice
  and form the first deterministic pilot set. Stage 1 does not remove comments; Stage 2 parsing
  will distinguish executable references from commentary.
- 31 pairs have identical logical file content. Identity is only a Stage 1 observation, not a
  semantic-equivalence verdict.

The pairing manifest records logical and transport hashes for every file, the pairing reason, the
order-to-cash table matches, and an explicit `not-run` comparison status. It does not copy upstream
source into this repository.

## Correction to the original premise

The repository layout is exceptionally pairable, so pairing is not the weak link at the pinned
commit. Maintenance provenance is the first unresolved question.

iDempiere contains an explicit Oracle-to-PostgreSQL conversion implementation in
`Convert_PostgreSQL.java` and `ConvertMap_PostgreSQL.java`, along with database-specific provider
classes. More decisively, `Convert.logMigrationScript` opens both dialect paths and writes the
Oracle statement and converted PostgreSQL statement into matching migration files. Therefore,
equal file counts and same-commit introduction do not prove that the two dialects were independently
written by hand.

Stage 1 consequently records:

- `conversion_layer_present: true`
- `dual_dialect_migration_log_writer_present: true`
- `independent_parallel_maintenance_proven: false`
- `generated_variants_ruled_out: false`
- `status: history-classification-required`

Stage 2 is consequently an audit of generated-or-maintained dialect output, not an audit of an
independently performed migration. It must not interpret a difference as independent migration
drift until provenance is classified. The bounded nine-file Java conversion boundary is included
deliberately; the remaining Java application source stays out of scope.

## Existing work reused rather than rebuilt

| Existing LIGHTYEAR result | How IDDA uses it | What IDDA does not repeat |
|---|---|---|
| MS #33 database semantic core | Canonical types, five-class compatibility policy, fail-closed decisions | No second semantic core or compatibility vocabulary |
| MS #34 Oracle-to-PostgreSQL proof | Progressive proof shape and separation of schema, data, query, transaction, CDC and stored-logic claims | No reuse of the bounded AUTHFRDS verdict as iDempiere evidence |
| MS #48 iDempiere inventory | Exact release-13 commit/tree, license identity, SQL counts and source-only acquisition boundary | No repinning, source vendoring or repeat estate inventory |
| MS #48/#52 order-to-cash slice | Existing nine-table business scope and operator context | No duplicate graph or Control Tower estate |
| MS #49–#51 Oracle program | Dialect authority, governed behavior catalog and native-execution admission boundary | No new Oracle language corpus or unearned native claim |
| Existing model workcell | 60,000-token input preflight, 25,000-token output ceiling and 80,000-byte role context cap when Stage 3 begins | No model calls during inventory or deterministic comparison |
| Existing factory roles | Planner and Analyst may triage only flagged pairs; deterministic verification owns the verdict | Builder remains idle because this project audits rather than generates |
| MS #54–#67 CloudBank evidence | Potential later destination and infrastructure qualification context | CloudBank execution does not count as iDempiere script-equivalence evidence |

## Governed project stages

### Stage 0 — baseline and premise check (complete)

Bind the existing source pin, inventory, business slice and semantic core. Locate the database
conversion and dual-file logging boundary. Keep each pair's generated-versus-later-edited
provenance unresolved until source history supports a per-pair classification.

### Stage 1 — inventory and pairing (MS #68 complete)

Build the 1,078-pair manifest, retain unpaired files as findings, select the 93-pair order-to-cash
pilot, and publish a content-addressed receipt. The committed receipt proves pairing coverage only.

### Stage 2 — deterministic semantic comparison (MS #69 bounded baseline complete)

The bounded dialect parsers and normalization layer use the existing semantic-core canonical types
and five compatibility classes. They distinguish:

- Oracle `ALTER TABLE ... MODIFY` from PostgreSQL `t_alter_column` helper semantics;
- `NUMBER` precision and scale from `NUMERIC` behavior;
- Oracle empty-string/NULL behavior from PostgreSQL character behavior;
- Oracle `DATE` from PostgreSQL date/timestamp choices;
- defaults, nullability, constraints, indexes and schema-object changes;
- DML effects and explicitly unsupported procedural or session-dependent behavior.

Coverage is the primary output. SQL units are counted as parsed-and-compared,
parsed-but-indeterminate, or unparsed. An unknown construct can never be treated as equivalent.
The order-to-cash pilot runs and is sealed before the remaining 985 pairs. The frozen lexical
pilot membership is retained; the SQL lexer excludes comments from executable units.

The exact admission rules and primary language references are in
[comparison-policy.json](comparison-policy.json). The verdict compares **ordered declared schema
effects**, not final database state or native execution. Equal explicit decimal facets are admitted
only for a bounded finite-number projection; PostgreSQL NaN/infinity and unconstrained numeric
domains are not equated. Character, datetime, index, constraint and catalog-dependent behavior
retains policy obligations. Typed literals are preserved; other expressions are opaque.

`INSERT VALUES`, `UPDATE` assignments and `DELETE` predicates are projected, but DML remains
indeterminate without baseline column domains, trigger and coercion evidence. Unknown statement
forms and procedural blocks remain unparsed. Ordered effect identities must match exactly; the
comparator neither guesses a resynchronization nor collapses repeated writes. Different statement
counts can align only through fully parsed column-effect expansion.

The bounded helper-definition exception is `db/postgresql/functions/altercolumn.sql` at the same
pin. Its five positional arguments are decoded, including the distinction between SQL NULL and
the string 'NULL'. Requested column facets are recorded, while dynamic catalog lookups,
dependent-view recreation, grants, coercion and historical helper deployment remain unresolved.
No historical migrations or additional Java files become comparison targets.

The known `SET DEFINE OFF`, `SET SQLBLANKLINES ON`, and migration-registration call forms are
counted separately and excluded from SQL-effect coverage. All other client/session commands are
unparsed. This policy assumes literal SQL execution and an existing schema-name mapping; it does
not certify SQL*Plus behavior, migration-log side effects, transactions or search paths.

The unit denominator is **statements and opaque blocks on both dialect sides**, not the original
plan's estimated 25,157 lexical occurrences. A lexically malformed file or unterminated Oracle
block can become one opaque remainder unit; unsupported inner statements are not invented.
Adjacent units with the same category/reasons are compacted into source-range segments. Each
segment retains its unit interval, line span and a digest of the ordered unit hashes.

### Stage 3 — bounded triage controls (MS #70 complete)

Only Stage 2 findings enter the work package. The deterministic sampler selects twenty unique
cases: one bilateral-evidence case from the frozen pilot and one from the remaining estate for each
of ten repeated reason strata. Planner bounds the implicated construct; Analyst classifies
deliberate adaptation, cosmetic difference, genuine divergence, or indeterminate. Runtime context
contains only the bound source ranges plus two lines, with a 48-line cap per dialect and an
80,000-byte cap per role.

Each role is limited to twenty calls, 60,000 input tokens and 25,000 output tokens per call. Planner
and Analyst cost ceilings are USD 50 and USD 150. A live OpenAI run must use token preflight and
explicit nonzero pricing. Builder remains unused. A deterministic verifier resolves every cited
evidence id and reason code, preserves the Stage 2 semantic verdict and downgrades unsupported
classifications to indeterminate.

The committed calibration validates these contracts against the twenty cases without representing
model performance: it records zero model calls and zero Builder calls. Live model execution remains
an optional, separately recorded operator action.

### Stage 4 — evidence assembly (MS #70 complete)

The repository publishes the unchanged coverage denominator, a zero-entry proven-divergence
register, all 1,077 flagged pairs in the semantic-indeterminate register, sampled provenance
classifications and one content-addressed receipt. Each sampled provenance result remains
`generation-path-present-per-pair-unclassified`; no history evidence was admitted. Community
engagement remains a separate authorized activity and was not performed.

## Run Stage 1

The upstream checkout must be clean and detached at the existing MS #48 pin.

```bash
git clone --filter=blob:none --no-checkout https://github.com/idempiere/idempiere.git /path/to/idempiere-release-13
git -C /path/to/idempiere-release-13 fetch --depth 1 origin 731515dcdd5278b843db33b9d3109d155b881951
git -C /path/to/idempiere-release-13 checkout --detach 731515dcdd5278b843db33b9d3109d155b881951
./idempiere-divergence-audit.sh build /path/to/idempiere-release-13
./idempiere-divergence-audit.sh verify
./idempiere-divergence-audit.sh verify-source /path/to/idempiere-release-13
```

Windows:

```powershell
.\idempiere-divergence-audit.ps1 build C:\path\to\idempiere-release-13
.\idempiere-divergence-audit.ps1 verify
.\idempiere-divergence-audit.ps1 verify-source C:\path\to\idempiere-release-13
```

`verify` validates the committed hashes, bindings, counts, station-use policy and claim boundary.
`verify-source` also rebuilds both artifacts from the pinned upstream checkout and rejects drift.

## Current claim boundary

Stage 1 proves deterministic pairing and pilot selection for one exact public-source commit.
Stage 2 adds a bounded static comparison and measures its substantial unresolved surface.
Stages 3 and 4 add bounded role contracts, deterministic safe-floor calibration and finding
registers without claiming live-model performance. None proves independent hand maintenance,
complete migration equivalence, native Oracle or PostgreSQL behavior, iDempiere application
equivalence, migration completion, customer readiness, or production readiness. No signed
CloudBank evidence is changed or reused as iDempiere proof.

## MS69 measured baseline

| Scope | Pairs | Equivalent under static policy | Divergent under static policy | Indeterminate |
|---|---:|---:|---:|---:|
| Order-to-cash pilot | 93 | 0 | 0 | 93 |
| All current pairs | 1,078 | 1 | 0 | 1,077 |

| SQL unit coverage | Oracle | PostgreSQL | Combined |
|---|---:|---:|---:|
| Parsed and compared | 388 | 388 | 776 |
| Parsed but indeterminate | 55,455 | 48,467 | 103,922 |
| Unparsed | 5,518 | 1,077 | 6,595 |
| SQL unit denominator | 61,361 | 49,932 | 111,293 |
| Administrative units excluded | 3,053 | 1,074 | 4,127 |

Decision coverage is **0.70%**, not 94% semantic equivalence because most statements were
structurally recognized. The pilot has 65,536 SQL units, of which 288 are decided, 59,957 are
parsed but indeterminate and 5,291 are unparsed. A pair can contain decided units and still be
indeterminate overall. Unknown constructs never inherit an equivalent verdict from file identity.

The only equivalent pair is `migration/iD11/*/202304171928_IDEMPIERE-5567.sql`: both dialects
declare a single-space default on `t_selection.t_selection_uu` and
`t_selection_infowindow.t_selection_uu`. The verdict excludes registration/client effects and
runtime coercion or constraints. It does not claim that either migration executed successfully.

The large flagged set means the original small-queue budget assumptions are not established.
MS70 consequently selected a bounded sample across repeated reasons instead of admitting the full
flagged set. Audit-specific Planner and Analyst payloads now sit around `BoundedModelProvider`, with
deterministic gates retaining verdict authority. The committed release proves contract calibration
and evidence accounting, not live-model classification quality.

## Run and verify Stage 2

```bash
./idempiere-divergence-audit.sh compare /path/to/idempiere-release-13
./idempiere-divergence-audit.sh verify-comparison
./idempiere-divergence-audit.sh verify-comparison-source /path/to/idempiere-release-13
```

```powershell
.\idempiere-divergence-audit.ps1 compare C:\path\to\idempiere-release-13
.\idempiere-divergence-audit.ps1 verify-comparison
.\idempiere-divergence-audit.ps1 verify-comparison-source C:\path\to\idempiere-release-13
```

Outputs are [comparison-policy.json](comparison-policy.json),
[stage2-pilot.json](stage2-pilot.json), [stage2-comparison.json](stage2-comparison.json) and
[stage2.receipt.json](stage2.receipt.json). Stage 1 artifacts remain unchanged.
Each pair ID resolves its exact source paths and logical hashes through the Stage 1 manifest;
segments identify the implicated ranges and reasons. Unequal structured schema values are retained
as declared differences, but policy-dependent differences are not promoted to proven divergences.

`verify-comparison` checks hashes, current implementation/policy/schema bindings, denominator,
source ranges, pilot prefix, claim boundaries and the derived receipt. These are **unsigned**
artifacts: offline integrity is not evidence authentication or a new semantic replay.
`verify-comparison-source` additionally admits the clean exact pin and rebuilds every result;
it rejects re-sealed results that disagree with source-derived semantics. Neither executes SQL.

## Run and verify Stages 3 and 4

```bash
./idempiere-divergence-audit.sh triage
./idempiere-divergence-audit.sh verify-triage
./idempiere-divergence-audit.sh verify-triage-source /path/to/idempiere-release-13
```

```powershell
.\idempiere-divergence-audit.ps1 triage
.\idempiere-divergence-audit.ps1 verify-triage
.\idempiere-divergence-audit.ps1 verify-triage-source C:\path\to\idempiere-release-13
```

`triage` deterministically rebuilds the policy, twenty-case work package, safe-floor calibration,
coverage, divergence, indeterminate and provenance registers, and receipt. `verify-triage` checks
their content hashes, current code/schema/policy bindings, exact derivation, budgets, counts and
claim boundary. `verify-triage-source` also replays the MS #69 source comparison and hydrates every
bounded source excerpt from the clean exact pin.

Credentialed execution is intentionally outside the release verifier. The Python controller's
`run-triage` action requires `OPENAI_API_KEY`, an explicit output path and current positive input and
output prices for both models. It uses `gpt-5.6-luna` for Planner and `gpt-6-astra` for Analyst by
default, performs input-token preflight, emits all forty call-evidence records, never invokes
Builder, and does not rewrite the committed deterministic registers.
