# B06 PR241 review fixes and qualification drafts

Operator review, not independent attestation. Zero model calls, zero Docker
commands and zero native qualification pairs in this increment. B05, work/ms94,
template-r1 and J1 implementation files are unchanged. This branch starts at
`538c0829766ca3d0d0611a46f7a06bbbaba2eba5` and carries forward the observer
preparation subsequently published in PR242 before applying these review fixes.

## Review findings 1–3

The B06 candidate boundary validates trace identities, UUIDs, saved/status fields
and the numeric fields consumed by the J2 judge. Missing/malformed trace files
and invalid fields produce typed business failures. Only the application
watchdog expiry becomes `candidate-timeout`; controller deadlines, cancellation,
unreadable evidence and unexpected verifier exceptions retain their infrastructure
classification. Cleanup failure overrides a candidate timeout. No arbitrary
`ValueError` from the native verifier is reclassified as candidate error.

Business rejection records bind the plan, authorization, entry, clock, all-table
captures, executions and trace bytes actually read. They list completed, failed
and unexecuted gate stages. An early rejection has `full_entry_replayed=true`
only after entry replay, and **`complete_gate_replayed=false`**. Later archive
audits must reproduce that executed prefix and verdict; they must not invent
completion of downstream checks.

Each native plan must bind ordered clock stages and an exact role/name/image
runtime inventory. Extra/missing/reordered samples, duplicate containers, a
wrong container name or an image assigned to the wrong role fail with typed
evidence errors. Observer containers are included and inspected. There is no
literal five-container admission rule.

## Posting-origin preparation

The external JDI collector now also observes the actual lock UPDATE called by
the pinned `Doc.post`, including its arguments, integer result and executed
bytecode identity. The host SQL probes read the same document while the JVM is
suspended. Independent replay checks the event chain, call/return/unwind stack,
bound class bytes, exact query set and readback hashes.

The new cause derivation requires an observed successful candidate `PO.lock`,
a native `Processing=N` to `Y` transition, a same-document support call, the exact
non-forced/non-repost lock UPDATE returning zero, and an escaping support failure.
Caught SQL/JDBC or VM faults defeat attribution. It does not treat the processing
flag as a database row lock. Support-origin, outside-origin and wrong-document
actions do not establish candidate ownership.

The prior-post control deliberately expects no posting failure when `postOnce`
skips an already-posted document. It must not be reinterpreted as successful
fault attribution. Synthetic Oracle and PostgreSQL streams test all six requested
control families. These are **unit fixtures, not native qualification evidence**.
The production replay entry point authenticates the native entry and collector
receipt before deriving a cause, and still reports `attribution_qualified=false`
with no production feedback until native qualification and delivery integration
are admitted. The old assertion-based attribution test fixtures confer no credit.

The revised Java observer passed a host JDK21 syntax compilation. It has not been
compiled in the target image or attached to a native JVM during this increment.
All earlier reference/observer compilation records remain historical and unchanged.

## Proposed fixed qualification schedules

| Draft | Fresh pairs | Maximum engine executions | Estimated serial Docker time |
| --- | ---: | ---: | ---: |
| [J1 requalification](j1-qualification-draft.json) | 55 | 110 | 9.17–18.33 h |
| [J2 procurement](j2-qualification-draft.json) | 41 | 82 | 6.83–13.67 h |
| [J3 materials](j3-qualification-draft.json) | 39 | 78 | 6.5–13 h |
| Total | 135 | 270 | 22.5–45 h |

Each includes ten retained references, applicable business/type mutants and
posting-origin controls on both engine formats. J1 additionally preserves the
five equivalent, three alternate-invoice and eighteen dated A2 delivery controls.
J2/J3 add trace, timeout, runtime-inventory and clock-sample boundary controls.
Genuine equipment faults have two separate slots, targeting Oracle and PostgreSQL;
a terminated first engine must not be represented as a completed second engine.
Controls never count as cohort successes. Any unexpected result stops the
qualification; preserve every attempted and unstarted slot with no replacements.

All three plans bind these images:

- Application: `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`
- Oracle: `sha256:96c4bda58cd8a8dfda586b2d83a2eb2a3e9f28fda0f1915d3fd758c890dc02b7`
- PostgreSQL: `sha256:6820c00e2aa9770bea672bc036646175d2bb5f5ce7343dc51e1dba5eb1d3da7f`

[Source bindings](source-bindings.json) contain reference/mutant hashes only.
Private J2/J3 candidate sources were prepared locally; their new variants are
uncompiled. J1 October reference hashes are reconstructed in memory using the
existing dated/calendar transformations; no J1 file was written or changed.
Expected diagnostic dispositions are prospective, not observations.

The estimate assumes 10–20 minutes per fresh pair; observer overhead has not been
measured. Offline compilation, independent archive replay and pauses are separate.
The proposed qualification group has a 96-hour cap and real clocks. Its conservative
guard refuses any slot when real UTC plus 96 hours reaches November 1 UTC. The
calculated latest start is October 27, 23:59:59 UTC (16:59:59 PDT), subject to the
approved Docker window. No Docker work may overlap the CardDemo intake from
October 5. Plan review does not grant per-run Docker approval.

**These are review drafts, not executable plans or native-run authorizations.**
The schedules and known sources/images are hash-bound, but final native-hook
materialization, target-image compilation/class catalogs, private input/register
assembly, zero-model delivery/replay integration and the immutable executable
snapshot remain required. J1's additional observer-control hooks are explicitly
unmaterialized; their recipes are not claimed as frozen executable sources.
Those gaps are enumerated in each draft. Changes to a reviewed schedule or source
require a new reviewed version before execution. The adapter rejects this draft
artifact type before resource creation.

## Builder access to tools/

The model-facing boundary has only the five public tools; it offers no file
reader or shell and rejects filesystem paths in API/contract arguments. The CLI
policy disables shell, apps, multi-agent and web capabilities and rejects unknown
tool events. Tests prove attempted `tools/` reads cannot reach the host broker.
The host broker itself necessarily imports verifier-side Python modules.

**OS-level unreadability is not yet confirmed for a B06 trial.** CLI `read-only`
mode is not a read-confidentiality guarantee. B06 has no admitted executable
transport, and a real zero-model denial probe under that transport's restricted
identity remains a mandatory preflight gate. Do not substitute a mocked boolean,
these capability tests or a model transcript for that proof.

## Status against core-status items 1–5

1. Review fixes and private source variants prepared; native acceptance,
   input/register assembly and remaining scope admission still pending.
2. Collector, independent content replay and narrow processing-flag cause
   derivation tested on synthetic streams. Native controls, terminal runtime-origin
   binding and production closed-diagnostic delivery remain unqualified.
3. Three fixed review drafts prepared. They are not an executable freeze; the
   listed materialization gaps must close before seeking native-run approval.
4. Controller core remains preparatory. Model transport, sandbox denial proof,
   per-attempt publication integration and complete terminal reporting are pending.
5. No native B06 preflight has run. No measurement is authorized.

The validation manifest records the final test count and file hashes. The first
test invocation failed because Windows sandbox temporary directories could not
be reopened. The suite was rerun with a writable local temporary directory and
host filesystem permission; this was not a native slot or a Docker run.
