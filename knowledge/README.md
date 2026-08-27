# LIGHTYEAR Modernization Knowledge Graph

## Cross-platform source identity

The canonical graph's modern semantic inputs are declared in `semantic-inputs.json`. Only those
content-addressed candidate and mapping files influence canonical semantic identity. Repository
implementation files remain governed by Git and CI but do not cause graph-wide receipt churn unless
they are deliberately added to the manifest.

Source-file nodes and evidence capsules retain two identities. `transport_content_sha256` (or
`transport_file_sha256`) hashes the exact bytes received for forensic chain of custody.
`content_sha256` (or `file_sha256`) hashes the same source after CRLF and legacy CR are normalized
to LF and is marked with `hash_basis: normalized-lf`. Semantic graph and evidence-pack receipts
exclude the transport-only observation, so one source revision has one logical identity on
Windows, macOS, and Linux without discarding the raw acquisition hash.

The canonical graph is complemented by the v0.17 live operational plane under
`../control-tower/`, the runtime evidence plane and z/OSMF adapter kit under
`knowledge/runtime/`, the audit ledger and Evidence Control Tower under `../audit/`, and the v0.12
hardened execution policy under `../factory/execution/`. Verified factory experiences are retained
under `../factory/memory/` and joined to graph context only when their graph and evidence identities
still match.
Runtime captures remain append-only evidence rather than nondeterministic mutations of the source
snapshot. The explorer joins both identities at read time and refuses to treat simulated or local
evidence as proof of z/OS equivalence.

The v0.23 read-only composite estate under `composite/` overlays the separately governed PL/I
fragment for navigation. It has its own identity and evidence pack while retaining the canonical
graph hash used by runtime and audit evidence.

The v0.24 PL/I conformance receipt under `../extensions/pli/conformance/` binds a 27-case synthetic
corpus and 22-category support matrix to the canonical graph. The capability projection exposes
these breadth metrics but explicitly identifies them as non-customer, static, non-runtime evidence.

The v0.25 PL/I build attestation under `../extensions/pli/attestation/` binds a reproducible
compiled JAR, JUnit-compatible test execution, dependency inventory, CycloneDX SBOM, clean source
commit, and MS #22 behavior evidence. A published development test key cannot be promoted to a
release identity; GitHub workload identity separately attests CI artifacts.

The graph is the factory's shared system model. It is deliberately broader than a code index: it
connects application structure, business meaning, modernization implementation, verification, and
provenance in one queryable artifact.

The committed snapshot currently describes the complete pinned AWS CardDemo estate. `INTCALC`,
the `CAVW` CICS/VSAM account-view path, the bounded `COBDATFT` HLASM routine, and the `CBPAUP0C`
IMS expired-authorization purge, and the Db2 AUTHFRDS data-modernization slice are mapped workloads.
Db2 tables, columns, constraints, indexes, DCL contracts, embedded SQL, and their issuing COBOL
paragraphs are first-class graph entities. IMS DBDs, PSBs, PCBs, segment hierarchies,
sensitivity views, and program bindings are structurally indexed; the CBPAUP0C normal path is
curated and development-proven without claiming live IMS equivalence or general IMS coverage.

## Why this can become a moat

Graph technology itself is not the moat. The compounding asset is the body of verified enterprise
knowledge accumulated in the graph:

1. deterministic structural facts extracted from source and configuration;
2. observed behavior captured from legacy runtime executions;
3. business rules with explicit evidence and confidence;
4. mappings from legacy behavior to modern implementation;
5. independent tests, holdouts, failures, repairs, and acceptance receipts;
6. reusable ontology and policies that transfer across modernization programs.

Every successful modernization adds evidence and improves future planning, context retrieval,
impact analysis, estimation, and verification. That feedback loop—not the choice of graph
database—is the durable advantage.

## Graph layers

| Layer | Examples | Initial authority |
|---|---|---|
| Structural | programs, paragraphs, copybooks, fields, jobs, datasets, Java types | deterministic parser |
| Operational | executions, traces, volumes, failures, observed outputs | legacy runtime capture |
| Semantic | workloads, business rules, domain concepts, exceptions | curated or inferred claim |
| Transformation | legacy-to-modern mappings and architectural decisions | reviewed mapping |
| Verification | scenarios, tests, mutations, differential results | independent verifier |
| Governance | visibility, confidence, policy decisions, receipts | factory policy engine |

The structural, semantic-mapping, initial verification, local exploration, governed-relationship,
content-addressed source-evidence, grounded-question, database-projection, bounded factory-
orchestration, signed admission, scoped identity, container policy, runtime evidence, z/OSMF
connection simulation, and audit-governance layers are implemented in this release. Independent
production evidence remains the most important next addition. v0.14 also implements the first
longitudinal memory layer for verified plans, patches, outcomes, and non-executable failures;
sealed evaluation content remains outside that memory boundary.

## Trust model

Every significant graph fact must be classified by provenance:

- `observed`: deterministically extracted from source or execution evidence;
- `asserted`: deliberately supplied in a versioned mapping or policy;
- `inferred`: proposed by an agent or heuristic and not yet independently confirmed;
- `verified`: confirmed by an approved verifier and evidence receipt.

Evidence records identify the source repository, path, line range, extraction method, and
confidence. Inferred claims must never silently become observed or verified facts.

Visibility is also part of the model. A node marked `inspector_private` is removed from context
packages created for an implementation agent. This prevents the worker from receiving private
holdout answers while allowing the independent verifier to use them.

## Ontology

Stable, namespaced IDs allow artifacts from different extractors and agents to join safely.

| Node family | Example |
|---|---|
| Legacy program | `legacy:cobol-program:CBACT04C` |
| Legacy paragraph | `legacy:cobol-paragraph:CBACT04C:1300-COMPUTE-INTEREST` |
| Copybook field | `legacy:cobol-field:CVACT01Y:ACCT-CURR-BAL:<line>` |
| JCL job | `legacy:jcl-job:INTCALC` |
| Dataset | `legacy:dataset:AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS` |
| CICS transaction | `legacy:cics-transaction:CAVW` |
| BMS field | `legacy:bms-field:CACTVWA:ACCTSID:84` |
| VSAM cluster | `legacy:vsam-cluster:AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS` |
| IMS database | `legacy:ims-database:DBPAUTP0` |
| IMS PSB/PCB | `legacy:ims-psb:PSBPAUTB` / `legacy:ims-pcb:PSBPAUTB:PAUTBPCB` |
| HLASM program | `legacy:assembler-program:COBDATFT` |
| HLASM DSECT | `legacy:assembler-dsect:COCDATFT` |
| Business rule | `rule:intcalc:monthly-interest` |
| Java method | `modern:java-method:...InterestCalculationService#calculate` |
| Test | `modern:test:...InterestCalculationServiceTest#matchesInterestAndDefaultRateRules` |
| Scenario | `scenario:intcalc:synthetic-differential` |
| PL/I extension program | `extension:pli-program:ACCTPL1` |

All relations are defined in `ontology/relationships.json`. Each definition includes a purpose,
direction, category, evidence policy, and exact allowed source/target node-kind pairs. The graph
snapshot carries the ontology content hash, and validation rejects undefined or incompatible edges.

## Artifacts

- `graph.snapshot.json.gz`: deterministic, compressed property-graph snapshot;
- `graph.receipt.json`: content hash, sources, and counts suitable for CI evidence;
- `semantic-inputs.json`: exact modern files and workload mappings allowed into semantic identity;
- `schema/graph.schema.json`: portable JSON Schema contract;
- `schema/relationship-ontology.schema.json`: governed relationship contract;
- `schema/evidence-pack.schema.json`: content-addressed source capsule contract;
- `mappings/carddemo-intcalc.json`: curated semantic and verification mappings;
- `mappings/carddemo-cics-vsam-account-view.json`: bounded CICS/VSAM proof mapping;
- `mappings/carddemo-asm-date-format.json`: bounded HLASM proof mapping;
- `mappings/carddemo-ims-expired-authorization-purge.json`: bounded IMS BMP proof mapping;
- `capabilities/mainframe-readiness.json`: graph-bound readiness gates for CICS, VSAM, IMS, HLASM, PL/I, and Db2/Data;
- `schema/capability-readiness.schema.json`: portable contract for the capability projection;
- `schema/pli-coverage.schema.json`: portable contract for PL/I supported-subset coverage evidence;
- `../extensions/schema/pli-build-attestation-receipt.schema.json`: compiled-artifact receipt contract;
- `ontology/relationships.json`: canonical meanings and endpoint constraints for all edges;
- `evidence/source.pack.json.gz`: deterministic source excerpts and supporting context;
- `evidence/source.receipt.json`: evidence-pack and graph identity receipt;
- `composite/`: read-only canonical-plus-extension snapshot, receipt, and extension-aware source pack;
- `viewer/`: locally served, dependency-free visual explorer;
- `neo4j/README.md`: optional Neo4j projection and import contract;
- `chat/`: grounded answer quality contract and versioned structured-output schema.
- `../factory/`: autonomous run contracts, example work orders, mutation benchmark, and operator
  guidance; run artifacts and receipts are generated beneath `../work/`.
- `../audit/`: hash-chained events, deterministic policy decisions, governed exceptions, release
  dossiers, schemas, and checkpoint guidance.
- `../control-tower/`: canonical operational events, freshness/alert policy, SSE projection, and
  production hardening guidance.

The graph uses plain JSON and the Python standard library so it remains portable. It can export
the same snapshot into Neo4j without making that database the source of truth; Amazon Neptune,
PostgreSQL/Apache AGE, or another engine can be supported through additional projections.

## Commands

```bash
./knowledge-graph.sh build ../carddemo-upstream
./knowledge-graph.sh verify ../carddemo-upstream
./composite-estate.sh verify ../carddemo-upstream
./lightyear.sh doctor
./lightyear.sh demo

PYTHONPATH=src python3 -m lightyear_knowledge_graph validate
PYTHONPATH=src python3 -m lightyear_knowledge_graph validate-evidence
PYTHONPATH=src python3 -m lightyear_knowledge_graph gaps
PYTHONPATH=src python3 -m lightyear_knowledge_graph stats
PYTHONPATH=src python3 -m lightyear_knowledge_graph capabilities
PYTHONPATH=src python3 -m lightyear_knowledge_graph impact \
  --node legacy:copybook:CVACT01Y --depth 2
PYTHONPATH=src python3 -m lightyear_knowledge_graph trace \
  --from legacy:cobol-paragraph:CBACT04C:1300-COMPUTE-INTEREST \
  --to modern:test:ai.lightyear.carddemo.service.InterestCalculationServiceTest#matchesInterestAndDefaultRateRules

./graph-explorer.sh

./live-control-tower.sh serve

./factory-benchmark.sh

./hardened-execution.sh verify

./audit-control-tower.sh verify

PYTHONPATH=src python3 -m lightyear_knowledge_graph export-neo4j \
  --output-dir work/neo4j-export
```

The explorer serves only on `127.0.0.1` by default. It queries bounded subgraphs and never attempts
to render the entire estate. Its implementer view filters verifier-private entities across search,
direct node reads, edge reads, source excerpts, neighborhoods, traces, and graph-chat retrieval.
Chat answers include evidence, confidence, limitations, supporting node and edge IDs, and the
canonical graph hash. The local selector is
a policy demonstration, not an authentication system; production use still requires identity,
authorization, auditing, and signed context and answer receipts.

`verify` rebuilds from the pinned upstream commit, validates graph integrity, relationship ontology,
mapping coverage, every evidence capsule, and byte-compares the generated graph and evidence
identities with committed receipts. CI therefore fails when source, extractors, ontology, mappings,
or generated evidence drift apart.

## Expansion roadmap

1. **Independent runtime evidence:** ingest real z/OS job executions, file hashes, record counts,
   return codes, and field-level differential observations.
2. **Deeper semantics:** extract control-flow, data-flow, SQL, CICS, IMS, MQ, scheduler, and security
   relationships; maintain inferred claims separately until verified.
3. **Coverage intelligence:** compute rule, branch, mutation, data-layout, and workload acceptance
   coverage directly from the graph.
4. **Agent context service:** serve minimal, signed, audience-specific subgraphs through a stable API
   or MCP interface.
5. **Factory scale-out:** v0.15 adds conflict-aware parallel cells and risk-based human approval;
   next move admission and identity signing to managed asymmetric keys and durable queues.
6. **Durable governance:** anchor signed audit checkpoints in immutable external retention with
   enterprise identity, trusted time, key rotation, and legal hold policy.
7. **Longitudinal memory:** retain graph deltas, architectural decisions, failed attempts, and
   production feedback across releases and customer estates.
8. **Portfolio learning:** derive reusable modernization patterns without exposing customer source,
   data, or private verification assets.

The acceptance principle remains strict: a rich graph improves understanding and orchestration,
but only independent behavioral evidence can establish equivalence.
