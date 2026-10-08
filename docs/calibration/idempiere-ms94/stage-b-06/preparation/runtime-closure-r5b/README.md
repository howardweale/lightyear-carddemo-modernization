# B06 Tycho runtime closure r5b: exact prospective plan

Operator review; not independent attestation. Prepared only; no Docker or model calls.

Window: October 8, 2026, 10:15–11:15 PDT (17:15–18:15 UTC).
Latest start: 10:20 PDT (17:20 UTC). One network-free container, no databases or
native pairs, 2700 runtime seconds plus 600 cleanup reserve, no retry. The exact
public commit and plan must receive a fresh signed Tower decision before launch.

Plan: `a64c4a66d50bee9c55d93ba601cb7f535d44b7e03b2dcfcee068ecfc564e1dab`.
Snapshot: `d80145682eee03be0f0489b8b164b5691404cb14eee0f42f7980d83f3105b62f`
(281 files). Source commit: `a0ac8717a0fc651e035a4069ed3fc207122bab29`.

The [Tycho correction and preserved-attempt review](../tycho-runtime-r5/README.md)
replace the Maven-Surefire booter assumption with exact Tycho file capture,
closed keys, observed Equinox fork and resolved test-bundle binding. Resolution
/3 records boot_classpath and keeps /2 replay unchanged. The failed r4 native
attempt and unlaunched r5 preparation remain preserved.

Validation: 54 focused offline tests passed; after adding replay to the freeze,
20 affected tests passed again. The host Java collector compiled. All 281 frozen
hashes and imports, unchanged measured Maven arguments, and a synthetic /3
producer plus independent replay passed from this immutable snapshot. Synthetic
fixture keys were generated in memory only; no production authority was opened.
No native qualification or generated-class provenance is claimed by these checks.

The original failed attempt lacks target/surefire.properties and a successful
runtime receipt, so it cannot be upgraded to /3. This new run must supply those
bytes. No old window/decision is reusable. The five-path census, qualification
and measurement remain separate later gates.
