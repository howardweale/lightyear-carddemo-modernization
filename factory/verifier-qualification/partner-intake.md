# Partner intake and pilot acceptance worksheet

Complete this worksheet before claiming compatibility or scheduling acceptance.
The public synthetic module is a proposed boundary, not the customer's contract.

| Required item | Partner/source owner supplies | Acceptance check |
|---|---|---|
| Scope | Named module, entry points, dependency boundary, critical behaviors, exclusions | Both parties agree the denominator before testing |
| Source authority | Exact original source/build identity, runtime version and configuration | Observations trace to a reproducible authorized source baseline |
| Candidate identity | Generated source or executable, vendor/tool version, build recipe, dependencies | Immutable identity covers the deployed candidate and its adapter |
| Invocation | Batch/API/UI entry points, transaction boundaries, schedules and restart procedure | Adapter drives the same business operation on both sides |
| State | Representative synthetic or approved de-identified inputs; initial database/file state | Both lanes start from equivalent, independently checked state |
| Observability | Outputs, full relevant records, messages, error codes, ordering and commit visibility | Missing observations prevent acceptance; adapter self-reports are corroborated |
| Semantics | Copybooks/schema, decimal/rounding rules, dates, encoding, null/padding rules | Field-scoped representation rules reviewed before comparison |
| Failure behavior | Retry keys, crash/restart points, rollback and concurrency expectations | Fault and recovery scenarios can be exercised and witnessed |
| Access | Approved environment, data use, credentials delivery and retention restrictions | No credentials or private source/evidence enter the public repository |
| Review | Named source/business owner and independent challenge reviewer | Review authority and blind evaluation provenance are explicit |

The initial pilot report must include:

- Required, exercised, observed, decided and unresolved behaviors, with critical
  behaviors listed individually and reasons/owners for gaps.
- Correct alternatives accepted, rejected and indeterminate.
- Confirmed faulty alternatives detected, blocked as indeterminate and missed;
  unexercised/equivalent faults excluded from detection denominators and retained
  in a separate register.
- Raw and normalized evidence with source/candidate/adapter/comparator/contract
  identities. Hashes alone do not prove observation authenticity.
- Every accepted normalization, its field scope, rationale and reviewer; evidence
  that meaningful nearby differences remain visible.
- Explicit source-parity, business-correctness, runtime, workload and production
  claim boundaries. Record intentional business differences separately from
  representation-only normalizations.

Before running, agree critical-behavior acceptance requirements and what blocks
the pilot. No blanket 70% threshold, inferred whole-migration equivalence, or
automatic acceptance of unresolved critical behavior is built into this kit.
