# iDempiere schema alignment and application preparation

Follow-up: [the bounded native application journey passed](../idempiere-application/README.md). This document records the preceding schema work and its remaining limits.

The isolated Oracle and PostgreSQL successors of the MS84 historical replay now
agree on all **3,826 foreign-key relationships** and the nullability of all
**18,852 common base-table columns**. Full table-row hash multisets are unchanged
by the repairs. The source databases from MS84 were stopped and preserved.

This is a bounded schema result, not unrestricted schema equivalence. The
[assessment](assessment.md), [machine-readable assessment](assessment.json) and
[receipt](receipt.json) retain that distinction. All measurements here used local
Docker; no GCP resources were started.

| Check | Before | After |
|---|---:|---:|
| Common base tables | 913 | 913 |
| One-sided foreign-key relationships | 36 | 0 |
| Nullability conflicts | 30 | 0 |
| Foreign-key catalog contracts that match | 3,790 | 3,826 |
| Matching primary-key column sets | 900 | 900 |
| Matching unique-key column sets | 917 | 917 |

The `AD_User_Roles` primary key lists its two columns in a different order on
the two engines. The tuple uniqueness rule is the same; index access order is
retained as a separate difference. Oracle also has two Java helper tables with
their own unique constraints. Matching key column sets alone do not prove
matching enforcement, null semantics or performance.

## Repairs and their authority

The 36 added foreign keys comprise 32 Oracle additions and four PostgreSQL
additions. Native preflight queries found no orphan rows. Definitions preserve
ordered child/reference columns, referential actions and deferral settings.
Both final catalogs show matching, enabled, validated relationships; PostgreSQL
internal referential-integrity trigger state is included in the assessment.

For the 30 nullability conflicts, the user selected the shared iDempiere
application dictionary as the rule. Both databases' dictionary rows agreed.
The repair made 23 Oracle columns optional, five Oracle columns required and two
PostgreSQL columns required. Native preflight found no null values in columns
being tightened. This resolves these 30 observed conflicts; it does not assert
that every column in the estate was audited against the dictionary.

All table-row multisets were captured before the foreign-key repair, after that
repair and after the nullability repair. These comparisons include engine-only
tables within each lane. Oracle's first observation immediately after the
foreign-key DDL failed with `ORA-01466`. The failure remains in the archive. Only
the observation was retried; the DDL was not executed twice.

## Native behavior checks

Thirty rollback-only checks passed on each engine across `C_BPartner`,
`M_Product`, `C_Order`, `M_InOut`, `C_Invoice` and `C_Payment`. Each table has a
positive update control and negative controls for its primary key, a foreign
key, a required column and its `IsActive` Y/N check. Deferred constraints are
forced immediate before observing the result. A rejection passes only if its
native error belongs to the expected class. The tested row is read back after
every rollback. This is 30 checks per engine, not complete constraint coverage.

Twenty additional paired **standalone expression** probes produced 11 matching
values, two matching numeric-overflow rejections and seven differences. These
expressions intentionally expose engine behavior; they do not reproduce all
table constraints or the application input path.

| Probe difference | Observed behavior |
|---|---|
| Unbounded 50-digit number | Oracle rounded; PostgreSQL retained all digits |
| Empty VARCHAR | Oracle returned null; PostgreSQL returned empty text |
| Multibyte input cast to one-byte/one-character CHAR | Oracle returned null; PostgreSQL retained the character |
| Fractional timestamp | Oracle DATE discarded fractional seconds; PostgreSQL timestamp retained them |
| Invalid UUID | Oracle VARCHAR accepted the text; PostgreSQL UUID rejected it |
| Invalid JSON | Oracle CLOB expression accepted the text; PostgreSQL JSON rejected it |
| Duplicate JSON object key | CLOB preserved the input text; JSONB retained the final value |

The separate clock observation also shows `SYSDATE` advancing during a
transaction while PostgreSQL `now()` stays at the transaction start. A matching
clock function name or similar default expression is not proof of equal timing.

In particular, **the CLOB probe does not establish that an actual Oracle JSON
column accepts invalid JSON**: the imported schema contains `IS JSON` checks.
Likewise, the pinned application's `PO.java` converts ordinary empty string
values to null and Boolean values to Y/N when saving. Application behavior must
therefore be measured through that code, rather than inferred from a cast.

## What remains to prove

The assessment keeps datatype behavior, defaults, broader key/check enforcement,
indexes, views, routines, triggers, privileges, row policies and sequences as
open dimensions. A catalog count of zero is not a platform-wide proof of absence
or effective permissions. The 6,268 declaration differences and 7,720 raw default
definition differences include dialect differences as well as substantive
behavior; neither number is a count of confirmed application defects.

The subsequent [application receipt](../idempiere-application/receipt.json)
records a successful customer, product, order, shipment, invoice and payment
scenario through the pinned application's model and document-workflow APIs.
Opening inventory and price-list setup are prerequisites. Verified outcomes
include completed documents, two units ordered/shipped/invoiced, matching
monetary totals, payment allocation and stock of eight after starting with ten.

Raw UUIDs, timestamps and other differences remain retained and validated under
explicit rules. That result supports a bounded application claim; it does not
make universal SQL equivalence or platform qualification true.

## Reproduction and retained evidence

The [evidence archive](evidence.zip) contains native catalogs, preflight results,
exact executed DDL, readback evidence, standalone probes and table-constraint
probes. Its inventory and byte hashes are in the receipt. Repeated row-hash
multisets are stored once by content hash; the state manifests reconstruct the
original sealed native states without changing their hashes. These are row
hashes, not a distributable database dump or an independent attestation.

From the repository root, run the offline assessment against extracted catalogs:

```powershell
$env:PYTHONPATH = 'src'
python -m lightyear_calibration.schema_equivalence `
  --oracle-catalog evidence/after-nullability/oracle-catalog.json.gz `
  --postgresql-catalog evidence/after-nullability/postgresql-catalog.json.gz `
  --output work/schema-review
```

The output directory must be new. Exit code 3 deliberately means that schema
review remains required; it does not mean the catalog capture failed. The
assessment and publication tests run offline without Docker or credentials.
