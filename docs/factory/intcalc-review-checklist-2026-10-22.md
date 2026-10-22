# INTCALC six-request review — 22 October 2026

**One sitting for content review; signing is blocked. Nothing here is signed,
imported or approved.** The [machine-readable packet](intcalc-review-packet-2026-10-22.json)
lists each exact template/file hash, queue-template hash, source commit/path/hash,
embedded evidence digest, decision scope and exclusions. Original dated contracts
remain unchanged. [Existing signing order](intcalc-signing-order-2026-10-17.json).

| Order | Review the proposed decision | Boundary |
|---|---|---|
| 01 | Loader-domain legacy behavior and dependent arguments | Disposition only, not a kill or release approval. |
| 02 | The 81-member APPL-RESULT equivalence class selected by I2 | Exact selected contract; template queue hash changes when its predecessor is bound. |
| 03 | Individual equivalence arguments and compiler refusals | Review named items independently; do not count exclusions as kills. |
| 04 | Scenario threshold/3 policy | Conditional policy only; cannot make request 06 effective. |
| 05 | The line-189 I/O exception argument | Exact exception scope, not general runtime or z/OS qualification. |
| 06 | Effective threshold, last | All four real typed conditions currently unmet; this template must refuse signing. |

- Confirm the exact green PR head and packet file SHA from CI before reviewing.
- Check each linked contract's complete details and every evidence binding in the
  packet; the short labels above never replace the original contract.
- Confirm request 02 is the current [I2 selection](appl-result-contract-selection-2026-10-18.json).
  Do not import a second APPL-RESULT contract to replace a live or decided one.
- Obtain externally designated public review trust and an independently trusted
  current journal head through Howard's approved process. **Live overlap status is
  unknown here**: no installed Tower state or proof export was read.
- Before every intake, re-run the existing trusted-journal/live-queue overlap guard.
  Subset, superset and partial overlaps require a committed dated supersession
  naming every current predecessor and decision; no such clearance is invented
  by this packet. [Guard](../../src/lightyear_control_tower/factory_supersessions.py).
- Resolve request 06's real typed evidence and request 02–06 predecessor decisions.
  Retain the [ordered signing runbook](intcalc-ordered-signing-runbook.md): later
  bound requests require fresh review, CI and exact-head approval. The current
  process needs five later publication rounds and cannot promise all six
  signatures in one sitting. A shorter binding workflow needs separate approval.
- Stop on changed bytes, stale trust, an unrecorded overlap, missing evidence or
  an unverified predecessor. The historical seven-record acceptance grants no
  INTCALC execution, model spend, native claim or release authority.

CI validates this **unsigned inventory**, including the expected refusal of 06,
and tests actual disposable live/decided overlap rejection. It cannot certify
production overlap clearance or signing readiness. Any eventual signatures still
cannot turn conditional projections into actual kills or bypass the 90% kill floor
and mandatory record-level z/OS match in Howard's release instructions.
