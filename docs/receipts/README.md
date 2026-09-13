# CloudBank execution receipts

AlloyDB is platform qualified for synthetic nonproduction: 29 scenarios and 8 services. Load: 5,428 requests, 0 errors, 458.91 ms aggregate p95. Exact quiesced PITR / backup restore: 507 / 451 seconds; RPO 30 seconds. Primary failover: 333 seconds. Production readiness remains false.

[AlloyDB platform receipt](alloydb-platform-20260912a/alloydb-platform.receipt.json) · [Export manifest](alloydb-platform-20260912a/publication-export.json) · [Campaign log and scope](../cloudbank-alloydb-platform-qualification.md)

MS71 is complete: Oracle to Cloud SQL and Oracle to AlloyDB each passed all 18 business scenarios with the same eight services and unchanged comparator. All execution recovery checks passed. This is bounded synthetic nonproduction equivalence; The original MS71 receipt records AlloyDB platform qualification and production readiness as false; later platform qualification is recorded separately.

[MS71 signed receipt](ms71-20260912a/ms71-alloydb-second-target.receipt.json) · [Export manifest](ms71-20260912a/publication-export.json) · [Cloud SQL comparison](ms71-20260912a/sql-managed-comparison.json) · [AlloyDB comparison](ms71-20260912a/alloydb-managed-comparison.json)

The [original Cloud SQL assembly failure](ms71-20260912a/sql-original-assembly-failure.json) and [signed reassembly record](ms71-20260912a/sql-reassembly.json) preserve the Windows line-ending correction; completed runtime observations were reused unchanged.

MS67 is complete for the bound synthetic nonproduction platform.

[Published evidence index](https://howardweale.github.io/lightyear-carddemo-modernization/receipts/) · [Final receipt](ms67-final-635689566db6425aadf6fb1fc6cf3de7/receipts/ms67-platform-receipt.json) · [Catalog](catalog.json)

The 31 original JSON files and exporter manifest are preserved byte for byte. Public verification checks file hashes, canonical content hashes and bindings. HMAC verification was performed by the operator exporter before upload; the public publisher does not have the key.

MS67 qualifies the bound synthetic nonproduction platform. Customer IdP, representative customer data and workload, customer approval, production deployment and final production readiness remain MS68.

Deterministic `factory/cloudbank/*/readiness.receipt.json` files remain admission contracts. The actual signed execution records are published here. Earlier milestones retain their own scope and flags; later qualification does not rewrite historical receipts.

Rebuild or verify these projections without cloud access:

```bash
python3 tools/publish_cloudbank_receipts.py build
python3 tools/publish_cloudbank_receipts.py verify
```
