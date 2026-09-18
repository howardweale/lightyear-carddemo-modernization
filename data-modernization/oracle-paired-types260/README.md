# Oracle 26ai / AlloyDB: 260 bounded datatype pairs

This pack covers all 13 `types` topic families in the current catalog: 65
behaviours, four case dimensions per behaviour, 260 comparisons and 520 database
lane executions. The first 100 cases retain the five-family pack's SQL and
expectations byte for byte. The other 160 cases add eight families.

The cases bind their catalog IDs, catalog expectation hashes, independent probe
expectations, source/target SQL hashes and implementation hashes into the signed
authorization. These are bounded synthetic probes, not exhaustive conformance
tests or 260 randomly generated inputs. A family reuses its native probe program
across the catalog's focus/dimension combinations; each case selects its
reviewed observations. Expectations are not inserted into observed output.

| New family | Explicit mapping and probes | Limits |
| --- | --- | --- |
| BINARY_FLOAT | PostgreSQL `real`; exact network-order IEEE bits for 1.5 and the smallest normal value, null, signed-zero equality, NaN ordering/equality, invalid input and recovery | No comparator tolerance; no exhaustive subnormal, rounding or arithmetic sweep |
| BINARY_DOUBLE | PostgreSQL `double precision`; corresponding 64-bit probes | Same bounded limits |
| NCHAR | Unicode `char(3)`; Omega, three-character boundary, blank padding, character length, comparison, actual column overflow and recovery; UTF-8 byte rendering | Does not qualify all national character sets or collations |
| RAW | PostgreSQL `bytea`; leading zero/high bytes, null, byte length, hex case equality, invalid hex and recovery | Does not enforce every Oracle RAW size limit |
| TIMESTAMP WITH TIME ZONE | PostgreSQL `timestamptz`; explicit UTC instant, year crossing, equivalent offsets, session display at +05:30, malformed input and recovery | Original offset/region retention and DST transitions are not covered |
| TIMESTAMP WITH LOCAL TIME ZONE | Oracle typed LTZ variable and PostgreSQL `timestamptz`; UTC/session projection of the same instant | No LTZ persistent storage, database time-zone migration or DST claim |
| INTERVAL YEAR TO MONTH | PostgreSQL interval; signed total months, 100-year boundary, null, ordering, invalid input and recovery | Does not enforce the full Oracle precision/range domain |
| INTERVAL DAY TO SECOND | PostgreSQL interval; signed total seconds, one-microsecond boundary, null, ordering, invalid input and recovery | No exhaustive precision, range or month/day conversion claim |

New diagnostic mappings are deliberately specific: invalid floating input
`-1722 ↔ 22P02`, NCHAR column overflow `-12899 ↔ 22001`, invalid hex
`-1465 ↔ 22023`, invalid exact datetime format `-1861 ↔ 22007`, and invalid
interval input `-1867 ↔ 22007`. Other errors fail the independent expectations.
Raw codes are retained. The comparator never strips padding, rewrites nulls,
rounds floats or silently adjusts timestamps.

The SQL contracts follow the relevant
[Oracle datatype definitions](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Data-Types.html),
[PostgreSQL numeric definitions](https://www.postgresql.org/docs/16/datatype-numeric.html),
[PostgreSQL date/time definitions](https://www.postgresql.org/docs/16/datatype-datetime.html),
and Oracle [year/month](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/TO_YMINTERVAL.html)
and [day/second](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/TO_DSINTERVAL.html)
interval conversion interfaces. Documentation and simulation do not establish
native equivalence; only verified paired observations do.

```powershell
$env:PYTHONPATH='src'
py -3.12 -m lightyear_workflow.paired_types260 verify --root .
py -3.12 -m lightyear_workflow.campaign_service review --root . --campaign-id oracle26ai-alloydb-types260
```

The profile lives in ignored local state at
`work/campaigns/oracle26ai-alloydb-types260/profile.json`. The existing stopped
AlloyDB primary and a temporary Oracle runner are reused under the same
ownership checks and shared exclusion lock. The plan permits a 60-minute active
window with cleanup afterward; the $10 allowance is an estimate, not a billing
cap. The prior 100-pair run took 24m41s including startup and cleanup. Scaling its
SQL phase suggests roughly 45–55 minutes, or $1.50–$2 at the existing $2/hour
planning rate. This is not a current GCP price quote or measured bill; persistent
storage/backups are excluded.

Thirteen family journals contain at most 60 case events each and are anchored
to the signed parent journal. No journal exceeds the existing 256-event bound.
Interruptions retain observations and never replay SQL automatically.

If all cases pass natively, prior 20 + prior 100 + new 260 becomes **260 unique
paired cases**, not 380. This is Oracle 26ai paired-probe coverage; it does not
advance the separate Oracle 19c/26ai wallet gate or extend/revoke CloudBank's
retained AlloyDB nonproduction platform qualification.
