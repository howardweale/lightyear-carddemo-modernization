# CloudBank execution receipts

**Published native Oracle 26ai–AlloyDB PostgreSQL result: 260/260 matching case pairs across 13 datatype families and 65 bounded behaviours.** The successful run has 260 source and 260 target observations. Overlapping earlier campaigns are deduplicated. The separate MS51 readiness snapshot's `native_executed_case_count: 0` does not aggregate these receipts and is not a project-wide execution total.

[Native campaign evidence](oracle26ai-alloydb-types260-20260917/README.md) · [Original manifest](oracle26ai-alloydb-types260-20260917/manifest.json) · [Evidence and count scopes](../oracle-native-evidence.md)

AlloyDB is platform qualified for synthetic nonproduction: 29 scenarios and 8 services. Load: 5,428 requests, 0 errors, 458.91 ms aggregate p95. Exact quiesced PITR / backup restore: 507 / 451 seconds; RPO 30 seconds. Primary failover: 333 seconds. Production readiness remains false.

[AlloyDB platform receipt](alloydb-platform-20260912a/alloydb-platform.receipt.json) · [Export manifest](alloydb-platform-20260912a/publication-export.json) · [Campaign log and scope](../cloudbank-alloydb-platform-qualification.md)

**Current AlloyDB status: `alloydb_platform_qualified: true`.**

MS71 is complete: Oracle to Cloud SQL and Oracle to AlloyDB each passed all 18 business scenarios with the same eight services and unchanged comparator. All execution recovery checks passed. This is bounded synthetic nonproduction equivalence. The original MS71 receipt covers equivalence only and retains its historical false qualification flag. Current AlloyDB platform qualification is true in the separate 29-scenario platform receipt; production readiness remains false.

[MS71 signed receipt](ms71-20260912a/ms71-alloydb-second-target.receipt.json) · [Export manifest](ms71-20260912a/publication-export.json) · [Cloud SQL comparison](ms71-20260912a/sql-managed-comparison.json) · [AlloyDB comparison](ms71-20260912a/alloydb-managed-comparison.json)

The [original Cloud SQL assembly failure](ms71-20260912a/sql-original-assembly-failure.json) and [signed reassembly record](ms71-20260912a/sql-reassembly.json) preserve the Windows line-ending correction; completed runtime observations were reused unchanged.

MS67 is complete for the bound synthetic nonproduction platform.

[Published evidence index](https://howardweale.github.io/lightyear-carddemo-modernization/receipts/) · [Final receipt](ms67-final-635689566db6425aadf6fb1fc6cf3de7/receipts/ms67-platform-receipt.json) · [Catalog](catalog.json)

The 31 original JSON files and exporter manifest are preserved byte for byte. Public verification checks file hashes, canonical content hashes and bindings. HMAC verification was performed by the operator exporter before upload; the public publisher does not have the key.

MS67 qualifies the bound synthetic nonproduction platform. Customer IdP, representative customer data and workload, customer approval, production deployment and final production readiness remain in the customer-production backlog.

Deterministic `factory/cloudbank/*/readiness.receipt.json` files remain admission contracts. The actual signed execution records are published here. Earlier milestones retain their own scope and flags; later qualification does not rewrite historical receipts.

Rebuild or verify these projections without cloud access:

```bash
python3 tools/publish_cloudbank_receipts.py build
python3 tools/publish_cloudbank_receipts.py verify
```
