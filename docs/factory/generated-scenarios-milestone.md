# Workstream 1.2: generated public scenarios

The deterministic campaign derives numeric boundaries from copybook PICs,
exercises rounding and cross-record boundaries, selects scenarios that add an
observed legacy outcome or kill a real compiled COBOL mutant, and adds bounded
finite-domain solver witnesses for source-bound conditions in both programs.
Every input records its generator, seed, target, source hash and input hashes.

All generated INTCALC cases run the twin, Python reference and Java candidate.
POSTTRAN runs the twin, source-derived invariants and a repeated execution.
Disagreement remains unresolved; no implementation is repaired toward another.
Control/traced outputs and return codes must match. Setup/compilation refusals
never count as mutant kills. The eight mutants modify pinned COBOL source;
the pinned INTCALC has no ROUNDED to remove, so addition is tested explicitly.

The Ubuntu artifact reports public-only and public-plus-generated coverage,
each remaining outcome, real mutant results, field diversity and comparisons.
A bounded solver miss is not an unreachability proof. This finite campaign
does not establish all-path coverage. Remaining I/O faults and domain gaps
block a claim that every reachable outcome is covered. These are engineering,
public-only, uncredited results; POSTTRAN remains provisional. Model calls: zero.

Focused generator, instrumentation and twin tests: 16 passed. Runtime figures
will be recorded from the completed Ubuntu 24.04 artifact, not inferred locally.
