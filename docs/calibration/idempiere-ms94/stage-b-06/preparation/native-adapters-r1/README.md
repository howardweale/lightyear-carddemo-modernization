# B06 native adapter preparation, increment 1

J2 and J3 have additive native pair adapters and privately held retained reference
implementations. This is preparation for review, **not native qualification**.
No database execution, model call or B06 measurement launch occurred.
Review is operator review, not independent attestation.

The implementation starts from `3e2d61188b5f49f1b0dafebc6103740097ec1447`.
J1 predicates, B05 frozen evidence, `work/ms94` and template-r1 were not changed.

The adapter requires a signed qualification authorization bound to a new run and
its exact plan. A started slot cannot be reused. Full inherited entry checks run
before either candidate, including the schema, sixty constraint probes and all
entry table multisets. J3 private accounting expectations are rederived from
those entry rows and the sealed work order before entry is signed. Every captured
base table is read, including tables absent from the business predicates.

J2 combines the inherited typed procurement judge with the B06 invoice/date
checks, purchasing scope checks and complete row reconciliation. J3 combines the
materials quantity, cost, valuation and account predicates with ownership checks
and complete row reconciliation. Neither an equal mutation on both engines nor a
new unowned row becomes acceptable merely because cross-engine values match.
Comparison rules still require registered columns. The new materials audit
predicates do not themselves expand a comparison register.

Application execution uses separate containers with candidate/public-worker
mounts only. Host timestamps bracket independent SQL clock reads; signatures,
receipts and logs remain on real UTC. Clock-setting capabilities and clock
manipulation environment variables are refused. Cleanup is attempted even after
entry failure and checked against actual owned containers, networks and volumes.
Cleanup failure prevents a passing receipt. Offline gate replay reads captures;
it does not execute candidates or databases.

## Validation and bindings

- 39 B06 preparation Python tests passed on Windows, including missing-table,
  changed-binding, signature, clock-drift, unowned-write, entry-failure cleanup
  and no-reuse regressions. Synthetic test data are not native evidence.
- Two offline Maven `test-compile` checks passed in the pinned application image,
  with tests skipped, no network, no database execution and no model calls.
  Both owned compiler containers were actually absent after cleanup.
- J2 compilation: 65.656 seconds. J3 compilation: 46.313 seconds. Total:
  111.969 seconds. Overall preparation wall time was not measured.
- The initial sandboxed Python test attempts failed because Python temporary
  directories could not be reopened under the Windows sandbox. The tests passed
  with the ordinary host permissions and workspace-local temporary directories;
  no implementation test failed on that run.

The [manifest](manifest.json) binds reference source hashes, application image,
compilation records and unchanged template files. Its content hash is
`c3c2ef4e32520f9373d4d0a6805dae94c6cd8ae79a1ddc49854440c8fdc69c33`.
The two reference sources, compiler logs and private expectation values remain
local. Only hashes and preparation metadata are published here.

J3 expectations hash:
`5e97c24fb65464795da27f007be3a6f90c12184826f63575beaf88671b2db564`.
The [derivation binding](private-expectations-binding.json) records equal
derivation from the existing Oracle and PostgreSQL seed captures. This read-only
preparation check does not substitute for fresh full entry admission.

## Remaining against core-status items 1–5

1. Adapter/reference code and compile preparation are present. Complete native
   execution and replay, exact plan assembly, J3 comparison-register column
   admission and native acceptance of the retained references remain unverified.
2. The trusted posting-origin collector and its independent native replay remain
   outstanding. The existing attribution predicate and signed synthetic tests
   are insufficient. Until the next increment admits origin evidence, execution
   failures have no diagnostic forwarding authorization.
3. Exact qualification plans, mutants, image bindings and diagnostic expectations
   have not been frozen. Native qualification remains unapproved; no slots have
   been attempted or replaced.
4. The multi-journey measurement executable remains incomplete and unqualified.
5. No immutable B06 executable preflight or measurement preregistration exists.

The next increments must remain separate PRs. No native qualification may start
before Howard approves the exact plan commit, and Docker work requires explicit
permission without overlap with the October 5 CardDemo intake.
