# CardDemo COBOL decision inventory

Source revision: `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`.

Inventoried **44 programs**, **1,423 source decisions** and **3,605 source outcome slots** under `cobol-source-outcomes-v1`.

This is a source-level test-planning denominator. Runtime coverage is **unobserved**, and compiled branch completeness is **not claimed**.

| Decision kind | Decisions |
| --- | ---: |
| altered-go | 1 |
| at-end | 1 |
| evaluate | 193 |
| if | 1,161 |
| invalid-key | 12 |
| perform-until | 54 |
| search | 1 |

## Scope and open boundaries

- Fixed format uses columns 7-72 and eight-column tab stops; positions use expanded columns. Compiler source-format settings still require reconciliation.
- Source outcomes include syntactic alternatives; reachability and compiler-generated branches are not proved.
- Each EVALUATE WHEN is a selection alternative, including alternatives sharing a body; missing OTHER adds no-match.
- SEARCH counts declared WHEN selections and exhaustion, not internal binary-search comparisons.
- COPY expansions are per inclusion; unresolved compiler libraries and embedded CICS/SQL/IMS behavior are listed.
- Compound conditions are one decision: this is not MC/DC or path coverage.
- The denominator must be reconciled with compiler listings, options and deployed load modules before a z/OS coverage claim.

| Issue | Count |
| --- | ---: |
| missing-copybook | 62 |

## Per-program denominator

| Program | Decisions | Outcomes |
| --- | ---: | ---: |
| app/app-authorization-ims-db2-mq/cbl/CBPAUP0C.cbl | 21 | 45 |
| app/app-authorization-ims-db2-mq/cbl/COPAUA0C.cbl | 32 | 75 |
| app/app-authorization-ims-db2-mq/cbl/COPAUS0C.cbl | 38 | 100 |
| app/app-authorization-ims-db2-mq/cbl/COPAUS1C.cbl | 23 | 55 |
| app/app-authorization-ims-db2-mq/cbl/COPAUS2C.cbl | 3 | 6 |
| app/app-authorization-ims-db2-mq/cbl/DBUNLDGS.CBL | 11 | 22 |
| app/app-authorization-ims-db2-mq/cbl/PAUDBLOD.CBL | 19 | 38 |
| app/app-authorization-ims-db2-mq/cbl/PAUDBUNL.CBL | 13 | 26 |
| app/app-transaction-type-db2/cbl/COBTUPDT.cbl | 8 | 24 |
| app/app-transaction-type-db2/cbl/COTRTLIC.cbl | 109 | 277 |
| app/app-transaction-type-db2/cbl/COTRTUPC.cbl | 65 | 239 |
| app/app-vsam-mq/cbl/COACCT01.cbl | 17 | 35 |
| app/app-vsam-mq/cbl/CODATE01.cbl | 15 | 30 |
| app/cbl/CBACT01C.cbl | 23 | 46 |
| app/cbl/CBACT02C.cbl | 12 | 24 |
| app/cbl/CBACT03C.cbl | 12 | 24 |
| app/cbl/CBACT04C.cbl | 47 | 94 |
| app/cbl/CBCUS01C.cbl | 12 | 24 |
| app/cbl/CBEXPORT.cbl | 21 | 42 |
| app/cbl/CBIMPORT.cbl | 16 | 36 |
| app/cbl/CBSTM03A.CBL | 25 | 58 |
| app/cbl/CBSTM03B.CBL | 13 | 29 |
| app/cbl/CBTRN01C.cbl | 36 | 72 |
| app/cbl/CBTRN02C.cbl | 53 | 106 |
| app/cbl/CBTRN03C.cbl | 44 | 90 |
| app/cbl/COACTUPC.cbl | 285 | 705 |
| app/cbl/COACTVWC.cbl | 34 | 101 |
| app/cbl/COADM01C.cbl | 10 | 30 |
| app/cbl/COBIL00C.cbl | 19 | 52 |
| app/cbl/COBSWAIT.cbl | 0 | 0 |
| app/cbl/COCRDLIC.cbl | 72 | 196 |
| app/cbl/COCRDSLC.cbl | 38 | 111 |
| app/cbl/COCRDUPC.cbl | 81 | 233 |
| app/cbl/COMEN01C.cbl | 12 | 37 |
| app/cbl/CORPT00C.cbl | 26 | 61 |
| app/cbl/COSGN00C.cbl | 7 | 17 |
| app/cbl/COTRN00C.cbl | 38 | 110 |
| app/cbl/COTRN01C.cbl | 10 | 24 |
| app/cbl/COTRN02C.cbl | 27 | 91 |
| app/cbl/COUSR00C.cbl | 37 | 110 |
| app/cbl/COUSR01C.cbl | 7 | 22 |
| app/cbl/COUSR02C.cbl | 18 | 46 |
| app/cbl/COUSR03C.cbl | 13 | 32 |
| app/cbl/CSUTLDTC.cbl | 1 | 10 |

Inventory SHA-256: `7e6cce0739adf97c685e7d17203279c82d26e347ba31a0bdea7ffee43d54fde5`

The JSON inventory contains every outcome ID, physical source location, COPY inclusion chain, source hash, issue and external boundary. No runtime hits have been inferred from this inventory.
