# Native Oracle 26ai / AlloyDB: 260 datatype pairs

**Result: `passed-bounded-native`, 260/260 equivalent pairs, 13 families,
65 bounded behaviours. Cleanup confirmed.**

Successful run: `types260-db44edf8ecce4c5b8b6860e698e79d97`.
Oracle 26ai Free 23.26.3.0.0 in FREEPDB1 and managed AlloyDB PostgreSQL 16.13
each produced 260 observations. All 260 comparisons matched; every family
finished 20/20 with no mismatched, blocked or pending cases.

The prior 20- and 100-pair campaigns overlap this scope. The verified catalog
overlay therefore reports **260 unique equivalent cases and 65 behaviours**,
not a sum of repeated executions. The catalog still has 500 bounded-model
behaviours overall. This is the bounded paired-probe contract described in the
[SQL pack](../../../data-modernization/oracle-paired-types260/README.md), not
exhaustive datatype conformance, Oracle 19c execution or additional platform
qualification. The retained CloudBank AlloyDB nonproduction qualification is
unchanged.

## Both attempts are retained

| Attempt | Result | Matched | Unexecuted pairs | Authorization through cleanup | Planning estimate |
| --- | --- | ---: | ---: | --- | ---: |
| `types260-a0da8b63ecf64777a220c01292f7f13f` | Failed: Oracle interval harness compile error | 220 | 40 | 41m 9.688s | $1.38 |
| `types260-db44edf8ecce4c5b8b6860e698e79d97` | Passed bounded native | 260 | 0 | 46m 34.650s | $1.56 |

The first attempt encountered ORA-00932/ORA-06550 before the first interval
observation. Its 220 completed comparisons all matched. Its failure and cleanup
remain signed and immutable; the 40 unexecuted pairs are not passes or semantic
mismatches. The corrected program uses explicitly typed negative Oracle interval
literals and text conversion for its invalid-input probe. Expected values and
diagnostic mappings did not change. The retry ran both interval families first,
then reran the remaining eleven families. Original interval SQL is retained
under the pack's `retired-v1` directory and bound to the exact retired plan.

## Cost and cleanup

The **$2.94 combined planning estimate** uses each attempt's authorization-to-
terminal elapsed time at the approved $2/hour planning rate, rounded up per
attempt. The separately approved cumulative allowance was $10. This is not a
measured GCP bill and excludes ongoing storage/backups. No resource was kept
running between attempts.

The engine signed completed cleanup for both attempts. A separate direct GCP
readback at `2026-09-18T03:14:32.307809+00:00` found AlloyDB and Cloud SQL
STOPPED with activation policy NEVER, and no owned runner VMs, boot disks or
firewall rules. `operational-readback.json` is explicitly unsigned operational
evidence; its file hash does not turn it into a signed database observation.

## Verification

`manifest.json` records the implementation revision for each attempt, file
hashes, elapsed times and cost basis. Each run folder contains its signed
authorization, exported journal and signed summary. `public-key.pem` is the
existing pinned campaign authority; no private key, credential or database
password is included.

The successful run has thirteen signed family journals, each with 60 case
events, anchored to signed parent checkpoints. Each individual journal stays
within the existing 256-event bound. The exporter verifies signatures, SQL and
expectation bindings, database identities and comparator replay. This is
operator-signed evidence, not independent vendor certification.

```powershell
$env:PYTHONPATH='src'
py -3.12 -m unittest tests.test_paired_types260_export -v
py -3.12 -m lightyear_data.oracle_paired_coverage --root .
```

In Control Tower, choose **CloudBank → 260 datatype pairs → The run**. Both
attempts remain in the recorded-run selector and Convergence. Expand the signed
authorization, family progress, case evidence and journal events to inspect
the result; the Work queue aggregate deduplicates the overlapping campaigns.
