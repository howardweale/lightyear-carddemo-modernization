# Oracle 26ai → AlloyDB: 100 bounded catalog pairs

This pack materializes five existing catalog families: NUMBER, CHAR, VARCHAR2,
DATE and TIMESTAMP. Each has five behaviours and four case dimensions per
behaviour: 100 unique case IDs, 200 SQL files, 25 bounded behaviours. NUMBER
reruns the previous pilot; it does not add 20 new catalog cases. Cases combine
reviewed probes across focus/dimension; this is not 100 random inputs or full
datatype conformance. Materialization and mock tests are not native execution.

| Family | Main observations and explicit target transformation |
| --- | --- |
| NUMBER | Existing precision, null, overflow, recovery and decimal-format probes, unchanged. |
| CHAR | Fixed-width padding, length, comparison and assignment overflow. Target SQL explicitly preserves padding when rendering text. |
| VARCHAR2 | Empty string becomes null, trailing spaces affect length/comparison, assignment overflow and recovery. Target SQL uses `nullif` explicitly. |
| DATE | Leap-day arithmetic and retained hours/minutes/seconds. Oracle DATE maps to PostgreSQL timestamp; formatting is explicit. |
| TIMESTAMP | Microseconds, precision reduction, day rollover, format and diagnostic recovery. No time-zone-qualified timestamp claim. |

Only three diagnostic pairs are approved: Oracle `-1438` / PostgreSQL `22003`,
`-12899` / `22001`, and `-1861` / `22007`. Raw codes remain in observations.
All other typed values and nulls must meet independent expectations and compare
exactly. The comparator never strips spaces or rewrites empty strings. Target
SQL adaptations are visible, hashed transformation code, not proof that the
unmodified database semantics are identical.

Character overflow uses real column assignment: disposable tables in the
isolated Oracle container and session-local `pg_temp` tables inside rolled-back
AlloyDB transactions. Explicit PostgreSQL casts can truncate, so they cannot
serve as the column-overflow test. No application data or permanent target
objects are used.

Contract authorities: [Oracle datatype semantics](https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/sql-data-types.html),
[Oracle exact format models](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Format-Models.html),
and [PostgreSQL character types](https://www.postgresql.org/docs/16/datatype-character.html).

The plan binds the case IDs, catalog expectation hashes, probe expectation
hashes, both SQL hashes, implementation hashes, image digest, resources, budget
and runtime. Verify without starting anything:

```powershell
$env:PYTHONPATH = 'src'
py -3.12 -m lightyear_workflow.paired_types verify --root .
py -3.12 -m lightyear_workflow.campaign_service review --root . --campaign-id oracle26ai-alloydb-core100
```

The separate ignored profile is
`work/campaigns/oracle26ai-alloydb-core100/profile.json`. It uses the existing
five-field profile schema. A profile is proposed terms, not authorization.

Each family has at most 60 case events (20 source, 20 target, 20 comparisons).
A bounded parent journal signs the family's head hash, event count and outcome
counts. Missing/swapped/modified children invalidate detail and aggregate
coverage. The RunStore bound remains 256. Convergence reads signed summaries
without opening any journal. NUMBER and Core100 share one authority/index and
resource exclusion: an active run or unresolved cleanup blocks either campaign.

The catalog overlay replays signed evidence under the paired probe contract,
deduplicates case IDs and retains the latest native result per case. It excludes
simulated/unclassified runs. It does not rewrite the legacy wallet gate or its
historical receipts: that gate requires 2,000 cases on **each Oracle version**,
19c and 26ai. AlloyDB executions cannot fill Oracle execution slots.

No result from this pack establishes full AlloyDB platform qualification,
CloudBank application equivalence, Oracle 19c coverage or production readiness.
