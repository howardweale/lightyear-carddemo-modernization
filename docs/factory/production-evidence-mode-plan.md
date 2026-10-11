# Production and evidence modes: plan for Howard

Priority 3, after generic scenarios and the dual-run prototype. Design only,
not authorization to implement or deploy. Both modes share business semantics
and typed interfaces; mode selection changes observation and retention only.

Define a versioned mode contract listing enabled instrumentation, provenance,
privacy filters, persistence and overhead limits. Evidence mode records the
complete required evidence or refuses; production mode makes no completeness
or qualification claim. Neither mode silently switches after a failure. Bind
mode and instrumentation revision to every result and comparison report.

Build an offline differential fixture proving identical outputs, return codes
and state deltas for both modes. Exercise partial writes, exceptions, shutdown,
missing events and quota exhaustion. Evidence mode must stop at its declared
gate; production telemetry loss must be visible and must not masquerade as a
complete evidence run. Never use a production receipt as an evidence receipt.

Deliver the mode schema, boundary tests, overhead measurement protocol and
migration/rollback design. Deployment and any real production-data trial remain
separate approvals. Historical evidence and B06 defaults are not rewritten.
