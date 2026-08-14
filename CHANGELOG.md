# Changelog

## 0.14.0 — 2026-08-14

- Added controller-owned, content-addressed semantic experiences that bind verified plans, patches,
  outcomes, graph nodes, source-evidence capsules, paths, gates, and run identities.
- Added positive repair, correct-unchanged, and non-executable negative memory classes; controller
  failures and unapproved evidence classes are quarantined instead of becoming reusable knowledge.
- Added a hard contamination boundary that excludes sealed-holdout runs and verifier-private
  artifacts from implementer memory, with adversarial validation and read-only projections.
- Added graph-, evidence-, path-, and vocabulary-aware retrieval with independent byte and result
  limits; graph or evidence-pack changes immediately stale prior experiences.
- Added progressive planner and builder memory context, while preserving fresh source evidence and
  deterministic gates as higher-authority inputs.
- Added versioned experience, snapshot, retrieval, and policy schemas plus cross-platform memory
  launchers, CLI ingestion/query/validation, and a Verified Experience Memory dashboard.
- Bound the verified-memory snapshot into the hash-chained audit ledger and current release dossier;
  full verification now rejects stale, tampered, or privacy-contaminated memory.
- Added tamper, idempotency, invalidation, negative-replay, sealed-contamination, context-budget,
  API, UI, and full-suite regression coverage.

## 0.13.0 — 2026-08-14

- Added HMAC-signed, expiring sealed evaluation envelopes with trusted key IDs, exact catalog
  identity, tamper detection, and fail-closed admission; a plain relabeled catalog is rejected.
- Added opaque holdout case references and privacy-safe receipts that omit private case names,
  categories, mutation markers, and verifier output from worker artifacts and dashboard APIs.
- Added clean `accept-unchanged` cases so needless edits are measured independently from mutation
  repair, including correct no-change and false-acceptance outcomes.
- Added evidence-selection precision, first-attempt repair, private-leak, unauthorized-edit, token,
  cost, baseline-rejection, and repair metrics under a versioned quality policy.
- Added a promotion-grade quality decision that can qualify only signed sealed evidence meeting
  every policy threshold; public calibration always remains non-qualifying.
- Added safety-first evaluation comparison, cross-platform quality-gate launchers, updated schemas,
  read-only evaluation APIs, and a Quality Control Tower view.
- Added signature, tamper, expiry, wrong-key, clean-case, privacy, policy, comparison, storage, UI,
  and full-suite regression coverage.

## 0.12.2 — 2026-08-13

- Replaced repeated full-context prompts with progressive role-specific retrieval: planners receive
  a compact graph and evidence catalog, and builders receive only plan-selected source capsules.
- Added fail-closed validation for planner-selected graph nodes and evidence capsule IDs plus
  independent 80 KB planner and builder context ceilings.
- Added exact Responses API input-token preflight before generation, a configurable per-call input
  ceiling, bounded count-request retries, and count identities and rate metadata in call evidence.
- Added request manifests that record prompt and payload hashes, context statistics, and selected
  evidence IDs without persisting provider credentials or full model prompts.
- Added an audience-safe controller-mediated transcript command that shows planner and builder
  artifacts while redacting verifier-private evidence by default.
- Added regression tests proving substantial context reduction, evidence-selection boundaries,
  exact token admission, pre-generation budget rejection, and transcript privacy.

## 0.12.1 — 2026-08-13

- Added bounded Retry-After-aware exponential backoff with jitter for transient Responses API
  throttling and transport failures; billing, quota, refusal, schema, and other hard failures do
  not retry.
- Added a 25,000-token per-call output ceiling, request timeouts, conservative pre-call cost
  admission, safe rate-limit metadata, and prompt-free retry evidence.
- Added evaluation-wide call, token, and estimated-cost budgets plus lower per-case ceilings and
  configurable pacing between cases.
- Added atomic per-case checkpoints, partial stopped receipts, sanitized provider failure
  classification, collision-safe retry run IDs, and resumability without repeating completed cases.
- Added v1.1 evaluation receipts, checkpoint schema, cross-platform resume commands, and tests for
  transient 429 recovery, hard-quota rejection, budget stops, partial evidence, and resume.

## 0.12.0 — 2026-08-11

- Added a replaceable model-provider contract with a controller-side budget boundary for calls,
  input/output bytes, tokens, estimated cost, and elapsed time.
- Refactored the OpenAI Responses integration behind the provider contract while retaining strict
  JSON Schema output, `store: false`, external credentials, refusal detection, and prompt-free receipts.
- Added a graph context assembler that binds approved graph roots, shared source-evidence capsules,
  allowed candidate files, truncation state, byte limits, and exact graph/evidence identities.
- Added an atomic constrained patch broker that validates all edits before writing and enforces
  allowlisted paths, text-only targets, exact matches, file size, patch size, file count, and changed-line limits.
- Added sanitized failure-analysis feedback, independently hashed model-call artifacts, run-level
  intelligence receipts, and Control Tower metrics for model, calls, tokens, cost, and evidence identity.
- Added a 36-fault, eight-category public calibration catalog plus an external sealed-holdout
  interface; public calibration is explicitly prevented from masquerading as blind evaluation.
- Added macOS/Linux and Windows model-workcell launchers, schemas, adversarial budget and atomicity
  tests, catalog mutation rejection tests, and full-suite verification integration.

## 0.11.2 — 2026-08-11

- Corrected OCI environment translation so the host workspace path becomes `/workspace` inside
  Docker/Podman, matching the read-only bind mount used by private acceptance gates.
- Added a regression assertion that rejects leaking the host workspace path into the container
  environment while preserving the fixed `/workspace/src` Python module path.
- Retained the v0.11.1 signed-admission and composite-evidence contract unchanged.

## 0.11.1 — 2026-08-11

- Split execution assurance into deterministic policy simulation, live container-runtime probe,
  and signed admitted OCI factory-run evidence; a probe can no longer satisfy the factory gate.
- Bound work-order admission, exact policy and work-order identities, issued agent identities,
  attested role actions, enforced acceptance gates, and non-persistent protected values into the
  factory execution-security receipt.
- Added strict evidence normalization that recomputes readiness, rejects unknown receipt types,
  invalid hashes, partial bindings, failed gates, missing actions, and producer-asserted readiness.
- Added a one-command macOS/Linux and Windows admitted-run workflow that signs, executes through
  Docker/Podman, validates the composite receipt, and builds a live audit snapshot and dossier.
- Updated audit ingestion, non-overridable policy, release dossier, Control Tower, and Factory UI to
  distinguish evidence class and clear only hardened execution while z/OS equivalence remains blocked.
- Added a normalized execution-evidence schema and adversarial tests proving that a successful live
  probe cannot impersonate a signed factory run.

## 0.11.0 — 2026-08-11

- Added signed, expiring work-order envelopes with trusted issuer keys, exact work-order and
  execution-policy identities, minimum key strength, maximum TTL, and append-only nonce replay
  prevention.
- Added short-lived, work-order-bound, audience- and action-scoped credentials for planner,
  builder, provider, and verifier roles; wrong role, action, work order, policy, signature, audience,
  time window, or issuer fails closed.
- Added an allowlisted one-use protected-value broker whose receipts never contain values and whose
  in-memory leases clear their contents after consumption.
- Added a real Docker/Podman backend with a digest-pinned image, network disabled, read-only root
  and workspace mounts, numeric non-root identity, all capabilities dropped, no-new-privileges,
  process/memory/CPU/tmpfs limits, environment filtering, command allowlisting, no shell, bounded
  output, and timeouts.
- Added a deterministic offline conformance receipt and separate live enforcement probe. Simulation
  is explicitly non-production-ready and cannot satisfy hardened-execution promotion policy.
- Integrated admission, agent-identity and gate-execution evidence into factory ledgers and run
  receipts, plus execution posture in the Factory control room.
- Added a non-overridable hardened-execution audit decision, Evidence Control Tower projection, and
  release-dossier gate alongside runtime and mainframe evidence.
- Added cross-platform execution launchers, three JSON Schema contracts, policy weakening,
  tampering, expiry, replay, identity scope, protected-value leakage, OCI invocation, orchestration,
  API and UI tests, and full-suite verification.

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
