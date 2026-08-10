# Changelog

## 0.5.0 — 2026-08-10

- Added node-aware graph chat for who, what, where, when, why, how, impact, lineage, verification,
  and general explanation questions.
- Added intent-specific bounded retrieval and deterministic local answers with no external runtime
  dependencies.
- Added an optional OpenAI Responses API provider with strict structured output, server-side secret
  handling, disabled API storage, and a model override.
- Added claim citations, confidence rationale, limitations, supporting node and edge IDs, graph
  snapshot identity, and suggested follow-up questions to every answer.
- Added retrieval-time implementer/verifier isolation, audience-change history clearing, untrusted
  graph-data instructions, and rejection of citations outside the retrieved evidence package.
- Added a versioned answer schema and documented answer-quality and production-security contracts.
- Added six-question, prompt-injection, private-holdout, schema, provider, HTTP, and citation-
  validation tests.

## 0.4.0 — 2026-08-10

- Added a locally executable LIGHTYEAR Graph Explorer with no third-party runtime dependencies.
- Added five curated exploration perspectives for workload, rule, JCL lineage, data contract, and
  discovered edge-case analysis.
- Added bounded search, node inspection, evidence display, pan, zoom, depth selection, and graph
  focus controls for the 10,000-node estate.
- Enforced implementer/verifier visibility across search, direct lookup, neighborhoods, and traces.
- Added a deterministic, lossless Neo4j CSV projection with graph identity and row-count receipts.
- Added Neo4j import guidance and explicit source-of-truth and private-evidence boundaries.
- Added HTTP, privacy, bounding, explorer, and Neo4j projection tests to the verification suite.

## 0.3.0 — 2026-08-10

- Added a deterministic, evidence-aware knowledge graph for the complete pinned AWS CardDemo estate.
- Added COBOL, copybook, JCL, dataset, Java, test, and Maven dependency extraction.
- Added nine curated `INTCALC` business-rule mappings from legacy evidence to Java and verification.
- Added graph validation, coverage-gap detection, impact analysis, traces, and agent context packages.
- Added implementer/verifier visibility separation for private holdout assets.
- Added content-addressed graph snapshots, source-file hashes, receipts, and JSON Schema.
- Integrated graph regeneration and policy checks into Windows, macOS, Linux, and GitHub CI flows.
- Made snapshot verification compare canonical graph hashes rather than platform-specific gzip headers.
- Added graph architecture, trust model, ontology, query examples, and expansion roadmap.

The complete CardDemo estate is structurally indexed. Only the `INTCALC` workload is currently
claimed as semantically mapped and behaviorally verified.
