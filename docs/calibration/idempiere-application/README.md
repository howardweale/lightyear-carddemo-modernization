# iDempiere: bounded native application equivalence

**Passed on Oracle 26ai Free and PostgreSQL 15.19, using local Docker.** One
end-to-end scenario exercised six business stages through the pinned iDempiere
application's model and document-workflow APIs. Both engines produced the same
verified business outcomes, with no new application issues and no unexplained
row differences. This is a headless business-logic test, not a browser UI test.

The [receipt](receipt.json), [comparison](comparison.json),
[exact Java harness](LightyearJourneyTest.java) and [native evidence](evidence.zip)
make the result inspectable. Source commit:
`731515dcdd5278b843db33b9d3109d155b881951`. The reference client is GardenWorld.

## What ran

The scenario creates a new customer with an address and a new stocked product.
It establishes opening inventory of ten units and a price-list entry of ten per
unit, then processes a two-unit order, shipment, invoice and payment. Customer,
product and document saves use normal commit boundaries. The same harness bytes
run on both engines; no direct SQL writes substitute for business operations.

| Stage or outcome | Oracle | PostgreSQL |
|---|---|---|
| Customer and address saved and linked | Verified | Verified |
| Stocked product and price-list entry saved | Verified | Verified |
| Order completed; quantity / net total | 2 / 20 | 2 / 20 |
| Shipment completed; quantity delivered | 2 | 2 |
| Invoice completed; total | 20 | 20 |
| Payment completed and allocated | 20 | 20 |
| Invoice marked paid | Yes | Yes |
| Closing stock, from opening stock of 10 | 8 | 8 |
| Inventory movement records | 2 | 2 |
| Invoice/payment/allocation accounting entries checked | 12 | 12 |
| Balanced document/accounting-schema/currency groups | 6 | 6 |
| New application issues | 0 | 0 |

The verifier reads committed records independently after the application JVM
exits. It checks customer/product/document relationships, UUIDs, quantities,
amounts, invoice paid status, completed allocation headers and allocation
amounts. It also checks opening and closing inventory and balances accounting
debits and credits separately for each document, accounting schema and currency.
A successful JUnit exit alone cannot satisfy these checks.

## Schema first, then application

The preceding [schema alignment](../idempiere-schema/README.md) repaired 36
one-sided foreign keys and 30 nullability conflicts, using the user-selected
shared application dictionary. All 3,826 foreign-key relationships now match;
all 18,852 common base-table columns agree on nullability. Those repairs changed
no table-row multisets. The original MS84 databases remain preserved.

The final application run used fresh successors of that same MS84 state. The
exact validated repairs were reapplied, full row multisets were checked against
MS84 again, and fresh catalogs were captured. The schema review still explicitly
leaves broader datatype, default, routine, view, index and platform behavior
unproven. Application execution proceeds under the declared six-stage scope;
this does not turn a partial schema assessment into universal equivalence.

## Every difference remains visible

The full readback covers **913 common base tables**. Differences are separated
by where their evidence came from:

| Category | Fields |
|---|---:|
| Unchanged differences already validated in MS84 | 5,540 |
| New UUID differences validated by existing rules | 5 |
| New differences validated by application rules | 300 |
| Total new validated differences | **305** |
| Unexplained differences | **0** |

Application rules permit only narrowly checked differences:

- New UUIDs must be valid, unique in their column and absent from the starting
  records. The column must be the declared table UUID column.
- Generated creation/update timestamps and processed epoch milliseconds must
  fall within the recorded native execution window. Existing creation times
  cannot be changed under this rule.
- Workflow durations must be nonnegative integers bounded by that execution
  window. This is functional evidence, not equal-performance evidence.
- Workflow messages may differ only in exact decimal rendering, such as `20`
  versus `20.0`; text, record numbers and numerical values must otherwise agree.
- Runtime database addresses must match the isolated target and pinned driver's
  connection format. Oracle's database instance name must match a native query;
  PostgreSQL's unchanged seed metadata is retained because the pinned
  application does not refresh that field on PostgreSQL.

Unknown differences, missing/extra row keys, new application issues and changes
outside the declared journey tables block admission. Every accepted difference
keeps both raw values and the rule that admitted it. Existing MS84 differences
are not counted as new application evidence.

## Earlier attempts are retained

The first attempt omitted a price-list entry. Both engines rejected the order
with “Product is not on Price List.” Those failed executions remain in the
archive as setup diagnostics, not successful full journeys.

The second attempt completed and committed on both engines, but held the whole
scenario in a single transaction. An invoice lookup outside that transaction
could not yet see the newly created customer, generating two application issues
on each engine. Both traces, the issue observations and the raw comparison are
retained. That transaction pattern is not qualified by this result.

The final attempt uses normal commit boundaries and fresh verified databases.
Both runs completed with no new issues. The archive contains all six native
application attempts: four diagnostic attempts and the two final executions.

## Claim boundaries

`bounded_journey_equivalence: true` means this particular priced, stocked,
customer-to-payment scenario passed on both native engines. The broader
`application_equivalence`, `schema_equivalence` and `platform_qualification`
flags remain false. This is not complete iDempiere certification.

The scenario does not cover every tax rule, valuation method, exception,
concurrent operation, cancellation/reversal, deployment configuration or user
interface behavior. It does not qualify Oracle 19c, AlloyDB, or a production
installation. The standalone SQL differences recorded in the schema assessment
remain explicit limits. No GCP resources were started.

The diagnostic and final database containers are stopped, with data retained.
The [cleanup observation](cleanup.json) records that state; it is bound by the
receipt.

Evidence consists of native application/database observations with content-hash
bindings. It is not independently attested or a digital signature by a third
party. Credentials, private runtime configuration and database images are not
included in the published archive.

## Reproduce the checks offline

The publication test reconstructs the original sealed states from deduplicated
row-hash manifests, verifies the retained raw row files, reruns every application
audit rule and checks the committed business/accounting outcomes:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_application_journey tests.test_application_effects tests.test_application_publication -v
```

This needs no database connection or credentials. The read-only module
`python -m lightyear_calibration.application_journey --help` also accepts the
retained snapshot, execution, trace, harness and effect-checkpoint paths.

To repeat native execution, build the pinned iDempiere checkout, place the
supplied harness in `org.idempiere.test/src/org/idempiere/test/`, and use an
isolated pair with the verified schema and starting data. The upstream Tycho
test runner selects it with `-DskipTests=false -Dtest=LightyearJourneyTest`.
Supply `PropertyFile`, `lightyear.output` and `user.timezone=UTC` to the test JVM.
The harness commits records and uses a fixed test customer/product value; a
fresh verified database pair is required for each repeat. Do not point it at
an employee evaluation package or a live customer database.
