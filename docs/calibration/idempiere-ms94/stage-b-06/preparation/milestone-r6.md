# B06 qualification and pinned transport milestone — r6

October 5, 2026. Operator review; not independent attestation.

This milestone records the preparation delivered in [PR #257](https://github.com/howardweale/lightyear-carddemo-modernization/pull/257)
and [PR #258](https://github.com/howardweale/lightyear-carddemo-modernization/pull/258).
The implementation commits are `159897376007c6d6b70fbac1bb96cd390b2bfb0f`
and `e0570be875eb073d8955ce2773388576c6b1ed86`, respectively. Publication and
merge do not authorize a Docker run, native qualification or model invocation.

## Delivered

The [qualification preparation](execution-r6/README.md) seals complete private
inputs for 135 slots: J1 55, J2 41 and J3 39. Public manifests contain hashes
only. A separate three-slot J1 smoke draft covers the retained reference, an
invoice-line mutant and direct candidate-runtime-exception delivery. It receives
no full-qualification credit. The four revised offline-catalog-r4 sources are
selected by hashes and an explicit applicability field, not editorial reason text.

Qualification execution now requires a verified Control Tower operator decision
bound to the plan, snapshot, public commit and approved Docker window. The Tower
key must differ from the campaign key. Cross-engine document-label disagreement
produces empty feedback and equipment suspicion, including in offline delivery
and replay tests. No native qualification has run in this increment.

The [pinned transport](transport-r6/README.md) uses Codex 0.160.0 at
`C:\Program Files\Lightyear\Codex\0.160.0\codex.exe`, outside desktop updates.
The plan binds its bytes, path, account identity, arguments and implementation.
The actual dedicated-account probe passed on its fifth fresh attempt. Empty-stdin
`codex exec` rejected the absent prompt before model protocol. Separate app-server
commands under that same executable proved the allowed-file positive control,
missing-file control and native access-denied results for tools and private files.

Account-scoped Windows Filtering Platform controls denied other-program IPv4
and IPv6 connections with WSAEACCES, while host listener controls succeeded.
The probe also blocked Codex itself; authenticated external model connectivity
was not tested. Combined signed transport admission passed. Read-only inspection
confirmed the account disabled, recorded processes absent, filters and sublayer
absent, and the temporary firewall rule removed.

## Bindings and validation

| Artifact | SHA-256 |
|---|---|
| J1 assembly v6 | `287bff9bc4bfc10d42f69fe2f127f83823676e2c8428637b08032ed7e131514c` |
| J2 assembly v6 | `b144e502b832f377ea090c9ce2ca3de294f342dd46eb58df7c2f52774f113815` |
| J3 assembly v6 | `842c6a3f86bdbf291971534bd23c77aead83340fee0e809631c2825e9b7b4ef4` |
| Pinned Codex binary | `4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01` |
| Transport plan | `5785ec68eb60910bafae415933555dede2caa902b2701234db7fa340debdfe88` |
| Signed pinned-exec proof content | `0b7d70d5bdb87143f73e52caad7229cfed45217ab2ebe8cc46784a431eccd548` |
| Signed public probe summary content | `d515c79440d562d66ade98d55519935d8dfee4e6e8a6b9069cd148b3c9c94049` |

PR #257 preparation passed 118 B06 offline tests and 34 Tower/documentation
regressions. PR #258 preparation passed 116 B06 regression tests and nine
documentation checks. These are separate branch results, not additive coverage
or native qualification. GitHub checks and merge outcomes are recorded on the
linked PRs; initially canceled #257 jobs reported unavailable hosted runners
and were retried without changing the tested implementation.

The successful host probe took 13.541 seconds including cleanup
(20:46:56.972–20:47:10.513 UTC). Earlier elevation, WFP-weight, protected-HOME
variable and CLI-argument-order failures remain preserved with their observations
and cleanup evidence. Raw proofs, account identifiers, private values, reference
sources and captures remain local. Zero model calls, zero Docker runs and zero
native pairs occurred in this r6 increment.

## What remains against core-status items 1–5

| Item | Remaining admission work |
|---|---|
| 1 — Native journey adapters | Demonstrate J2/J3 entry, complete captures, reconciliation, judge, clocks and cleanup in approved native runs. J1 predicates remain unchanged. |
| 2 — Posting-origin attribution | Qualify the observer and independent replay on both engines with all declared posting controls. Synthetic fixtures confer no native qualification credit. |
| 3 — Executable qualification | Capture unambiguous loaded Tycho/OSGi class identities, convert the sealed assemblies into immutable executable plans, obtain exact group/window decisions, then execute and audit J1/J2/J3. |
| 4 — Measurement controller | Complete the model/MCP transport adapter and require full `admit_transport`; the older OS-only `builder_gate` alone is insufficient. Complete native evidence and metric integration. |
| 5 — Preflight and launch | Run the approved immutable three-journey zero-model preflight, verify replay/cleanup and Tower behavior, then freeze preregistration, costs, launch window and runbook for approval. |

The runtime-resolution Docker proposal is still unapproved: commit `1598973`,
October 5, 20:00–20:55 PDT, one pinned-image container, no database or native pair.
Its 45-minute container limit reserves ten minutes for cleanup. If that window
passes, obtain a new explicit window rather than executing late. J1 smoke is also
only a draft. No native pair may start on the strength of these PR merges.

October 17 remains a conditional executable-freeze go/no-go; readiness is
currently no-go. B04 remains void. B05 frozen evidence, `work/ms94`, template-r1
and J1 predicates are unchanged. Historical failures remain separate and intact.
