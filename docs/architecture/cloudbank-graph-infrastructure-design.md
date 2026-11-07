# Knowledge graph to target infrastructure — design only

Not yet implemented: this proposal maps a provenance-bearing legacy inventory to a
reviewable target infrastructure plan. It does not provision resources, infer
approval, select production capacity or qualify a target from a graph alone.

The existing graph model (`src/lightyear_knowledge_graph/model.py`) records nodes,
edges and source/path/line evidence. `ontology.py` validates allowed relationship
pairs and the ontology hash. A future mapper must consume those identities rather
than untraceable summaries. Node names alone are insufficient for a mapping.

| Inventory input | Proposed target declaration | Required provenance and decision | Judge obligation |
| --- | --- | --- | --- |
| Online transaction entry points and call edges | Service boundary, ingress route, service account and allowed service-to-service traffic | Source entry point, called programs, authentication context, owner-selected grouping | Route and field equivalence; deny undeclared callers; observe intended identity |
| Batch schedules, dependencies and restart semantics | Scheduler/job specification, ordering, concurrency cap, checkpoint storage | Calendar/timezone, late/duplicate execution rules, predecessor conditions, restart record definition | Original-time deadlines, duplicate/restart tests, bounded concurrency and cleanup |
| Dataset definitions, reads/writes and transaction boundaries | Database/schema, storage location, private connectivity, backup/PITR policy | Record layout, keys, consistency/atomicity, retention, classification and residency | Exact normalized restoration, transaction behaviour, RPO/RTO measurements |
| Security rules and credential references | Least-privilege IAM, Workload Identity, Secret Manager references, network policies | Principal/resource/action scopes, deny precedence and separation of duties | Positive and negative access probes, runtime identity, rotation and restoration |
| Cross-domain dependencies | Explicit private routes and external-service contracts | Endpoint ownership, protocol, trust boundary and outage behaviour | Dependency loss, bounded retries, fail-closed behaviour; no silent fallback |
| Observability and operational objectives | Metrics/log/trace configuration, alert policy and capacity constraints | Required signals, redaction, retention, latency/load objectives and alert owner | Alert fire/recovery, sustained load and signal coverage; NOT RUN for absent drills |

Planned mapping pipeline:

1. Freeze the source inventory, ontology, evidence paths and unresolved findings by
   hash. Reject unsupported or ambiguous relations; retain every unmapped item.
2. Produce an intermediate mapping with a stable mapping ID for each source node or
   edge, target resource address, rationale and alternatives. A reviewer resolves
   deployment boundaries and operational objectives before generation.
3. Render infrastructure and rollout separately. Terraform owns cloud resources;
   application manifests and deployment steps own workload rollout. Neither may
   silently create resources assigned to the other owner.
4. Bind the mapping hash, source commit, rendered rollout hash and Terraform plan
   digest into the qualification packet. A resource without a mapping, an orphaned
   source item or a changed mapping invalidates that packet.
5. Derive platform drill expectations from the resulting declarations. Preserve
   independent behavioural equivalence and existing safety gates. A successful
   mock plan demonstrates neither cloud enforcement nor legacy behaviour.
6. After separately approved live execution, bind the observed platform verdict
   and the code receipt into one Ed25519-signed envelope. Verification uses an
   independently trusted public key and checks the complete evidence joins.

## Open questions before implementation

- Which legacy sources establish batch calendars, restart semantics and security
  deny precedence? Missing sources must remain explicit gaps.
- Which transaction groups belong in one deployment or database transaction?
  The graph supplies dependencies, not permission to split atomic work.
- Who supplies residency, retention, RPO/RTO, peak concurrency and latency targets?
  No cloud size or availability tier should be guessed from source line counts.
- How are external systems and unsupported legacy facilities represented without
  inventing replacements or treating a stub as equivalent?
- What independently reviewed mapping rules and negative fixtures cover each
  supported node/edge kind? Unsupported kinds must stop generation.
- Which graph and plan changes require renewed human approval and requalification?
  The initial rule should invalidate all affected downstream evidence.
- How will existing estate adoption/import, rollback and destruction preserve
  retained data, receipts, image-signing keys and unrelated resources?

Phase C ends with this design. No graph-to-IaC generator, deployment, admission,
MS67 closeout, native/P5 qualification or signing is implemented by this note.
