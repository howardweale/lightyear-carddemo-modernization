# AUTHFRDS data-modernization proof cell

This bounded v0.19.2 vertical slice translates the AWS CardDemo Db2 for z/OS `CARDDEMO.AUTHFRDS` contract to PostgreSQL and Oracle while retaining source lineage and explicit evidence gaps.

## What is proven

- deterministic parsing of the 26-column Db2 DDL, composite primary key, unique index, DCL, and COPAUS2C embedded INSERT/UPDATE SQL;
- a target-neutral canonical data model plus PostgreSQL 16 and Oracle Database 26ai Free adapters;
- fixtures covering CP037 EBCDIC, packed and zoned decimal, dates, nulls, and fixed-width text;
- fail-closed exact live comparisons for column metadata, constraints, index order, normalized rows, checksums, queries, commit, and rollback;
- an HMAC-signed **development** receipt whose signer is intentionally labeled as a fixture;
- an on-demand Docker PostgreSQL proof using no network, a read-only root, dropped capabilities, and ephemeral tmpfs storage;
- an Oracle Free proof using no network or published ports, ephemeral credentials, dropped capabilities, and an honestly recorded writable-root exception required by the database image;
- a multi-target aggregate receipt that fails unless both target receipts pass.

## Run

macOS/Linux:

```bash
./data-modernization.sh verify /path/to/aws-carddemo
./data-modernization.sh live-postgres
./data-modernization.sh live-oracle
./data-modernization.sh live-all
```

Windows PowerShell:

```powershell
.\data-modernization.ps1 verify C:\path\to\aws-carddemo
.\data-modernization.ps1 live-postgres
.\data-modernization.ps1 live-oracle
.\data-modernization.ps1 live-all
```

For a customer-controlled signature, set `FACTORYDARK_DATA_EQUIVALENCE_KEY` and run `sign`.
After `live-all`, the command signs the multi-target aggregate; otherwise it signs the PostgreSQL
receipt. Never commit that key.

## Honest boundary

The Oracle runner defaults to the official locally built `oracle/database:23.26.1-free` image. Follow
Oracle's official container-image instructions and accept the applicable license before running it.
The image supports Oracle Database Free on ARM64, but startup is materially slower than PostgreSQL.

`production_ready` remains `false`. The cell has not observed a live Db2 catalog, customer data,
z/OS transaction behavior, CDC, or cutover. The current source lineage is COBOL-specific for the
AUTHFRDS slice; PL/I lineage is not claimed. Oracle empty-string semantics also require live data
profiling. These are v0.20/v0.21 evidence requirements, not inferred claims.

## Scope confirmation

| Capability | v0.19.2 status |
|---|---|
| Parse Db2 DDL, DCL and bounded embedded SQL | Passed for AUTHFRDS/COPAUS2C; not a general Db2 parser |
| Graph tables, columns, indexes, constraints and SQL | Passed for this vertical slice |
| Connect source logic to reads/writes | COBOL paragraph lineage passed; PL/I not present in this slice |
| Target-neutral canonical model | Passed for AUTHFRDS |
| PostgreSQL and Oracle generation | Passed deterministically |
| EBCDIC, packed/zoned decimal, dates, nulls, fixed width | Covered by representative fixtures |
| Live target containers | On-demand; receipt exists only after each target actually runs |
| Exact schema/data/query/transaction comparison | Implemented fail-closed for both targets |
| Signed equivalence | Development HMAC and customer-key signing mechanism; no production key is shipped |
| Control Tower lineage/gaps/equivalence | Side-by-side target projection implemented |
