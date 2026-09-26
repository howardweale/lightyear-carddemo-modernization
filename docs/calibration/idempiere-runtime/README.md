# iDempiere: measured runtime context and native migration effects

**Measured on local Docker, 25–26 September 2026.** No GCP resources were started.
The [sealed receipt](receipt.json) separates the two experiments and names what
remains unresolved. This is a public reference-estate experiment, not customer
application or historical-upgrade certification.

| Measurement | Result |
|---|---:|
| Pairs replayed statically with actual catalog/session facts | 1,078 |
| Decided SQL units, current gate without context | 780 / 111,293 |
| Decided SQL units, same gate with captured context | 780 / 111,293 |
| Additional decisions from native context | **0** |
| Pending migration pairs executed on both engines | **20** |
| Native script executions | **40** |
| Successful native client exits | 40 / 40 |
| Strict whole-pair row-effect comparisons that differ | 20 / 20 |
| Whole-pair equivalence claims | **0** |
| Exact table-delta matches | 49 / 111 |
| Additional table comparisons with matching changed fields | 13 |
| Invalid Oracle objects after the tranche | **14** |

## Stage one: actual facts, no extra decisions

The official release-13 schema and data were imported into Oracle AI Database
26ai Free (23.26.3.0.0) and PostgreSQL 15.19. Both images are pinned by digest in
the receipt. Source commit is `731515dcdd5278b843db33b9d3109d155b881951`;
binary seed commit is `30af25e9db302a6cdefd9e6c3846f7cedc5ce4d0`.
[Preflight](preflight.json) retains the original archive URLs and hashes. Its
prepared/not-executed status describes that earlier offline step only.

The successful Oracle import reported one expected error: the pre-created
ADEMPIERE user already existed (ORA-31684). The supplied AfterImport.sql then
completed successfully and reported no invalid objects. The PostgreSQL import
completed without errors. An earlier Oracle lite-image bootstrap failed because
its Data Pump support was unusable; that attempt was retained locally and never
used as evidence for the successful import.

Both metadata captures contain all results from the versioned collector query
sets: tables, columns, constraints, triggers, routines, views, sequences, policies,
privileges and effective session settings. A query failure stops capture. The
raw captures are retained as compressed JSON under `evidence/`. Completeness is
relative to those schema-owner query sets, not every database-wide setting.

The replay reconstructs the conservative runtime context from those exact
captures and rejects a supplied context that differs. It replays every pinned
pair and runs a same-version no-context control. Full metadata stays in the raw
capture; types and effects the current gate cannot reason about remain unknown.

**Runtime context lift is zero.** The older 776-to-780 improvement came from the
previous calibration work. It is not counted again here. The current gate still
reports one equivalent complete pair and 1,077 indeterminate pairs. The complete
[stage-one report](evidence/stage-one/report.md) and
[measurement](evidence/stage-one-measurement.json) retain counts and unresolved
causes. Real constraints/triggers do not become absent merely because they have
been observed, and broad datatype semantics remain outside the current gate.

These are facts about one imported release-13 baseline. They are not historical
entry catalogs for older migration scripts. The result measures the ceiling of
this gate on this corpus and these supplied facts, not a universal ceiling of
static analysis.

Catalog sessions and execution sessions are recorded separately. For example,
the Oracle metadata capture observed time zone -07:00; native migration clients
explicitly selected UTC and logged the effective value before every script.

## Stage two: observed execution, with all differences retained

The live migration registers identified 20 normal scripts outstanding on both
engines. They were executed in upstream sorted-path order, using their pinned
source bytes with native SQL*Plus and psql clients. Before and after each pair,
the collector read all ordinary base tables, every column and every row, with no
sampling, plus the defined structural metadata query set.

The two seeds already differed: Oracle began with 913 base tables and 185,292
rows; PostgreSQL began with 912 tables and 185,253 rows. Consequently an observed
difference is not automatically a defect in the migration. Before/after hashes
and exact row multisets retain that distinction.

All 40 clients exited successfully; no ORA, SP2, ERROR or WARNING lines appeared
in their execution logs. All 20 scripts registered successfully on both engines.
That establishes execution, not equivalent effects. All 20 strict row-effect
comparisons differ. No timestamps, UUIDs, dialect-specific registration paths,
sequence counters or other fields were suppressed to manufacture a pass.

Across 111 changed-table comparisons, 49 have identical full row deltas.
Thirteen more have identical changed-field transitions when aligned by the
captured primary key, despite different untouched values in their full rows.
Those are diagnostics only; they do not promote the original verdict.
Remaining differences include AD_MigrationScript registrations, AD_Sequence
counter values, and timestamps or inserted values in application metadata.
[Effect diagnostics](evidence/effect-diagnostics.json) retain both lanes' values.
Structural changes require separate semantic review; row matches alone do not
certify them.

After pair 11, a read-only Oracle after-snapshot encountered ORA-01466 following
DDL. Both scripts had already succeeded. Only the observation was retried in a
new directory; the migration was not re-executed. The failed partial capture
remains local. Later observations waited across the DDL timestamp boundary.

## Remaining work and upgrade limits

The [final checks](evidence/final-checks.json) found 14 invalid Oracle views or
procedures after this tranche, although USER_ERRORS was empty. No constraints
or triggers were disabled. PostgreSQL had no invalid indexes, unvalidated
constraints or disabled triggers under the checks performed. Invalid Oracle
objects remain a blocker to calling the upgraded estate clean; their cause and
recompilation behavior have not been established.

The 1,078-pair inventory is accounted for as follows:

- 1,053 pairs already registered on both seeds: not re-executed and not counted
  as fresh native evidence.
- 20 common outstanding normal pairs: executed in this tranche.
- One older Oracle-only unregistered script (IDEMPIERE-3413): unresolved entry
  history; not blindly replayed over a newer seed.
- Four post-migration maintenance pairs: a separate phase, not executed here.

Next, resolve the Oracle validity and entry-state differences, execute the
maintenance phase with separate observations, and define reviewed comparison
policies for runtime values. Preserve the strict results alongside any policy-
based comparison. Native coverage of the historical scripts needs older seeds
or verified checkpoints; the current seed cannot recreate their entry states.

## Evidence and repeatability

`receipt.json` lists SHA-256 hashes for 123 retained evidence files (approximately
5 MB): both complete raw catalog captures, import logs, execution plan, all 20
comparisons and client logs, field diagnostics, final checks, and the exact
run-specific capture/execution controller sources. Hashes establish integrity,
not independent attestation. Controller sources document this run and are not a
general-purpose unattended provisioning interface.

Full row snapshots and the larger replay bundle remain in the ignored local
`work/native-run-20260925/` directory. They contain all original row values and
sealed state files; published row hashes alone cannot reconstruct those rows.
Local credentials are in ignored `private.json` and are not included in this
publication. Task-owned containers are stopped after evidence capture, with data
retained for follow-up.

To replay stage one against the retained captures, derive context from the
source-bound acquisition template using
`lightyear_calibration.native_catalog.context_from_captures`, then pass that
compact JSON to `python -m lightyear_calibration replay-idempiere` together with
`--oracle-catalog` and `--postgresql-catalog` (the `.json.gz` files are supported).
Use the pinned source, `factory/idempiere-divergence-audit/stage2-comparison.json`
and `pairing-manifest.json`, and a new output directory. This reads evidence and
source; it does not rerun migrations. Re-executing native scripts requires fresh
verified entry states, not the already-upgraded containers.

From this checkout in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_native_catalog tests.test_native_effects tests.test_native_publication tests.test_idempiere_runtime_preflight tests.test_calibration_loop tests.test_calibration_public -v
```

These tests verify collector/comparator safeguards and published evidence
accounting. Synthetic test fixtures do not count as additional native executions.
