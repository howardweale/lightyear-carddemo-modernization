# P5 digest-bound build-once contract — October 10, 2026

`lightyear_evidence.build_once` extracts exact byte descriptors, replacement-scoped package comparison and the consumer pre/post binding from the B06 build-once adapter. The module imports no B06 code and cannot launch a process, call Docker, sign a decision or confer native admission. Native argv, configuration, OSGi loader, source inventory and observed-class checks remain in B06.

The generic saved-output contract pins shared artifact bytes, the separately allowed consumer class, exact command, exit code, stdout/stderr and before/after bindings. Callers must provide a trusted manifest digest. Unsigned digests establish integrity against that pin, not independent execution attestation. No missing receipt is synthesized during replay.

The tiny public JVM fixture in `tests/fixtures/build-once-public-v1` has two shared classes (`Main`, `Shared`) compiled once and two `Probe` variants. Actual Corretto 21.0.10 host executions returned 21 and 35. Shared class bytes were identical before and after both consumers. Sources, compiler/runtime hashes, generator bytes, class bytes and saved outputs are retained with contract `34541294631e0020a5b864a195f0851a172f465f3c4bff9dcc4e757468fa9272`. Replay uses these files and does not invoke Java. This public example has no database, network, model or Docker activity and grants no B06 credit.

Validation: seven generic contract tests, seven unchanged B06 build-once tests and one standalone worker import test passed (15 total). Tampering checks cover shared and consumer bytes, unexpected entries, metadata changes, missing replacements, wrong manifest, command, exit code, output, before/after state and traversal. The prospective standalone worker packaging includes the shared module through exact Git-byte snapshot mappings. Historical plans, receipts and frozen snapshots remain unchanged.

Next adopter: CardDemo Java, to bind a prebuilt application artifact and per-attempt consumer configuration to saved judge outputs. That adoption and any native run are outside this PR. Merge requires Howard's commit-specific approval.
