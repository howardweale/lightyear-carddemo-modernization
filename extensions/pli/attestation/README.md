# PL/I reproducible build and artifact attestation

MS #25 closes the source-only boundary in the bounded `ACCTPL1` modernization proof. The
attestation builder compiles `MixedPliAuthorizationService` with the JDK 17 compiler module,
creates a byte-reproducible standalone JAR, executes a deterministic test harness, emits a
JUnit-compatible XML report, inventories runtime dependencies, and produces a CycloneDX 1.5 SBOM.
The committed inventory binds the Java SE 17 language and compiler-module contract rather than a
runner-specific JDK vendor string; GitHub workload-identity provenance records the concrete CI
environment separately.

```bash
./pli-build-attestation.sh verify
```

The committed provenance records the exact clean source commit and binds the relevant source-tree
digest, JAR, test report, dependency inventory, SBOM, MS #22 contract, fixtures, comparison, and
development receipt. When the recorded commit is available, validation also compares every bound
source path to that Git object. The signed source-tree digest remains portable after a squash merge
makes the pre-evidence commit unreachable. Its RSA key is deliberately published as a non-secret
development test key and has `release_authorized: false`; it proves verifier behavior and a
reproducible local build, not a release identity.

GitHub Actions independently rebuilds the artifacts and uses GitHub workload identity through
`actions/attest` for authoritative CI provenance and SBOM attestations. The CI artifacts are
published per workflow run rather than committed as live or mainframe evidence.

Any missing, changed, stale, foreign-workflow, replayed, or incorrectly signed artifact demotes
PL/I development readiness. Neither signer path can satisfy authorized original execution,
PL/I load-module equivalence, `mainframe_equivalent`, or `production_ready`.
