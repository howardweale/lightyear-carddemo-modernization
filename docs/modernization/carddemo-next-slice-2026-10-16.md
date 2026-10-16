# CardDemo next slice — October 16, 2026

The new volume gate generates 100,000 unique display-digit primary keys per file from the pinned public record template, retaining the other record bytes. It tests the existing PostgreSQL browse implementation against an independent byte-sort/filter reference. Each query records result count, expected/actual hashes and elapsed time; each file records load/wall time, relation bytes and raw readback equality. Alternate-index duplicates retain primary-key ordering. Low-values, high-values and mixed letters/digits are a separate raw-key fixture because those bytes are not valid PIC 9 business data.

This is a byte-key/index volume proof. The existing 210-record typed reconstruction/control-total proof remains separate; this gate does not claim 500,000 typed reconstructions or business transactions. CI emits both receipts. No local database or workload is run.

## IMS framing limitation

The pinned public unload is `app/app-authorization-ims-db2-mq/data/EBCDIC/AWS.M2.CARDDEMO.IMSDATA.DBPAUTP0.dat`, 51,736 bytes, SHA-256 `cce00a6c86b3e02ee6d3c99723d5d5c080f9c1e1ae779591e98ba873849d3569`, from CardDemo commit `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`.

DBD `DBPAUTP0` declares 100-byte PAUTSUM0 roots and 200-byte PAUTDTL1 children. The unload length is not divisible by 100: it cannot be treated as a concatenation of those payloads. `slice.json` deliberately has no public-unload profile. The pinned data does not supply a verified utility framing specification binding record headers, segment identifiers and hierarchy. Guessing offsets from this sample would not verify framing. Public-unload import remains indeterminate until a utility specification plus a source-bound expected segment/control-total inventory is supplied and tested.

CI rebuilds the existing `readiness/ims-expiry` 40-case synthetic DL/I conformance model into a new artifact directory. It preserves the historical receipts. A passing replay proves that bounded model, not IMS runtime compatibility, the public unload parser, or a PostgreSQL DL/I adapter.

## Bounded implementation of the next slice steps

1. The BMS generator binds all 21 maps to the same upstream commit. Models preserve source lines, attribute-byte positions, field lengths, color, protection, hidden fields, initial cursor, pictures, validation and justification operands. Unknown constructs refuse. Pictures/validation/justification are retained in the model; affected input processing or dynamic picture output refuses until implemented.
2. P3 adapters add byte-record keyed read/write/rewrite/delete/browse and a two-level PostgreSQL DL/I root/child get/hold/insert/replace/delete interface. CI checks duplicate/not-found/EOF statuses, primary-key preservation, alternate order, hold consumption, orphan refusal and cascade deletion. Callers own transactions and must clear DL/I position at boundaries. No CICS locking, SSA parser, IMS checkpoint/restart or unload compatibility is claimed.
3. P4 static HTML previews use the BMS field coordinates and input/hidden/protected attributes. A headless Chromium check fills the sign-on fields, verifies password masking and records a screenshot. BLINK is deliberately presented as underline. These previews are not deployed business screens.
4. P5 begins with source-derived sign-on session cases: missing credentials, not-found, read failure, wrong password, uppercase conversion, user/admin routes, invalid AID and exit. Downstream program business actions explicitly return blocked. The CI cases are an operator-authored source model, not an independently captured CICS session oracle.

Source semantics for attribute-byte positions and field lengths: [IBM DFHMDF documentation](https://www.ibm.com/docs/en/cics-ts/6.x?topic=macros-dfhmdf). A full faithful application session and z/OS-facing equivalence remain unverified; these bounded steps do not substitute for them.

No release, signing, activation or merge authority is implied.
