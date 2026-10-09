# B06 runtime closure r4: prospective plan

Operator review; not independent attestation. No runtime result is claimed.

Window: October 8, 2026, 09:15-10:15 PDT (16:15-17:15 UTC); latest start 09:20 PDT. One network-free container, 2,700 runtime seconds plus 600 seconds cleanup reserve, no retry, no databases, no native pairs and zero model calls. A fresh exact Tower decision is required before Docker. No automatic extension.

This follows the passed inventory-only r1 report `2b3ad80a49aa51eef3357589837f19a1becf3259a58096b5d270c6eb8e817adc` and catalogue `de870b5a9b3b423535ecef007cdb4f67fbdf285cd26493bda400cdc34960040b`. Its public-key signature was verified. Inventory did not execute a target JVM and is not runtime qualification.

The plan binds the exact image and Java executable. It starts the separately authorized no-database Tycho/Equinox test JVM, records effective configuration and booter classpath, measures observed runtime artifacts and extracts pinned runtime modules with jimage. Loaded targets include NodeTestTask and ExecutionListenerAdapter. Actual commands, class identities, observations and failed output are retained locally. Cleanup touches only the owned container; frozen hashes are checked before success is signed.

Source commit: `0997d854b8081ecca3d77cfc4afd549cf32959a5`.
Snapshot: `4560e88525a13273e6915fccc339d06da494d13de032a47dc614f4caa4356721` (275 files).
Plan: `ec0bd6ce0e03d862de98d141f2c8a8aa2954d1834c6be1ff78c01a12327ed9ea`.

The launcher now binds the Tower request envelope hash as well as plan, snapshot, public commit and window. The real inbox and signed-decision verifier are tested together. Validation: 38 offline tests passed; snapshot hashes, frozen imports and measured launch arguments checked from the immutable directory. Zero Docker/model calls. An earlier test command named one nonexistent module; the corrected suite passed. An initial inventory check used the unsigned-contract verifier on a signed envelope; the correct envelope verifier passed. Neither preparation error started a runtime or changed evidence.

Public payload: code and hash-only preparation metadata. Runtime artifacts, captures, class blobs, credentials and keys stay local. Earlier r10 failure, rejected r11 and frozen evidence remain unchanged.

Remaining gates: scoped extraction/provenance proof and pinned-image observer overhead; corrected pool-rule approval; five-path census (J1 three paths plus J2/J3 retained, both engines); native qualification and measurement preflight. This request authorizes none of the later native/census/measurement runs. J1 predicates and expected outcomes are unchanged.
