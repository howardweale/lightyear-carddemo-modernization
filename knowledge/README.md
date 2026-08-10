# LIGHTYEAR Modernization Knowledge Graph

The graph is the factory's shared system model. It is deliberately broader than a code index: it
connects application structure, business meaning, modernization implementation, verification, and
provenance in one queryable artifact.

The committed snapshot currently describes the complete pinned AWS CardDemo estate. `INTCALC` is
the first fully mapped workload; the rest of the application is structurally indexed but is not
yet claimed to be semantically recovered or behaviorally verified.

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

The structural, semantic-mapping, initial verification, local exploration, grounded-question, and
database-projection layers are implemented in this release. Runtime truth is the most important
next addition.

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
| Business rule | `rule:intcalc:monthly-interest` |
| Java method | `modern:java-method:...InterestCalculationService#calculate` |
| Test | `modern:test:...InterestCalculationServiceTest#matchesInterestAndDefaultRateRules` |
| Scenario | `scenario:intcalc:synthetic-differential` |

Core relations include `CONTAINS`, `CALLS`, `USES_COPYBOOK`, `EXECUTES`, `ALLOCATES`, `READS`,
`WRITES`, `DERIVED_FROM`, `IMPLEMENTED_BY`, and `VERIFIED_BY`.

## Artifacts

- `graph.snapshot.json.gz`: deterministic, compressed property-graph snapshot;
- `graph.receipt.json`: content hash, sources, and counts suitable for CI evidence;
- `schema/graph.schema.json`: portable JSON Schema contract;
- `mappings/carddemo-intcalc.json`: curated semantic and verification mappings.
- `viewer/`: locally served, dependency-free visual explorer;
- `neo4j/README.md`: optional Neo4j projection and import contract.
- `chat/`: grounded answer quality contract and versioned structured-output schema.

The graph uses plain JSON and the Python standard library so it remains portable. It can export
the same snapshot into Neo4j without making that database the source of truth; Amazon Neptune,
PostgreSQL/Apache AGE, or another engine can be supported through additional projections.

## Commands

```bash
./knowledge-graph.sh build ../carddemo-upstream
./knowledge-graph.sh verify ../carddemo-upstream

PYTHONPATH=src python3 -m lightyear_knowledge_graph validate
PYTHONPATH=src python3 -m lightyear_knowledge_graph gaps
PYTHONPATH=src python3 -m lightyear_knowledge_graph stats
PYTHONPATH=src python3 -m lightyear_knowledge_graph impact \
  --node legacy:copybook:CVACT01Y --depth 2
PYTHONPATH=src python3 -m lightyear_knowledge_graph trace \
  --from legacy:cobol-paragraph:CBACT04C:1300-COMPUTE-INTEREST \
  --to modern:test:ai.lightyear.carddemo.service.InterestCalculationServiceTest#matchesInterestAndDefaultRateRules

./graph-explorer.sh

PYTHONPATH=src python3 -m lightyear_knowledge_graph export-neo4j \
  --output-dir work/neo4j-export
```

The explorer serves only on `127.0.0.1` by default. It queries bounded subgraphs and never attempts
to render the entire estate. Its implementer view filters verifier-private entities across search,
direct node reads, neighborhoods, traces, and graph-chat retrieval. Chat answers include evidence,
confidence, limitations, supporting entity IDs, and the canonical graph hash. The local selector is
a policy demonstration, not an authentication system; production use still requires identity,
authorization, auditing, and signed context and answer receipts.

`verify` rebuilds from the pinned upstream commit, validates graph integrity and mapping coverage,
and byte-compares the result with the committed snapshot. CI therefore fails when source,
extractors, mappings, or generated evidence drift apart.

## Expansion roadmap

1. **Runtime evidence:** ingest z/OS job executions, file hashes, record counts, return codes, and
   field-level differential observations.
2. **Deeper semantics:** extract control-flow, data-flow, SQL, CICS, IMS, MQ, scheduler, and security
   relationships; maintain inferred claims separately until verified.
3. **Coverage intelligence:** compute rule, branch, mutation, data-layout, and workload acceptance
   coverage directly from the graph.
4. **Agent context service:** serve minimal, signed, audience-specific subgraphs through a stable API
   or MCP interface.
5. **Factory orchestration:** use graph boundaries to decompose work, prevent conflicting edits,
   select tests, route failures, and drive repair loops.
6. **Longitudinal memory:** retain graph deltas, architectural decisions, failed attempts, and
   production feedback across releases and customer estates.
7. **Portfolio learning:** derive reusable modernization patterns without exposing customer source,
   data, or private verification assets.

The acceptance principle remains strict: a rich graph improves understanding and orchestration,
but only independent behavioral evidence can establish equivalence.
