# POSTTRAN independent conversion preregistration

Phase 1 budget approved; execution preflight is blocked. No model call or
candidate code has been produced. The published
[plan](plan.json) seals the exact public input allowlist, prompts, client and
budgets. Model: `gpt-6-astra`, high reasoning, standard service. Client:
`codex-cli 0.155.0-alpha.9.2`, SHA256
`bc45017e8239dc150258f69309ced9df6bbcdf5b8e4f346decf780ac0999e226`.
The binary must match before execution; unavailable bytes require a revised
preregistration and approval. The official model page lists no dated snapshot;
this is an exact configuration pin, not a claim of immutable server weights.

| Phase | Calls / attempts / compilations | Input / output token caps | Hours | Estimated API equivalent | Hard API-equivalent cap |
|---|---:|---:|---:|---:|---:|
| 1 independent build | 3 / 3 / 3 | 750,000 / 48,000 | 2 | $3.03–$16.92 | $25 |
| 2 normal repair, separately approved after adjudication | 2 / 2 / 2 | 500,000 / 32,000 | 1 | $2.02–$11.28 | $17 |

Every call, including failures, consumes budget. Per-call limits are 250,000
input tokens and 16,000 output tokens including reasoning, 30 minutes, no
transport retry. Reserve the full next-call allowance before dispatch. Missing
usage stops the phase; no cap can be borrowed across phases. Token-cap
sensitivities including long-context cache-write pricing are $22.35 and $14.90.
These are planning equivalents, not subscription invoices. Prices checked
October 11 UTC against [official pricing](https://developers.openai.com/api/docs/pricing).
B05 supplies observed usage, not a POSTTRAN success forecast. The retained
INTCALC reconciliation has no recorded model-token sample; it supplies only
the three-way harness/compile precedent, so no INTCALC cost average is invented.

Phase 1 runs in a new isolated directory containing only allowlisted files:
no checkout/history, twin outputs, invariant results or review sheet. Compile
and structural diagnostics may be returned to the builder. Own-output
invariants and repeatability are evaluated by the judge, never exposed during
Phase 1. The first accepted candidate is frozen; no person edits it. Compare
that accepted candidate on all four public POSTTRAN scenarios and all fourteen
generated POSTTRAN scenarios from the pinned generator. Seal their exact input
manifest before the first call. The measured fourteen-case input hashes are now
sealed in [the generated input manifest](generated-input-manifest.json), from
Ubuntu run38100613787. All four public input sets are also hash-bound in the
plan. A changed manifest requires a new plan hash.

Every mismatch gets a stable register ID with candidate/twin hashes, field,
scenario, values and pinned source lines. Howard or his named reviewer signs
which side is wrong. The normal loop cannot start with unresolved records or
twin defects; a twin fix requires a separately reviewed plan and fresh evidence.
Phase 2 uses normal Verdict Engine feedback and is explicitly **not** an
independent second opinion. Publish failures and exhausted attempts as well as
success. POSTTRAN remains provisional throughout preparation.

Two focused tests check allowlist exclusion and fail-closed adjudication.
No provider-calling entrypoint is installed by this PR. Exact budget approval,
isolated execution preflight and all declared bindings are launch prerequisites.

Howard approved the exact Phase 1 budget for plan
`c022241cb0e4a62656daf9f889119fdab9441adcd4c6645be3f71da776ab9ebb`
in chat. That approval is recorded separately; the preregistration bytes stay
unchanged, and Phase 2 is not authorized. The [preflight result](phase1-preflight.json)
records 16 independently staged public packet files and all 18 public/generated
evaluation input sets matching the approved hashes. Neither twin outputs nor
invariant results are in the builder packet.

The locally installed clients do not match the approved binary. The official
release archive for the same `0.155.0-alpha.9.2` version was retrieved and its
archive digest verified against OpenAI's release metadata; its executable is
`384285237e5bd33b96f6d9de4644bfd203efdee5dbbecee24dbe8eebddce2020`,
which differs from the approved `bc45017e…` binary. A version string alone is
insufficient. No client was installed or substituted.

The release's configuration schema also does not establish enforcement of the
promised 16,000 output-token limit including hidden reasoning. Post-call usage
accounting would not enforce a hard per-call cap. Dispatch therefore remains
blocked until an approved exact client and enforceable transport limits are
available. A replacement client/transport requires a concrete amended plan and
approval; the existing approval is not being treated as permission to weaken
the caps. Five focused tests cover the allowlist, exact approval, client-byte
refusal, isolated packet and Phase 2 boundary. No candidate was authored by a
person, and no model budget was spent.
