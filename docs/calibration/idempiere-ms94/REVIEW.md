# MS94 human source review

Review packet: `factory/idempiere/qualification-ms94/review-packet-v2.json`.
The first packet remains unchanged for equipment-01. The revision-2 packet binds
the replacement operations reference; JourneySupport and the purchasing files
are unchanged. Choosing to review the packet is not recorded as acceptance.

## JourneySupport

Read `factory/idempiere/qualification/public/JourneySupport.java`.

It serializes decimals without exponent notation, represents null with the
declared token, rejects duplicate trace keys, reads Posted with the typed Boolean
accessor, skips explicit reposting, and rolls back and closes failed transactions.
Check commit failure and rollback failure as well as the happy path.

The posting guard only controls the caller's explicit posting operation.
iDempiere's internal costing can still repost matching records and write
accounting history. Acceptance must retain this limit.

## Purchasing reference and effects rule

Read these together:

- `factory/idempiere/qualification/references/procure-to-pay/LightyearOperationsTest.java`
- `tools/qualification_procurement_scope.py`
- `tools/qualification_procurement_effects.py`
- `tools/qualification_purchasing_comparison.py`
- `factory/idempiere/qualification/proposals/purchasing-comparison-register.json`

The rule admits new costing/history rows only after checking their document
chain, product, client, organization and accounting schema, retaining old rows
and balancing the accounting-history groups. Check that an unrelated row or a
wrong organization cannot be admitted merely because it is in one of the three
extra tables. Native MCostDetail/DocManager/Doc source at application commit
`731515dcdd5278b843db33b9d3109d155b881951` supplied the MS93 call-chain evidence.

Both the reference and the proposed rule were developed after seeing MS92
candidates. The human reviewer must be someone other than that author. These
are AI-assisted development artifacts, not independent standards or proof of
unfamiliar-journey performance.

## How acceptance is recorded

After review, state your name, which review(s) you accept, and that you reviewed
the exact packet. For purchasing, also confirm you were not its author. The
operator tool can then sign that explicit statement against the packet hash.
It records your attestation; it does not independently verify your identity.

The reference remains test equipment. None of these reviews or native reference
passes count as autonomous factory successes. Stage B additionally needs all
native qualification and publication gates, then its own exact budget and source
transfer authorization.
