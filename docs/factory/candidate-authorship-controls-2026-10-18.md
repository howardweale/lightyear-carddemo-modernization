# Candidate authorship controls - 2026-10-18

This F1 increment adds `CandidateHistory` to the existing factory workspace, `RunLedger` and `ArtifactStore`. It is controller machinery, not authorization-screen candidate code. CI exercises only a throwaway text file.

The controller owns a separate Git object database outside the no-history agent workspace. Only the approved candidate paths enter its index. Candidate commits use `LIGHTYEAR Factory <factory@lightyear.invalid>` for author and committer, with exact run and attempt trailers. Hooks, signing, inherited Git configuration and alternate object databases are disabled for these commands. No human identity is copied from the caller.

The audit walks every commit in the start-to-receipt ancestry, including side branches, merges and later-reverted edits. Every commit changing a candidate path is checked against the dedicated identity and final trailer paragraph. Each parent-to-commit candidate diff is retained through the existing artifact store and hash-chained ledger. Wrong identities, missing trailers and another run's trailers count as interventions. A later factory revert does not erase a human intervention.

This is an attribution record, not cryptographic proof of who invoked Git. The trusted CI controller must own the history directory and bind it to the approved run. Egress enforcement, encrypted complete model-call records, orchestration integration, the computed build receipt and all four complete F1 stub cases remain required before F1 acceptance. These component fixtures alone do not establish F1 acceptance or a factory-built screen.

No candidate execution, real model call, signing, import, activation or Phase 2 was performed in the developer session.
