# CloudBank customer PostgreSQL mapping

Milestone 55 selects the pinned CloudBank `customer` service as the first database transformation
workcell. It maps `CUSTOMER.CUSTOMERS` to PostgreSQL 16 and qualifies the bounded database behavior
needed by MS #56. It does not refactor or run the Spring application.

The mapping covers all seven columns, the primary key, Liquibase order, synthetic data, Oracle
empty-string normalization, Oracle `DATE`/`SYSDATE`, case-sensitive fragment searches, and CRUD
commit/rollback behavior. The compatibility ledger explicitly preserves two wider boundaries:

- `ROLE` exists in the Oracle schema and bootstrap data but is absent from the JPA entity. The
  target column is preserved, while application equivalence remains blocked until MS #56.
- The upstream demonstration password values are not copied into committed fixtures, output, or
  receipts. Only synthetic non-credential values are used.

## Static verification

```bash
./cloudbank-customer-postgresql.sh verify
./cloudbank-customer-postgresql.sh verify-source ../cloudbank-upstream
```

## Native PostgreSQL proof

The native action requires the admitted MS #54 Oracle receipt and the same evidence key used to
sign it. Pull the pinned target image and capture its immutable image ID:

```bash
docker pull postgres:16-alpine
POSTGRESQL_IMAGE_ID="$(docker image inspect --format '{{.Id}}' postgres:16-alpine | sed 's/^sha256://')"

./cloudbank-customer-postgresql.sh native-postgresql \
  ../cloudbank-upstream \
  work/cloudbank-oracle-runtime.receipt.json \
  "$POSTGRESQL_IMAGE_ID" \
  work/cloudbank-customer-postgresql.receipt.json \
  operator-id

./cloudbank-customer-postgresql.sh verify-receipt \
  work/cloudbank-customer-postgresql.receipt.json
```

The container runs without a network, with a read-only root filesystem, dropped capabilities,
bounded CPU/memory/PIDs, and tmpfs database storage. Receipts retain hashes and normalized markers,
not raw output, credentials, signing keys, or production data.

Passing the native proof qualifies this bounded database mapping. It does not prove Spring/JPA,
HTTP/API, authorization, concurrency, CDC, cutover, whole-CloudBank, or production equivalence.
