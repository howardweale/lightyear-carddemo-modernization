# Changelog

## 0.10.0 — 2026-08-11

- Added a versioned, append-only audit contract with actors, roles, actions, subjects, evidence
  references, visibility, timestamps, sequence numbers, previous-event hashes, and event identities.
- Added deterministic ledger snapshots bound to the canonical knowledge-graph identity, plus
  validation that detects mutation, deletion, reordering, duplication, broken chains, stale
  projections, invalid decision hashes, statistics drift, and checkpoint tampering.
- Added deterministic development-readiness, mainframe-equivalence, and release-promotion policy
  decisions. Planner and builder roles cannot record acceptance decisions, and missing z/OS proof
  blocks release promotion.
- Added governed exceptions requiring a human approver, named owner, substantive justification,
  expiry, and compensating controls; mainframe equivalence and release promotion are non-overridable.
- Added optional HMAC-SHA256 checkpoint signing through an environment-only key, wrong-key
  detection, and explicit unsigned-canonical warnings.
- Added machine-readable and human-readable release evidence dossiers with policy rationale,
  unresolved gaps, evidence inventory, and ledger checkpoint identity.
- Added a read-only Evidence Control Tower to the graph explorer with promotion posture, policy
  decisions, audit timeline, dossier, and checkpoint views.
- Added cross-platform audit build and deterministic verification launchers, six portable JSON
  Schema contracts, tamper/privacy/policy/signature/API/UI tests, and full-suite integration.

## 0.9.0 — 2026-08-11

- Added a read-only z/OSMF Jobs adapter for job discovery, status and step data, spool-file
  inventory, and bounded spool-record retrieval using IBM-compatible resource shapes.
- Added verified TLS, optional enterprise CA and mutual TLS, Basic or bearer authentication,
  no-redirect transport, strict URL and identifier validation, time and response limits, and
  fail-closed status and content-type handling.
- Added recursive secret redaction and a minimization boundary that retains approved metadata,
  graph matches, and spool hashes while discarding raw spool bodies and server resource URLs.
- Added an explicit real-z/OS attestation gate: only non-loopback HTTPS captures made with the
  operator acknowledgement can emit `zos_observed`; simulator and unattested captures remain
  `simulated` and cannot satisfy mainframe equivalence.
- Added an IBM-shaped local z/OSMF server, INTCALC job/step/program/DD mapping, deterministic
  simulator snapshot, macOS/Linux and Windows launchers, and connection/capture commands.
- Added conformance, authentication non-leakage, transport security, content minimization,
  program-contradiction, record-range, deterministic capture, and trust-policy tests.

## 0.8.0 — 2026-08-11

- Added a versioned runtime-evidence contract that binds every observation to an existing graph
  node or edge and rejects unknown identifiers before ingestion.
- Added replaceable local-oracle and recorded-fixture adapters plus a clean boundary for future
  z/OSMF, JES, spool, SMF, and dataset-allocation collectors.
- Added append-only SHA-256 event chains, content-addressed run receipts, deterministic compressed
  snapshots, source-system identity, artifact hashes, and declared limitations.
- Added runtime reconciliation with `static_only`, `runtime_observed`, and
  `runtime_contradicted` states and evidence-class-aware confidence scoring.
- Added separate development-readiness and mainframe-equivalence policies; simulated and local
  evidence can exercise the factory but only `zos_observed` evidence can prove mainframe parity.
- Added a Runtime explorer view for adapter runs, trust policies, observed operations, limitations,
  receipt identities, and node/edge runtime projections.
- Added deterministic build and verification launchers, JSON Schemas, a synthetic z/OS-shaped
  replay fixture, tamper and contradiction tests, and full-suite integration.

## 0.7.1 — 2026-08-11

- Added shared macOS/Linux Python admission that automatically selects Python 3.11 or newer,
  supports an explicit `LIGHTYEAR_PYTHON` override, and rejects Apple's bundled Python 3.9 before
  a run can be misclassified as a semantic failure.
- Made the offline benchmark candidate postpone annotation evaluation as a defensive import guard.
- Added collision-safe, path-opaque run keys so repeated benchmark collections with the same
  human-readable run IDs remain independently addressable in the Factory control room.
- Added supported/unsupported runtime-admission and repeated-collection regression tests.

## 0.7.0 — 2026-08-11

- Added a deterministic autonomous-factory controller around replaceable planner, builder, and
  verifier agents; workers propose artifacts while deterministic policy remains authoritative.
- Added versioned work-order, agent-artifact, and run-receipt contracts with strict path, attempt,
  file-count, patch-size, timeout, audience, and network-intent policies.
- Added copy-on-run workspaces, exact bounded edit application, command-array acceptance gates,
  content-addressed artifacts, and an append-only hash-chained event ledger.
- Added implementer/verifier separation so private gate output and diagnoses are withheld from the
  builder while public failure envelopes remain useful for repair.
- Added local reference agents and an optional OpenAI Responses API adapter using strict structured
  output, disabled response storage, server-side credentials, and interchangeable model selection.
- Added an offline five-fault INTCALC mutation gauntlet that proves every defect is rejected before
  repair and reports autonomous repairs and false acceptances separately.
- Added a Factory control room to the graph explorer for run status, gates, state transitions,
  changed paths, receipt identity, and audience-filtered event inspection.
- Expanded modern source indexing so factory, graph, oracle, benchmark, and test Python files are
  searchable source nodes with content-addressed evidence in the canonical graph.
- Added factory contract, path-boundary, ledger-tamper, privacy, provider, benchmark, HTTP, and UI
  tests. Mainframe equivalence remains explicitly unclaimed until runtime evidence is connected.

## 0.6.0 — 2026-08-11

- Added a versioned relationship ontology covering all 21 graph relationship types, their purpose,
  direction, category, evidence policy, and allowed node-kind pairs.
- Bound the ontology identity into the canonical graph and added validation for undefined,
  reversed, incompatible, or drifted relationship claims.
- Added 11,646 content-addressed source evidence capsules covering all 12,129 graph evidence
  supports, including source context, highlighted lines, file hashes, excerpt hashes, and receipts.
- Added audience-safe edge and evidence APIs that resolve source only through visible owner IDs and
  evidence indexes; browser-supplied source paths are ignored.
- Made SVG edges and inspector relationship rows clickable and added a plain-language Edge
  Inspector with semantics, direction, endpoint navigation, properties, and supporting sources.
- Added a source-code drawer with contextual line display and exact evidence highlighting.
- Extended grounded chat to focus on a selected relationship and explain why the edge exists.
- Added ontology, pair validation, evidence integrity, tamper detection, path traversal, privacy,
  HTTP, UI-contract, and edge-focused chat tests.

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
