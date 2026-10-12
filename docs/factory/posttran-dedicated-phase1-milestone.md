# POSTTRAN dedicated transport and attempt 1 - October 11, 2026

Howard requested a dedicated, operator-invoked standard-library transport using
only `LIGHTYEAR_POSTTRAN_OPENAI_KEY` at call time. The implementation binds the
exact public packet and plan, verifies TLS, prohibits redirects and retries,
sets `store: false` and `max_output_tokens: 64000`, and refuses incomplete
responses or missing/invalid usage. Errors expose fixed codes, not credential,
server-body or exception text. Request/response hashes are recorded.

Transport SHA256: `41b0df0367194599a892f7596254d9eba94fb28ee9593e16ca0c9a9651e6243f`.
Amended plan: `bb53fd6de1afed29fc1064f986c6c2dadc5d709b93c9732c50a67077aaeb2919`.
The [exact diff](posttran-second-opinion/dedicated-transport-plan-2026-10-11.diff)
preserves the previous plan and approval. The new preflight is outside the
reservation ledger and consumes zero attempts. Attempt 1 reserves before
generation and refuses another invocation. Timeouts are 30 seconds to connect,
120 seconds total for count and 1,800 seconds total for generation. A local
timeout does not prove remote cancellation. No automatic retries or refunds.

Fifteen offline tests passed using mocked network/process boundaries and a fake
environment. They cover no generic-key fallback, verified TLS, fixed timeouts,
redaction of exception/raw/escaped key echoes, refusal behavior, plan pins,
stale/changed preflights, reservation ordering and duplicate invocation refusal.
The agent did not make a model/count API call or read the real credential.

The operator subsequently ran preflight and attempt 1 from their terminal.
Preflight completed at 4:06:51 PM PDT, counting 147,242 input tokens outside
the reservation ledger. Attempt 1 ran from 4:07:44 to 4:12:20 PM PDT
(276.152 seconds). It completed with 147,242 input tokens and 17,969 output
tokens, including 8,779 reasoning tokens. $11.05 was reserved; this is not a
claim about the billed amount. Local receipt seals, request binding, saved
response bytes and usage were verified. A hash-only
[public summary](posttran-second-opinion/attempt-1-public-summary-2026-10-11.json)
binds the result; the raw response and ledger stay local.

Generation success is not candidate correctness. No candidate compilation,
execution or Phase 1 invariant validation has been claimed. Phase 2 remains
blocked until Phase 1 passes, disagreements are human-adjudicated with source
lines, twin defects are resolved, and Howard separately approves Phase 2.
Neither publishing nor merging this transport grants that approval. No Docker,
B06 native attempt, signing or machine changes are part of this milestone.

The overall Phase 1 ceilings remain three attempts/compilations, 750,000 input
tokens, 192,000 output tokens, two hours and $36. This transport implements only
the preflight and attempt 1; further attempts and compilation are not automatic.
Final-head CI and Howard's commit-specific approval are required before merge.
