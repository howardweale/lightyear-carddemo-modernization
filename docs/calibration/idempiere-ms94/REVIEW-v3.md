# MS94 revised source review — candidate v3

Howard Weale's acceptance is **conditional**: resolve the attached technical
pre-review findings and present the revised packet. Neither required source
review is marked complete. Purchasing reviewer independence is unconfirmed.

The source packet is `factory/idempiere/qualification-ms94-v3/review-packet.json`.
Its hashes identify this candidate only. Native qualification and Stage B remain
blocked; these changes are not retroactively applied to earlier results.

## Findings and changes

| Finding | Implemented response | Verification and remaining gate |
|---|---|---|
| S1: rollback hides the original exception | Preserve the original exception or error; attach rollback and close failures as suppressed exceptions. Always attempt close. | Java regression exercises simultaneous body, rollback and close failures. |
| S2: binary floats can emit exponents | Refuse `Float` and `Double`; `BigDecimal` uses plain decimal text. | Java regression covers floats and a decimal supplied in exponent form. |
| S3: null sentinel/reload/private error | Reserve `SQL-NULL` for actual null; reject a literal string collision; check reload results; retain posting error as a private exception cause. | Java regression; raw application errors must not enter builder feedback. |
| S4: duplicate facts silently replaced | Ordinary `fact()` now rejects duplicates. Reference identity/status/payment lifecycle transitions use explicit `lifecycle()` calls. Added duplicate-trace negative-control source. | Duplicate-key Java regression; native negative control still required. It will be an execution failure, not credited as a judge mutation kill. |
| S5: application may internally repost | Limit retained. SDK prevents explicit caller reposting only. | No broader claim. |
| R1: own-document repost indistinguishable | Candidate must use SDK posting; direct posting/reposting and reflective dispatch are statically refused. Native history cardinality is bounded by the deterministic reference. Added a candidate that deliberately reposts its own `MMatchInv`. | Source-policy and balanced-extra-history regressions pass. Both-lane native mutation remains required. Static policy is not a malicious-Java sandbox or proof of call origin. |
| R2: partial ownership checks | Check every changed/added/removed row in all seven purchasing-added tables, including other products' cost details, purchase matches and vendor-product rows. Restrict owned vendor-product updates to declared price/date/audit columns. | Foreign-row, wrong-link and vendor-update regressions; replay of both native reference captures. |
| R3: business errors become judge errors | Explicit `BusinessViolation` assertions at business/shape checks; integrity failures retain `CalibrationError`. New envelope dispatches by exception type, never message prefix. | Regression renames a business message and gives an integrity error an old business-looking message; both retain the proper classification. |
| R4: native costing origin | Source evidence records pinned `MCostDetail`, `DocManager`, `Doc` and `MPeriod` code; deterministic reference captures establish observed cardinalities. | Independent purchasing reviewer must assess this argument. No complete dynamic call-origin proof claimed. |
| R5: purchasing line shape | Already explicit in MS94; retained in v3: exactly one order, receipt and invoice product line, with the required links. | Public selectors and shape regression retained. |
| R6: purchasing lacks shared helper | Purchasing reference now uses the same SDK as operations for posting and serialization. | Both revised references compiled against the pinned application image; fresh native controls remain required. |
| R7: accounting-schema writes | `MPeriod.isOpen` updates the accounting schema's cached period. Permit only period/audit-column changes tied to this journey's posted facts. Reject other configuration changes. | Source evidence, two-lane historical capture check and configuration mutation regression. This is a bounded cache rule, not permission to edit accounting policy. |
| P2: reused register identifier | New `idempiere-declared-purchasing-comparison-v4-ms94` identifier. Changed scopes have a proposed owner and fresh effective/review dates. | Howard Weale is proposed owner, effective 2026-09-28, review 2026-10-28. Explicit owner approval remains pending; old ownership/signatures do not approve new scopes. |

## What to review and sign

1. **Support source:** revised `public/JourneySupport.java`, both reference
   integrations and their explicit lifecycle updates. Accept the stated posting
   limit and serialization contract, or identify further changes.
2. **Independent purchasing review:** reference, owned-row scope, effects,
   typed business assertions, source policy, native history bound, register and
   source-evidence argument together. Record reviewer identity and relationship
   to the purchasing work; the reviewer must not be its author. The supplied
   pre-review additionally recommends someone who did not direct or accept the
   earlier purchasing work, ideally with iDempiere costing experience.
3. **Rule ownership:** explicitly approve or reject the new scope/version and
   proposed owner/dates. A pending proposal is not a signed admission decision.

Expected monetary results and private native captures remain outside the builder
payload. Public contracts disclose posting restrictions, permitted shapes,
ownership, transaction boundaries and structural history bounds.

## Native execution status and limitations

The original declaration stopped with insufficient rollback evidence. The second
declaration passed its first three operations controls, then stopped with an
operator-induced execution failure on slot four. During preparation of this
revision, per-attempt pinning picked up a new development module and a subsequent
edit violated its pin. The declaration's original pins were unchanged, but the
attempt's pins were not. The stopped report and captures are preserved, with 52
unstarted slots and zero model calls. Cleanup is complete.

Slot four's unchanged publication verifier refuses the implementation mismatch.
Do not label that publication replay-verified. Its original pinned source is in
the native `qualification-source` snapshot. The stopped run must not be resumed
or replaced with a success.

The new driver requires a separate execution-source snapshot and derives each
attempt's implementation inventory from its frozen declaration. Tests verify
that edits to the development root do not alter the execution copy and that
added modules in the execution copy are rejected. Signed controller-failure
records now replay exactly and reject tampering. The new driver and publication
adapter are integrated, but have not run a fresh database pair. Native success
must still be demonstrated; these tests are not source-review approvals.

The proposed next qualification retains 20 positive pairs and the 12 existing
faults, adds three own-match repost trials (39 scored negative pairs total), and
adds three duplicate-trace support controls outside the mutation-score
denominator: **62 pairs**, no generation. This is a proposal, not an authorized
replacement campaign. Its frozen plan is prepared separately after sealing this
source packet. Stage B still requires completed Stage A and a
separate concrete generation-budget/source-transfer approval.
