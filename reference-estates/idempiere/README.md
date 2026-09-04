# iDempiere reference estate for Oracle compatibility

This directory is the inventory-only acquisition record for the supported iDempiere release 13
baseline. The upstream checkout is pinned at commit
`731515dcdd5278b843db33b9d3109d155b881951`; its source is not copied into this repository.

The inventory establishes four bounded facts:

1. the exact upstream source and license identity;
2. the size of a reproducible static Java source-unit dependency graph and Oracle SQL surface;
3. the order-to-cash and procure-to-pay business slices selected for later analysis; and
4. the first eight Oracle semantic fixtures that must be grounded in Oracle's official sample
   schemas and examples before any translation claim is considered.

## Build the complete inventory and projection locally

```bash
git clone --depth 1 --branch release-13 --filter=blob:none --no-tags \
  https://github.com/idempiere/idempiere.git /path/to/idempiere-release-13
./oracle-reference-estate.sh build-full /path/to/idempiere-release-13
```

The tool refuses a dirty checkout or a commit other than the recorded pin. It writes the complete
inventory, compressed projection, and receipt beneath `work/reference-estates/idempiere/`, which
is ignored by Git. The complete upstream-derived structural graph is intentionally not committed.

## Control Tower projection

The Control Tower exposes this evidence as **iDempiere Reference Estate (Large)** and describes
Oracle only as the compatibility-analysis platform. This is public reference source, not an
Oracle customer, and Oracle Corporation does not sponsor or endorse this project. The exact
GPL-2.0 license is preserved at `LICENSES/GPL-2.0-only.md`.

The locally generated full fragment contains two workloads, 20 static trace scenarios, and the complete
measured Java source-unit dependency graph. The fragment contains 4,542 nodes and 36,863
relationships, including all 4,520 package-qualified Java source units and all 36,819 unique
internal Java dependencies:

- order to cash: ten documented relationships across order, shipment, invoice, payment, and
  allocation tables;
- procure to pay: ten documented relationships across purchase order, receipt, vendor invoice,
  payment, and allocation tables.

The order-to-cash workload starts from all 12 curated seeds and retains its 181-node/497-edge
depth-one scope metadata; procure-to-pay does the same for its 177-node/475-edge scope. The wider
estate graph remains searchable and navigable from any source unit. These are static source
dependencies, not runtime call observations.

Verify the committed bounded projection or generate the full projection on macOS or Linux:

```bash
./oracle-reference-estate.sh verify
./oracle-reference-estate.sh build-full /path/to/idempiere-release-13
```

Windows:

```powershell
.\oracle-reference-estate.ps1 verify
.\oracle-reference-estate.ps1 build-full C:\path\to\idempiere-release-13
```

## Evidence boundary

This is upstream static inventory, not customer source, Oracle runtime evidence, a complete
application-dictionary graph, a CloudBank mapping, translated code, behavioral equivalence,
migration completion, or production readiness. The same physical iDempiere tables support both
selected slices; `IsSOTrx` and `IsReceipt` are part of the slice definition and must not be erased.

CloudBank remains the intended modern destination and reference architecture, but no CloudBank
mapping is asserted by this inventory milestone. The SAP ASE reference estate remains separately
bounded and synthetic unless a sanitized customer or partner corpus is obtained.
