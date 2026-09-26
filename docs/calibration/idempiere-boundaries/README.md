# iDempiere boundary and operational journeys

The boundary journey found a real precision loss: **Oracle discarded fractional
seconds from `M_InOut.ShipDate`; PostgreSQL preserved them.** Both engines
produced the expected fractional-price, discount, tax and payment results,
preserved the Unicode customer name, and saved an empty optional description as
SQL null through the application.

A separate operations trial found an Oracle syntax error in the pinned
application's `Query.setForUpdate(true).firstOnly()` combination. The original
failure remains evidence; a later test uses the collection-query API with an
explicit single-primary-key predicate and cardinality assertion. These are
different caller contracts.

**The final bounded operations comparison passed on both engines**, with zero
unresolved row differences and zero new application issues. Fractional timestamp
preservation and the original locking API remain failed claims.

See the [receipt](receipt.json), [fractional comparison](fractional-comparison.json),
[operations comparison](operations-comparison.json), [datatype inventory](mappings.md),
and [native evidence archive](evidence.zip). There is no blanket application or
platform qualification claim.

## The risky business inputs

Both lanes run the same pinned iDempiere model and document-workflow code, commit
normal business transactions, then undergo independent native database readback.
Source commit: `731515dcdd5278b843db33b9d3109d155b881951`.
The engines are Oracle 26ai Free and PostgreSQL 15.19 in local Docker.

| Input or independently calculated outcome | Value |
|---|---|
| List price | 19.995 |
| Discount | 10% |
| Actual unit price | 17.9955 |
| Quantity | 3 |
| Net amount, rounded HALF_UP to two places | 53.99 |
| Fixture tax rate | 7.5% |
| Rounded tax amount | 4.05 |
| Invoice and payment | 58.04 |
| Opening / closing stock | 10 / 7 |
| Customer name | `Café 東京 Łódź` |
| Optional description input / stored value | empty string / SQL null |
| Shipment timestamp input | `2026-09-26T12:34:56.123456` |
| Oracle timestamp readback | `2026-09-26T12:34:56` |
| PostgreSQL timestamp readback | `2026-09-26T12:34:56.123456` |

The tax is an existing GardenWorld reference fixture, not a claim about current
tax law. Expected monetary results are calculated independently using decimal
arithmetic. The verifier checks line price, discount, net, tax base, tax amount,
gross, payment allocation, stock and balanced accounting. It cannot pass merely
because the two engines agree on the same incorrect total.

Oracle passes 14 of the 15 boundary checks; PostgreSQL passes all 15. The full
comparison covers 913 common base tables and leaves one unresolved field
difference, `M_InOut.ShipDate`. Its column is Oracle `DATE` versus PostgreSQL
`timestamp without time zone`. The application dictionary exposes it as a
datetime field. The supplied fraction is retained in the harness and trace;
the comparator does not normalize the loss away.

The [exact boundary harness](LightyearBoundaryTest.java) and raw evidence remain
available. This is a headless application test, not browser automation.

## Operational scope

The [operations harness](LightyearOperationsTest.java) exercises the same
fractional pricing, discount, tax, Unicode and empty-field inputs, then:

1. Ships one unit from a three-unit order. Native observations show one delivered,
   two reserved and nine on hand. A second shipment delivers the remaining two.
   One aggregate invoice bills all three; split invoicing is not part of this test.
2. Creates a one-unit credit memo linked to that invoice: net 18.00, tax 1.35,
   total 19.35. Reverses the credit through the document workflow. The reversing
   document totals -19.35; records link reciprocally and accounting cancels by
   account, accounting schema and currency.
3. Saves a customer in a transaction and injects an exception before commit.
   Rollback must leave no row. A retry commits one customer. A repeated logical
   request explicitly looks up its key and returns the existing record.
4. Holds a customer row lock while a second transaction attempts the same row.
   Each application model update adds 0.01 to a 100.00 credit limit. The second
   operation waits; both commits must survive, leaving 100.02.

Each experiment uses a fresh successor of the admitted MS84 state with the MS85
schema repairs reapplied and row multisets verified unchanged. The operational
starting state does not inherit the fractional timestamp difference.

## The failed locking API remains a finding

In the first operational trial, PostgreSQL completed the scenario. Oracle
completed the preceding business and rollback/retry steps, then rejected SQL
ending in:

```sql
FOR UPDATE FETCH FIRST 2 ROWS ONLY
```

The error was `ORA-03049`. The trial used
`Query.setForUpdate(true).firstOnly()`. Its harness, native execution record,
trace, SQL error excerpt, issue rows and final native states are retained under
`diagnostic-first-only` in the archive. It is not relabelled as a successful
run or an intentional negative-control success.

The later harness uses `Query.setForUpdate(true).list()` with a unique primary
key and verifies that exactly one row is returned. This avoids the generated
fetch clause. A result for this caller pattern does **not** repair or qualify
the `firstOnly()` combination. Upstream production application sources remain
at the recorded commit.

## Datatype mappings

The [machine-readable inventory](mappings.json) retains native declarations for
all 18,852 common base-table columns, plus one-sided columns. It finds:

- 9,393 NUMBER/numeric mappings: 8,370 have matching declared precision and scale;
  1,023 have unbounded or partial declarations.
- 2,259 Oracle DATE/PostgreSQL timestamp mappings that need explicit fractional
  second behavior checks.
- 914 text/UUID mappings, three CLOB/JSON or JSONB mappings, and three BLOB/large
  object reference mappings, alongside the text, binary and other timestamp
  families listed in the inventory.

Matching declarations do not prove equivalent inputs, rounding, collation or
constraints. The inventory records required behavioral checks and leaves
`behavior_verified_column_count` at zero. The native journeys are separate,
bounded observations; they do not promote thousands of columns into verified
coverage. UUID and JSON boundary journeys remain future work.

## Limits and next corrections

The fractional timestamp requirement remains unmet on Oracle. Preserving it
requires a reviewed storage/input contract, such as an Oracle `TIMESTAMP(6)`
mapping for this field, followed by native reruns and migration checks. Silently
truncating PostgreSQL to seconds would weaken the tested requirement.

The locking failure requires a correction to the unsupported query combination
or an explicit caller restriction. Neither a passing alternative nor a passing
cash-flow scenario makes the original path safe.

Controlled row locking is not load, deadlock, isolation-level or production
concurrency qualification. Injected pre-commit rollback is not process-crash,
network-loss, ambiguous-commit, failover or disaster-recovery qualification.
Caller-keyed retry does not prove built-in global idempotency. Credit reversal
does not cover every payment, shipment or accounting reversal. There is no
inventory valuation, all-tax-rules, maximum numeric precision or Unicode
length/collation claim.

No GCP resources were started. The [cleanup observation](cleanup.json) records
the experiment containers stopped with data retained. Credentials, private
runtime settings and database images are excluded. Content hashes bind the
evidence; they are not independent attestation or a third-party signature.

## Reproduce the offline checks

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_datatype_mappings tests.test_boundary_contract tests.test_boundary_publication -v
```

The publication checks reconstruct sealed native states, verify raw rows and
archive hashes, recompute application difference rules and business outcomes,
and ensure the timestamp and locking failures cannot acquire a passing claim.
Docker and database credentials are unnecessary for offline replay.

The affected calibration, native-evidence, milestone and publication suites ran
212 tests locally: **210 passed and two were skipped**. Milestone manifest
verification and `git diff --check` also passed. An initial sandboxed attempt
could not create Windows temporary directories; the complete validation was
rerun with the required filesystem access.

To repeat native execution, use separate fresh verified pairs for the boundary
and operational harnesses. Build the pinned iDempiere checkout, copy the desired
Java harness into `org.idempiere.test/src/org/idempiere/test/`, and select it with
`-DskipTests=false -Dtest=LightyearBoundaryTest` or
`-DskipTests=false -Dtest=LightyearOperationsTest`. Supply `PropertyFile`,
`lightyear.output` and `user.timezone=UTC` to the test JVM. The harnesses commit
business data and use fixed logical keys; use isolated disposable copies.

The datatype inventory can also be rebuilt from the captured catalogs:

```powershell
python -m lightyear_calibration.datatype_mappings `
  --oracle-catalog evidence/fractional/baseline/oracle-catalog.json.gz `
  --postgresql-catalog evidence/fractional/baseline/postgresql-catalog.json.gz `
  --output work/datatype-review
```

The output directory must be new. Exit code 3 means behavioral review remains
required; it is not a catalog capture failure.
