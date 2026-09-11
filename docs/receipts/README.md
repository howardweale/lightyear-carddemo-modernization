# CloudBank execution receipts

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
