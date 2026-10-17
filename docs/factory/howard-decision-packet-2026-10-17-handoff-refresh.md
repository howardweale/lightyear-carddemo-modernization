# Howard decision packet — 2026-10-17-handoff-refresh

Decisions only. The measured status and failure inventories are in the current status and program verdicts.

| Order | Decision | Consequence of signing |
| --- | --- | --- |
| 1 | [intcalc-01-loader-domain-request-2026-10-17](intcalc-01-loader-domain-request-2026-10-17.json) | Accept only the pinned twin loader-domain exclusion; no kill credit. |
| 2 | [intcalc-02-appl-result-class-request-2026-10-17](intcalc-02-appl-result-class-request-2026-10-17.json) | Accept the exact APPL-RESULT class arguments, twin-scoped. |
| 3 | [intcalc-03-individual-and-compiler-request-2026-10-17](intcalc-03-individual-and-compiler-request-2026-10-17.json) | Accept the 30 individual and two compiler-proven items within twin scope. |
| 4 | [intcalc-04-threshold3-policy-request-2026-10-17](intcalc-04-threshold3-policy-request-2026-10-17.json) | Approve threshold/3 policy subject to its four typed conditions; not effective yet. |
| 5 | [intcalc-05-line189-io-request-2026-10-17](intcalc-05-line189-io-request-2026-10-17.json) | Accept the exact line 189 false-edge argument. |
| 6 | [intcalc-06-effective-threshold-last-request-2026-10-17](intcalc-06-effective-threshold-last-request-2026-10-17.json) | Make the policy effective only after all typed evidence is present. Currently refuses; signatures cannot establish non-provisional evidence. |
| Separate | [POSTTRAN line 203](posttran-io-exception-request-2026-10-16.json) | Accept only the pinned structurally unreachable false edge. The current POSTTRAN verdict lists campaign gaps and unresolved survivors separately. |
| Separate | [z/OS loader-domain proposal](intcalc-zos-loader-domain-proposal-2026-10-16.json) | Requires real loader capture and confirmation before any z/OS-facing overlay. |
| Separate | [POSTTRAN execution request](posttran-phase2-authorization-request-2026-10-16.json) | One candidate/twin comparison, only after signed proof and exact variables; not release authority. |

| Phase 2 | Plan seal | Executable commit | Signing deadline (UTC) | Days remaining |
|---|---|---|---|---:|
| POSTTRAN | `9b199d95ed391319ad45d5e316e95e927f9ad67ccb0a5cd1a53b39d189896f13` | `65bd4cd549067dd3695f4197e495cc15c9473417` | 2026-10-29T14:46:00+00:00 | 12.066 |
Evaluated at 2026-10-17T13:10:22+00:00. More than five days remain.
Compiler expiry: 2026-10-30T14:46:00+00:00. No signing or execution has been performed.

Current public retention: [evidence-retention-2026-10-16-posttran.json](evidence-retention-2026-10-16-posttran.json), [evidence-retention-2026-10-16.json](evidence-retention-2026-10-16.json). Historical packets remain unchanged.

All new requests are unsigned. Exact-final-green-commit merge approval remains separate.
