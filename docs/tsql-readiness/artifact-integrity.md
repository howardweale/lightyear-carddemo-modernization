# Public artifact integrity layer

Planned CI use: call `tools.ci.tsql_readiness_artifact.verify` with the repository's pinned public selection and a retained artifact directory. Supply the expected CI identity, harness hash, ScriptDom bridge hash and engine profiles from the reviewed execution plan, independently of the artifact being checked.

The helper reads JSON and public corpus assets only. It neither connects to a database nor starts a service, creates credentials, signs, or calls a model. It checks file closure, raw hashes, duplicate JSON keys, finite values, exact procedure/case/repeat inventory, declared input bindings, case-to-procedure receipt links, comparison verdict consistency, cleanup outcomes and summary aggregation. Rehashed missing cases, incorrect selectors, wrong-twin matches and stale external bindings cannot establish an internally consistent successful summary.

Not executed: this new helper and its five negative/contract tests have no CI result at preparation time. The tests manufacture clearly synthetic retained documents; they do not simulate native execution authority. No existing tests or assertions change.

The result deliberately separates `integrity_complete` and `reported_passed` from `native_execution_verified=false`, `comparator_replayed=false` and `coverage_qualification_verified=false`. Consistent attacker-authored files can still satisfy byte consistency, so no native or customer equivalence is inferred. Planned follow-up: acquire compatible qualified controls, implement the permitted CI provisioner, execute the ten native public pairs, and independently replay the existing comparator. The no-machine-signing and Friday runner restrictions remain.

This addition stays in the separate T-SQL draft. It changes no comparator, production source, required gate, workflow or #455 file.
