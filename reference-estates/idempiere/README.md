# iDempiere Oracle reference-estate inventory

This directory is the inventory-only acquisition record for the supported iDempiere release 13
baseline. The upstream checkout is pinned at commit
`731515dcdd5278b843db33b9d3109d155b881951`; its source is not copied into this repository.

The inventory establishes four bounded facts:

1. the exact upstream source and license identity;
2. the size of a reproducible static Java source-unit dependency graph and Oracle SQL surface;
3. the order-to-cash and procure-to-pay business slices selected for later analysis; and
4. the first eight Oracle semantic fixtures that must be grounded in Oracle's official sample
   schemas and examples before any translation claim is considered.

## Rebuild the inventory

```bash
git clone --depth 1 --branch release-13 --filter=blob:none --no-tags \
  https://github.com/idempiere/idempiere.git /path/to/idempiere-release-13
python3 tools/inventory_idempiere_reference.py \
  --source-root /path/to/idempiere-release-13
python3 tools/inventory_idempiere_reference.py \
  --source-root /path/to/idempiere-release-13 --verify
```

The tool refuses a dirty checkout or a commit other than the recorded pin.

## Control Tower projection

The Control Tower exposes this evidence under the operator-facing estate name **Oracle Customer
(Large)**. The upstream name remains in this provenance directory, the exact source pin, and the
GPL-2.0 license record; it is not used as the customer/company label.

The generated fragment contains two workloads and 20 static trace scenarios:

- order to cash: ten documented relationships across order, shipment, invoice, payment, and
  allocation tables;
- procure to pay: ten documented relationships across purchase order, receipt, vendor invoice,
  payment, and allocation tables.

Build or verify the projection on macOS or Linux:

```bash
./oracle-reference-estate.sh build
./oracle-reference-estate.sh verify
```

Windows:

```powershell
.\oracle-reference-estate.ps1 build
.\oracle-reference-estate.ps1 verify
```

## Evidence boundary

This is upstream static inventory, not customer source, Oracle runtime evidence, a complete
application-dictionary graph, a CloudBank mapping, translated code, behavioral equivalence,
migration completion, or production readiness. The same physical iDempiere tables support both
selected slices; `IsSOTrx` and `IsReceipt` are part of the slice definition and must not be erased.

CloudBank remains the intended modern destination and reference architecture, but no CloudBank
mapping is asserted by this inventory milestone. The SAP ASE reference estate remains separately
bounded and synthetic unless a sanitized customer or partner corpus is obtained.
