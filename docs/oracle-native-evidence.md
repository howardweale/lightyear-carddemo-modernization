# Oracle / PostgreSQL native evidence: 260 matching pairs

**The published Oracle 26ai–AlloyDB PostgreSQL campaign passed all 260 native
case pairs across 13 datatype families and 65 bounded behaviours.** The zero in
the separate MS51 readiness snapshot is not a project-wide native execution count.

| Evidence scope | Recorded result | What the count means |
| --- | --- | --- |
| Native Oracle 26ai ↔ AlloyDB PostgreSQL paired campaign | **260/260 matching pairs** | 260 source observations and 260 target observations in the successful run; 520 lane observations, compared as 260 pairs. |
| Deduplicated paired-campaign coverage | **260 unique pairs; 65 behaviours** | Earlier 20- and 100-pair campaigns overlap the 260-pair scope and are not added again. |
| MS51 Oracle 19c + 26ai catalog readiness snapshot | **`native_executed_case_count: 0`** | This committed admission/readiness artifact does not aggregate the separate paired-campaign receipts. |
| Bounded-model catalog | **500 behaviours; 2,000 cases** | Model verification is a separate evidence class from native database execution. |

## What ran

The [published campaign](receipts/oracle26ai-alloydb-types260-20260917/README.md)
records successful run `types260-db44edf8ecce4c5b8b6860e698e79d97` on Oracle
26ai Free **23.26.3.0.0**, database FREEPDB1, and managed AlloyDB PostgreSQL
**16.13**. Each of the 13 families completed 20/20 matching pairs. The published
bundle retains the signed authorization, family journals and summary, public
verification key, and cleanup evidence.

The first attempt completed 220 matching pairs and left 40 unexecuted after an
Oracle interval harness compile error. Its failed result remains intact. The
successful retry ran all 260 pairs; it did not relabel the incomplete attempt.

The [manifest](receipts/oracle26ai-alloydb-types260-20260917/manifest.json)
identifies both attempts and their original file hashes. Verification checks
the pinned campaign authority, signatures, SQL bindings, journal chains and
comparator replay. This is operator-signed evidence, not vendor certification.

## Why MS51 still contains zero

The [MS51 gate](../data-modernization/oracle-native-execution-gate/README.md)
defines a different contract: 2,000 catalog cases on each of Oracle 19c and 26ai,
or 4,000 required case/version executions. It requires its own per-case harness
and expectation bindings, wallet identity and signed receipt format. Its first
NUMBER family has 40 materialized case/version harnesses.

The paired campaign uses a separately verified source-to-target probe contract.
Its receipts are not imported into the MS51 readiness snapshot. The zero is
**not** a claim that no native Oracle tests ran, and it is **not** a rule that
partial coverage must stay zero until all 4,000 executions finish. Replacing it
with 260 would mix contracts and change the meaning of a historical artifact.

The current paired report computes its own verified counts and deduplicates
overlapping case IDs. From the repository root:

```powershell
$env:PYTHONPATH = 'src'
py -3.12 -m lightyear_data.oracle_paired_coverage --root .
```

In Control Tower, select **CloudBank → 260 datatype pairs → The run** for the
recorded attempts. The Work queue's **Native Oracle 26ai–AlloyDB paired coverage**
shows the verified aggregate, separately from the selected run. If evidence
cannot be verified, the report shows unavailable counts rather than assuming a
zero or preserving an earlier pass.

## Qualification boundaries

The 260 pairs establish bounded equivalence for the tested examples. They do
not establish exhaustive Oracle compatibility, Oracle 19c execution, or customer
production acceptance. The separate [CloudBank AlloyDB platform qualification](
cloudbank-alloydb-platform-qualification.md) remains valid for its synthetic
nonproduction scope. Application journeys, datatype pairs and platform drills
retain their own counts and receipts.

This reporting clarification changes no original receipt, signature, measured
result, acceptance threshold or qualification flag. No new database run is needed
to display the existing result accurately.
