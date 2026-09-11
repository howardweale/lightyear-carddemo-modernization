# iDempiere Oracle/PostgreSQL divergence audit (IDDA)

IDDA is the MS #68–#70 project stream inside the existing LIGHTYEAR repository. It audits the paired
Oracle and PostgreSQL migration scripts in the already-pinned iDempiere release 13 estate.

| Milestone | Scope | Status |
|---|---|---|
| MS #68 | Inventory, pairing and premise check | Complete |
| MS #69 | Deterministic semantic comparison | Planned; order-to-cash pilot first |
| MS #70 | Bounded triage and evidence assembly | Planned; comparator findings only |

Customer production readiness, governed cutover and continuous assurance remain future unnumbered
work. Reassigning these milestone numbers does not change earlier signed CloudBank evidence.

The governing execution rule is **deterministic sweep first; models only on the bounded set that
the comparator cannot resolve**. Stage 1 is complete and used no model calls.

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

### Stage 2 — deterministic semantic comparison (MS #69 next)

Build dialect parsers and a normalization layer against the existing semantic core. The comparator
must distinguish at least:

- Oracle `ALTER TABLE ... MODIFY` from PostgreSQL `t_alter_column` helper semantics;
- `NUMBER` precision and scale from `NUMERIC` behavior;
- Oracle empty-string/NULL behavior from PostgreSQL character behavior;
- Oracle `DATE` from PostgreSQL date/timestamp choices;
- defaults, nullability, constraints, indexes and schema-object changes;
- DML effects and explicitly unsupported procedural or session-dependent behavior.

Coverage is the primary output. Each construct is counted as parsed-and-compared,
parsed-but-indeterminate, or unparsed. An unknown construct can never be treated as equivalent.
The order-to-cash pilot runs before the remaining 985 pairs.

### Stage 3 — bounded triage (MS #70 planned)

Only Stage 2 findings enter the model workcell. Planner bounds the implicated construct; Analyst
classifies deliberate adaptation, cosmetic difference, genuine divergence, or indeterminate.
The existing token preflight and per-role context limit apply. Builder remains unused. A
deterministic verifier checks evidence and policy; a model classification cannot create a verdict
by itself.

### Stage 4 — evidence and publication (MS #70 planned)

Publish the coverage denominator, paired/unpaired register, divergence register, indeterminate
list, provenance classifications, and one content-addressed run receipt. Community engagement is a
separate authorized activity; nothing in this repository contacts iDempiere maintainers.

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

Stage 1 proves deterministic pairing and pilot selection for one exact public-source commit. It
does not prove independent hand maintenance, parser coverage, semantic equivalence, native Oracle
or PostgreSQL behavior, iDempiere application equivalence, migration completion, customer
readiness, or production readiness.
