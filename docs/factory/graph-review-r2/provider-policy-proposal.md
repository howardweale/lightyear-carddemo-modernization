# Approved provider credential scope

Howard explicitly approved the provider-only credential scope during the PR 272-274 review. The active `factory/execution/policy.json` now permits `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` leases for the factory provider role, alongside the existing `OPENAI_API_KEY` lease.

Planner, builder, failure analyst and verifier roles remain denied all three credential leases. Credentials are neither persisted nor added to the builder environment. Network isolation is unchanged. This approval authorizes the policy change only; it grants no model-call or evaluation-budget approval.

The earlier automatic approval review rejection was resolved by Howard's exact scope approval. Eleven hardened-execution tests pass, including synthetic lease issuance, one-time consumption, redaction and denial for every other role. No real credential was read and no model was called.
