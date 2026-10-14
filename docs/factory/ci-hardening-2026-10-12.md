# CI registry and path hardening — October 12

The CI PostgreSQL source digest stays `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`. A manual, main-only GitHub workflow prepares an authenticated GHCR mirror using `skopeo copy --all --preserve-digests` and verifies the raw destination manifest SHA. It has not been dispatched; the mirror must not be reported as populated. No local Docker, registry login, account setting or image change was performed.

Consumers select GHCR, public ECR, then Docker Hub, always at that same digest. A missing/private unpopulated GHCR mirror can fall back; quota/transient pull errors get at most two attempts per registry. Digest-integrity failures and permanent errors at public upstreams fail closed. Test/container execution is never retried. Callers use the successful registry reference with `--pull=never`, avoiding the former literal-ECR mismatch after fallback.

A complete local Git diff of PR base...head selects the four CloudBank-only jobs. Known Factory-only paths omit those jobs; shared/unknown/workflow changes, non-PR events, errors and missing path inventory run them. Renames include both old and new paths. The verification workflow and required aggregator remain active. No failed semantic load check is reclassified as transient.

Fifteen mocked registry/path/gate tests pass. Real mirror publication and registry fallback remain unverified until the workflow is reviewed and dispatched after B06. Workflow-file publication is tested through the branch push; no additional credential or account scope changes are requested by this code. `packages: write` belongs only to the manual mirror job, with read-only package pulls in verification.

Hold merge until authenticated B06 cleanup is sealed. The original ECR quota failures and original #327 semantic failure remain historical evidence.
