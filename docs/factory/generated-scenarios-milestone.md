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

## Measured Ubuntu result

[Run 38100613787](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38100613787) completed successfully on `88dbf5542eba50922078b89609b899c59a997c74`.

| Program | Public-only outcomes | Public + generated | Real legacy mutants killed | Remaining outcomes |
|---|---:|---:|---:|---:|
| CBACT04C | 51/94 | 64/94 | 5/5 | 30 |
| CBTRN02C | 63/110 | 73/110 | 3/3 | 37 |

[Measured metrics, all mutant kills and every remaining source condition](generated-runtime-coverage.json). Thirty-seven deterministic cases were attempted. The duplicate indexed-category case is refused by the adapter before legacy execution; it receives no branch or mutant-kill credit. It still runs the Python/Java comparison and remains unresolved. The first campaign failure exposing that admission behavior is preserved in run38100353939.

INTCALC missing disclosure/account/xref and duplicate-category cases remain explicit unresolved refusal/comparison records. POSTTRAN duplicate IDs fail the independent ambiguity invariant and remain unresolved. No autorepair or promotion occurred. All eight source mutants compiled and were killed by generated inputs, including ROUNDED addition and scale truncation. The original source has no ROUNDED to remove.

**Acceptance limitation:** complete reachable-path coverage has not been established. The remaining30/37 outcomes are individually listed as not solved with source conditions; none is called unreachable without proof. Runtime I/O fault paths need a separately controlled experiment. These metrics are not a 100% coverage or production-release claim.

## Integration cleanup regression

After PR311 merged, the updated PR312 integration head exposed an existing
macOS worker-exit race in Control Tower CI (run 38108080917). A process-group
signal could return PermissionError while enforcing the output cap, masking
the original worker-output-limit refusal. Cleanup now suppresses that signal
error only after a fresh poll confirms the worker has exited, then reaps it.
Permission denial for a live worker still fails. The output and timeout limits
are unchanged. Two deterministic regressions cover both outcomes; the original
failed run remains evidence and is not relabeled successful.
