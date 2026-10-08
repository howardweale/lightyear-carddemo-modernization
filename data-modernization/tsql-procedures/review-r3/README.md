# PR277 follow-up: fresh native qualification

Operator review; not independent attestation. Zero model calls. All database execution used the approved dedicated Linux VM; no local Docker commands were run.

## Results

| Group | Native pairs | Result | Native elapsed seconds | Independent offline replay seconds |
|---|---:|---|---:|---:|
| Revision 8 attempt, preserved | 108 | 83/86 expected outcomes; failed qualification | 501.204 | 3.771 |
| Revision 9 coverage controls | 9 | 9/9 coverage expectations met | 50.283 | 0.138 |
| Revision 9 full corpus | 108 | **86/86 expected procedure/variant outcomes met** | 514.272 | 4.963 |
| Ordering controls | 8 | All declared rejection/refusal expectations met | 53.679 | 0.496 |
| Generated LEN cases and shrink probes | 18 | Replay/bookkeeping verified; not full-corpus qualification | 100.409 | 0.467 |

The full corpus contains 43 procedures. The 108 pair-level observations comprise 55 matches on compared observables and 53 divergences. These are not 108 equivalence certificates: qualification checks the declared procedure/variant outcomes, including policy-gated ambiguous cases. All 108 archives replayed independently using the revision 9 comparator and versioned finalizer. Signed cleanup receipts and separate actual owned-label checks found no remaining containers, networks or volumes for every group.

The failed revision 8 attempt remains unchanged. Its three unresolved correct twins were ci-unique (terminal error before a result), dynamic-parameter-binding and multiple-result-sets. Revision 9 adds narrowly bounded result reachability, constant parameter-only dynamic assignment and parser handling for closed refcursor parameter types. It does not relax unknown dynamic SQL or missing provenance. Historical revision 7/8 comparators and dependencies are retained for faithful replay.

Ordering controls prove that a missing target ORDER BY is rejected even when rows happen to match, reversed ordered UNION results diverge, SELECT INTO does not shift result contracts, and d.id cannot silently bind to projected h.id. Both qualified-key control variants are insufficient-evidence, as intended. Their subset reports have qualification_passed=false because the 43-procedure acceptance driver was not requested; that flag is not a failed control assertion.

The generated run executes seven generated argument cases for each twin plus four bounded shrink probes (18 pairs total). Two wrong-twin generated cases diverged; the four shrink probes did not preserve those divergences. Other argument cases match by coincidence and remain recorded. No global minimality claim is made. The historical proposal-origin label `proposed-not-executed` is retained in these records; actual execution is established by each signed pair manifest and replay, not that generator label. Per-verdict cases_run and the unreduced failure-witness hash are populated; the finalizer counts bound generated case plans and validates shrink history.

## Binding and implementation

- Executed source bundle: `7f840211287fef57264c80ef94c4df886ab3877f567b507448c26030cc7ddb27` (1,015 public source/fixture files).
- ScriptDom bridge: `7993f6aea4288a2e039242d390f7034ed49550b3d40c92fd7d2c2da0f5c5cf91`.
- Coverage controls report: `72006afe49112fe089fbc3dec395c9b100662f7b6c4277de4b20f8ff1d4a51b2`.
- Full qualification report: `97116694c110465c639180a79b3ba3512d44566a49b529d8f24ce7713e69e2ef`.
- Acceptance record: `b5edf5113c0c80d698ac4b060aac981979f5d627befdbb983f3db8d991f6c1a8`.
- SQL Server image: `sha256:4402d880dd4c34bfa7d8705e56a86cd6c88da80a1f6bbbe741f999e76264a090`.
- PostgreSQL coverage image: `sha256:b03ef125d79567173ab5622d9c5b05c9baf353a4eb78f8c13a938de4141de30d`.

Source result contracts come from ScriptDom; target SQL/PLpgSQL contracts come from pinned pglast 7.10. Only actual result producers receive contracts. Exact qualifiers/aliases, branch reachability and byte-bound callee catalogues prevent positional and last-name matching. The comparator checks duplicate-preserving multisets before unresolved ordering, so value differences are not hidden. SQL compatibility level is configurable; PostgreSQL dependency edges and closed two-part synonyms are captured. Datetime precision loss remains visible; rowversion is treated as engine-generated with unresolved policy, rather than silently equating its values. Unknown dependencies, dynamic SQL, nondeterminism and missing coverage remain fail-closed.

Local T-SQL tests: 121 run, four skipped because the host has no .NET SDK. The actual .NET build on Linux had zero warnings/errors and all ten real ScriptDom tests passed. CI now builds the bridge and runs those tests on Linux and Windows; CI has not run for this unpublished increment.

Public files here contain hashes, verdicts and audit summaries only. Raw archives, database captures and recorder private keys remain on the VM. The recorder is not an independent attestor. Existing public project identifiers are operational metadata, not credentials; historical signed evidence was not rewritten for a repository-wide identifier purge.

Customer-scale dependency closure, customer policy approval, performance/concurrency/security equivalence and certification remain outside this public-corpus qualification.

Source-byte check after documentation: 54 T-SQL implementation/bridge files still match the executed revision 4 source bundle exactly. Git attributes preserve those bytes after checkout.
