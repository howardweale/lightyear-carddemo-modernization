# PR273 native review validation — October 8 UTC

Operator review; not independent attestation. Zero model calls. All database work ran only on the approved dedicated Linux VM; no local Docker commands were used.

The head executor completed all 108 declared paired seed cases across 43 named typed procedures and 26 trap families: 57 matches on compared observables and 51 divergences. This is **not** 57 equivalence successes. The original terminal report is preserved with qualification false: finalization detected a mismatch between generated display labels and the old case-label convention.

A versioned offline finalizer now binds each case to signed procedure/setup assets, actual argument hashes, variant and repeat. It rejects changed report bindings, missing cases and duplicate cases. Replaying the same preserved pairs leaves ten procedure/variant outcomes unresolved; no verdict or old report was changed:

- Conditional or unresolved result origin: catch-retains-prior-work, ci-unique, xact-abort, and both cursor-fetch-status variants.
- Dynamic SQL/callee-result closure: dynamic-parameter-binding reference.
- Unresolved ordering key: both null-and-collation-order variants.
- Unresolved native dependency edges: scope-identity-trigger and set-trigger references.

These are explicit limitations, not exemptions. Full-corpus qualification and mLogica readiness are not claimed. The two blocking false-acceptance paths are closed by refusal when ordering/dependency origin is unresolved, and by typed table-value contracts; unresolved inputs cannot become equivalent through a corpus label or float policy.

## Evidence and preservation

See [the hash-only audit summary](native-review-r2-audit.json). Full native report content hash: 7c1dbfbb406a1de224bb4de7f213b6804e641eea75c7f4c7ac169cce3e81e9d9. Native duration: 345.989376 seconds. Independent replay across all five attempts took 3.524831 seconds and verified 255 available pair archives, plus signed report/file bindings. Read-only owned-label checks found no containers, networks or volumes for any of the five attempts.

Four earlier failed attempts remain preserved: ScriptDom type spacing, the datetime2 type-name guard, parameterized RAISE NOTICE syntax, then RAISE EXCEPTION syntax. All owned cleanup passed. The corrected public fixtures also use distinct amount parameter names and an explicit null output-slot contract. Historical parameterless corpus assets and older evidence remain unchanged.

The nine fresh coverage-v2 controls independently passed earlier; that demonstrates collector discrimination, not corpus equivalence. The handler-hit control's business divergence remains recorded. Its native report is 4955af4748481925956012a236a198783d0290369f44ce6b19ee6c204bc70e20, with the separate [coverage audit](coverage-head-r3-audit.json).

## Implementation boundary

The runner calls typed boundary generation, preserves every shrinking probe and records minimal-case hashes in its run report. Single-pair verdicts correctly retain one executed case; a later reduction does not rewrite their signatures. Float tolerance requires a verified Tower decision bound to corpus, source/target assets and calling convention; missing authority, stale proof or changed policy fails before containers. No live float-tolerance decision was fabricated. Unordered-choice, row-count suppression and unknown effects cannot be waived by this policy.

Native module catalogues retain all user procedures, functions, views, triggers and synonyms before and after invocation. Unreadable/dynamic modules, cross-database or late-bound edges and unresolved synonym targets are unsupported. Capturing a catalogue is not a claim that arbitrary dynamic SQL has been resolved.


## Generated boundaries and shrinking

The separate public integer-division integration run completed 92 fresh pairs without a fatal error: 54 observable matches and 38 divergences. Native time: 289.061085 seconds; independent replay: 0.930938 seconds. All 92 signed pair archives replayed, and read-only owned-label checks confirmed cleanup. Report content hash: e0fca8e8e5a17b37130653c3c7da3c650b9738404475bbe4b9f3b1a622999e4a.

Case origins: {'proposed-not-executed': 52, 'shrink-probe': 40}. There were 20 recorded bounded reductions, 40 native shrink probes, and 18 reductions with at least one failure-preserving step. The source label proposed-not-executed records the generator's original proposal status; each retained native record separately proves execution and replay. This subset run makes no full-corpus qualification claim. See [the safe audit summary](native-generated-r1-audit.json).
