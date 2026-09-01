# Changelog

## 0.47.3 — 2026-09-01

- Corrected the density guard so every reduction choice and the explicit full-render override
  dismiss the blocking layer before the graph is rendered.
- Added collision-aware graph-label placement across five candidate positions, preserving labels
  by graph importance and suppressing only those that cannot be placed without overlap.
- Made graph nodes keyboard-operable with roving focus, directional arrow-key navigation,
  Enter/Space inspection, Home-to-root behavior, descriptive accessible names, and visible focus.
- Raised top-control and repeated metadata labels to readable sizes while retaining the compact
  two-band Control Tower layout.
- Replaced the permanently clipped visual stream-status string with an accessible live status on
  the existing status indicator.

## 0.47.2 — 2026-09-01

- Folded session-stable Company and Business problem selectors into an Estate popover, retaining
  Workload, Technology scope, and Operator lens in a single 1366-pixel-safe working bar.
- Replaced the five visible native header selects with labelled, keyboard-accessible comboboxes and
  added hover, focus, motion, and pressed states across interactive controls.
- Replaced the compressed claim-band debug string with labelled Snapshot, Entities, Relationships,
  Rules, and Extensions values; one visible snapshot identity carries the canonical and composite
  hashes in its tooltip.
- Added a 70-node readability guard with implementation-package collapse, rules-and-proof focus,
  legacy-to-modern path focus, and an explicit full-render override.
- Added pill-backed graph labels and package-count nodes so high-density implementation detail reads
  as a product rather than an unstyled graph demonstration.
- Added the workload action “Open proof run for this workload” and reduced the inspector's primary
  actions to proof, subgraph focus, and trace-start work.
- Refused non-loopback binds unless the operator supplies the explicit
  `--i-understand-this-is-unauthenticated` flag and printed a warning naming the exposed evidence.
- Required a generated per-session bearer token for verifier-audience HTTP routes while leaving the
  implementer projection open only on loopback; customer deployment still requires external SSO.
- Bundled SIL-OFL IBM Plex webfont subsets and removed all Google Fonts requests.

## 0.47.1 — 2026-08-31

- Replaced the black Control Tower theme with the approved warm editorial paper, stone, and burnt-
  orange palette while preserving graph-bound navigation and live evidence behavior.
- Reduced the header to two functional bands, moved evidence planes to the left rail, limited the
  right rail to Inspect, Trace, and Ask, promoted operational alerts, and versioned browser assets.

## 0.47.0 — 2026-08-31

- Recast the Evidence Control Tower in the LIGHTYEAR investor-deck visual system with Material-
  influenced clarity: warm-white work surfaces, a near-black operational plane, gold hierarchy,
  bronze boundaries, modern sans-serif typography, sentence case, rounded controls, and more space.
- Added a dedicated Knowledge Graph binding card that exposes the canonical content identity,
  entity and relationship counts, freshness, and downstream binding status beside the live stream.
- Added the operator path that was missing from the first cut: Company → Business problem →
  Workload → Technology scope → Operator lens. Company and problem constrain the available
  workloads; workload selection moves the graph root; scope and lens refine that graph in place.
- Promoted the canonical graph and its source-evidence pack to a first-class operational source
  with fingerprinted observations and hash-chained `graph.projection.changed` events.
- Added live graph reload through the existing SSE refresh path so a changed canonical snapshot
  updates metadata, perspectives, operator context, legend, metrics, and the active graph view.
- Added a five-second status refresh alongside the event stream so freshness ages and the visible
  last-updated time continue to advance even when no projection-change event is emitted.
- Added fail-closed graph binding checks: a graph identity change invalidates a mismatched source-
  evidence pack, Runtime projection, or Audit projection and raises a critical Control Tower alert
  until the affected evidence is rebuilt.
- Preserved the Control Tower as a read-only projection. No approve, dispatch, retry, promote,
  exception-authoring, or other command endpoint was added.
- Added focused server, HTTP, UI, policy, graph-binding, and documentation regression coverage plus
  customer-readable MS #47 documentation in Markdown, Word, and PDF.

## 0.46.0 — 2026-08-31

- Added customer, technology-scope, and operator-lens navigation to the Evidence Control Tower,
  keeping engagement, platform focus, and task perspective separate.
- Added unified-estate, mainframe, and database focus modes that retain connected cross-platform
  context instead of hiding dependencies at platform boundaries; SAP estate and governed security
  vulnerability views are visibly planned.
- Added graph-derived platform coverage for COBOL, PL/I, DB2, VSAM, IMS, JCL, CICS, HLASM, BMS,
  Java, and modernization evidence, with Oracle and SAP ASE marked qualification-only and not
  projected.
- Added directed evidence tracing, an explicit related-evidence mode, hop and platform summaries,
  static-versus-runtime claim language, evidence-gap results, and inspector actions for choosing
  endpoints.
- Added first-class `ISSUES_DLI`, `READS_SEGMENT`, and `WRITES_SEGMENT` semantics, resolving exact
  COBOL `EXEC DLI` calls through the program's PSB/PCB view to authorized IMS segments.
- Added one-click source-backed COBOL-to-IMS `DLET` tracing plus a separate non-customer `AUTHUPD1`
  PL/I-to-DB2 `UPDATE` fixture; retained the original `ACCTPL1` DB2 read and IMS dependency examples.
- Added visible static-source, static-reference-fixture, non-customer, and runtime-not-observed
  labels so a graph path cannot be mistaken for a production transaction.
- Kept Oracle-to-mainframe and Oracle-to-IMS transaction claims blocked because no Oracle or SAP
  ASE graph fragment, customer integration edge, or runtime transaction evidence is attached.
- Added regression coverage and customer-readable MS #46 documentation in Markdown, Word, and PDF.

## 0.45.0 — 2026-08-31

- Added a target-neutral SAP ASE `SourceAdapter` implementing schema discovery, privacy-preserving
  profiles, sealed extraction contracts, content-bound replication resume, and explicit transaction
  and locking capabilities without selecting PostgreSQL or Oracle prematurely.
- Added a customer-shaped ASE catalog with 2 tables, 31 columns, 4 user-defined datatypes, 2 identity
  columns, 5 constraints, 3 indexes, multiple locking schemes, 6 procedures, and 4 triggers.
- Added a 187-case executable corpus with depth across types and UDTs, identity, money/exact numeric,
  datetime/time, empty strings and character semantics, Transact-SQL and stored logic, locking and
  rollback, and replication ordering/resume.
- Added a 107-entry five-class compatibility ledger covering every discovered column, UDT,
  constraint, index, stored-logic object, and 54 declared ASE behaviors. Unsafe policy and loss
  decisions remain unresolved; unsupported behavior is excluded from the claim scope.
- Added twelve separate qualification gates, five frozen JSON Schemas, ten content-addressed evidence
  artifacts, POSIX and PowerShell verification paths, adversarial overclaim tests, and extensive
  customer-readable documentation.
- Kept live ASE observation, native stored-logic execution, target selection, target migration
  qualification, stored-logic completion, database-migration completion, and production readiness
  false pending a real pilot and authorized native evidence.

## 0.44.1 — 2026-08-31

- Replaced the Markdown-only milestone browsing experience with a responsive, client-side index
  that searches milestone number, title, customer value, capability, boundary, release, and roadmap
  phase without sending search text to a server.
- Replaced context-dependent relative links with absolute GitHub links for Markdown and PDF and
  direct-download links for Microsoft Word so the format links work from GitHub, ChatGPT previews,
  copied documents, and the published index.
- Added GitHub Pages publication, URL-backed filter state, keyboard search controls, responsive
  mobile presentation, result counts, empty-state guidance, and regression tests for all 132 format
  targets.
- Extended the content manifest and fail-closed verifier to govern the Markdown and HTML index files
  alongside the 132 milestone artifacts.

## 0.44.0 — 2026-08-31

- Added a governed customer-readable documentation library for MS #1 through MS #44 with one
  canonical narrative and matching Markdown, Microsoft Word, and PDF artifacts per milestone.
- Recovered MS #1 and MS #2 from the initial repository commits and bound MS #3 through MS #43 to
  the existing release record rather than inventing missing historical claims.
- Standardized purpose, customer value, delivered capability, relationship to earlier work,
  evidence posture, source of record, and explicit claim boundaries across all milestone briefs.
- Added a deterministic cross-format generator, 132-artifact content manifest, source identity,
  exact byte and SHA-256 checks, and fail-closed detection of missing, stale, changed, or extra
  milestone artifacts.
- Added customer-facing index, POSIX and PowerShell build/verify entry points, optional document
  build dependencies, format-completeness tests, and rendered DOCX/PDF publication artifacts.
- Moved the planned SAP ASE semantic source adapter to MS #45 so MS #44 can close the customer
  documentation and release-governance gap before another technical qualification claim is added.

## 0.43.0 — 2026-08-31

- Added a genuine Oracle semantic-core `SourceAdapter` with deterministic source discovery,
  privacy-preserving profiling, contract-bound extraction, content-bound SCN resume, and explicit
  fail-closed transaction capabilities.
- Added a 38-entry Oracle source compatibility ledger covering all 26 AUTHFRDS columns and Oracle
  number, date/time, empty-string, identifier, transaction, redo, DDL, sequence, procedure,
  package-state, and autonomous-transaction boundaries using all five governing classes.
- Added four bounded Oracle PL/SQL procedures and deterministic PL/pgSQL translations covering
  `SELECT INTO`, `NO_DATA_FOUND`, UPDATE and `SQL%ROWCOUNT`, decimal branches and application
  errors, and `NVL`/empty-string behavior.
- Added a 20-case stored-procedure corpus covering results, side effects, row counts, exception
  mapping, numeric thresholds, null/empty/space behavior, type failures, duplicate rows, and
  mutation boundaries.
- Added explicit fail-closed exclusions for dynamic SQL, autonomous transactions, package state,
  database links, and procedure-owned commits.
- Bound the source adapter, procedure conformance and five-class ledgers into eight independent
  Oracle-to-PostgreSQL gates; bounded development and the supported procedure subset pass while
  live source/target, redo, native procedure, full stored-logic, database-completion, and production
  claims remain false.

## 0.42.0 — 2026-08-31

- Bound the exact five-cell `ACCOUNTV` pilot selected in MS #32 to its six source files, five
  technologies, five coordination dependencies, and canonical source-graph identity.
- Added a deterministic 40-case integrated corpus covering online and batch paths, Db2 cardinality,
  schema and index behavior, copybook layout, JCL flow and datasets, HLASM branching, cross-language
  calls, source identity, dependency edges, and four fail-closed native vectors.
- Preserved material source truths: unqualified single-row SQL cardinality, the PL/I account-ID
  overwrite, the bounded null/non-null `DATEFMT` branch, and the external `CBACT04C` boundary.
- Added five bounded cell receipts, ten acceptance-evidence items, 15 blocked live-evidence items,
  a 30-entry compatibility ledger using all five governing classes, and twelve qualification gates.
- Added frozen schemas, POSIX/PowerShell release-gate integration, deterministic artifacts, graph
  holdouts, source/dependency drift probes, mutation cases, and rehashed-overclaim tests.
- Marked Wave 2 integrated development evidence ready while keeping factory dispatch, native
  compilation/execution, mainframe equivalence, production release, and production readiness false.

## 0.41.0 — 2026-08-31

- Bound HLASM qualification to the canonical graph inventory of two programs, 41 instructions, 23
  symbols, one DSECT, five fields, one macro, nine branch edges, and exact DSECT/macro relationships.
- Added a deterministic 40-case synthetic semantic corpus with 32 targeted boundary cases, 36
  passing cases, four explicit fail-closed cases, and 121 observed feature categories.
- Covered `COBDATFT` date behavior and source quirks, the 80-byte `COCDATFT` layout, MVC/MVI/ST,
  CLI/CLC condition codes, B/BE/BNE, register operations, STM/LM save areas, USING/DROP, COPY,
  ASMWAIT static expansion, LTORG, COBOL parameter lists, and the bounded `MVSWAIT` handoff.
- Added a 28-entry HLASM compatibility ledger using all five governing classifications and explicit
  exclusions for privileged services, storage protection, recovery, broad instruction families,
  native assembler output, binder behavior, and STIMER timing.
- Separated eleven gates for graph inventory, corpus provenance, source/directives, DSECT/storage,
  instructions, condition codes/branches, linkage policy, native exclusions, the existing private
  date proof, and authorized native build/execution evidence.
- Added frozen schemas, POSIX/PowerShell release-gate integration, deterministic receipts, graph
  holdouts, exact-corpus checks, negative diagnostics, and rehashed-overclaim tests.
- Kept native HLASM, assembler, binder, LE linkage, system services, runtime, mainframe-equivalence,
  and production claims false pending authorized assembly, bind, execution, and operational evidence.

## 0.40.0 — 2026-08-31

- Bound IMS qualification to the canonical graph inventory of four databases, four dataset groups,
  four PSBs, six PCBs, three segments, three fields, and their structural relationships.
- Added a deterministic 40-case synthetic semantic corpus with 32 targeted boundary cases, 36
  passing cases, four explicit fail-closed cases, and 94 observed feature categories.
- Covered HIDAM, secondary-index and GSAM boundaries; GU/GN/GNP and GHU/GHN/GHNP navigation;
  qualified, unqualified, multi-level, and invalid SSAs; blank, GE, GB, II, AJ, and DJ status codes;
  ISRT, REPL, DLET, PROCOPT, SENSEG, CHKP, XRST, ROLB, and scheduling boundaries.
- Added a 28-entry IMS compatibility ledger using all five governing classifications and explicit
  exclusions for Fast Path DEDB, MSDB, IMS TM shared queues, DBRC logging, and recovery.
- Separated eleven gates for graph inventory, corpus provenance, DBD/storage, hierarchy and SSAs,
  PSB/PCB policy, navigation/status, mutation behavior, checkpoint/recovery, runtime exclusions,
  the existing private expiry-purge proof, and authorized native execution.
- Added frozen schemas, POSIX/PowerShell release-gate integration, deterministic receipts, graph
  holdouts, exact-corpus checks, negative diagnostics, and rehashed-overclaim tests.
- Kept native IMS, IMS TM, Fast Path, DBRC recovery, restart, runtime, mainframe-equivalence, and
  production claims false pending authorized region, database, logging, and recovery evidence.

## 0.39.0 — 2026-08-30

- Bound CICS/VSAM qualification to the canonical graph inventory of 240 CICS commands, 25
  transactions, 16 file resources, 15 VSAM clusters, three alternate indexes, three PATHs, and
  their exact graph identity.
- Added a deterministic 38-case synthetic semantic corpus with 30 targeted boundary cases, 34
  passing cases, four explicit fail-closed cases, and 59 observed feature categories.
- Covered KSDS, ESDS, RRDS, alternate-index and PATH lookup, READ/WRITE/REWRITE/DELETE, update
  tokens, STARTBR/READNEXT/READPREV/ENDBR, file status, RESP/RESP2, ENQ/DEQ, syncpoint commit and
  rollback, BMS maps, and LINK/XCTL/RETURN.
- Added a 27-entry CICS/VSAM compatibility ledger using all five governing classifications and
  explicit exclusions for LDS record access, RLS, TSQ, TDQ, journals, and exits.
- Separated eleven gates for graph inventory, corpus provenance, organizations and keys, alternate
  indexes, file access, mutation behavior, locking/recovery, CICS command boundaries, exclusions,
  the existing private account-view proof, and authorized native execution.
- Added frozen schemas, POSIX/PowerShell release-gate integration, deterministic receipts, graph
  holdouts, exact-corpus checks, negative diagnostics, and rehashed-overclaim tests.
- Kept native VSAM, native CICS, RLS, recovery, runtime, mainframe-equivalence, and production
  claims false pending authorized region, catalog, concurrency, journal, and recovery evidence.

## 0.38.0 — 2026-08-30

- Bound JCL qualification to the canonical graph inventory of 46 jobs, two procedures, 119 steps,
  451 DD allocations, and their exact graph identity.
- Added a deterministic 30-case synthetic JCL conformance corpus with 20 targeted semantic-boundary
  cases, 24 passing cases, six explicit fail-closed cases, and 36 observed feature categories.
- Added a 22-entry JCL compatibility ledger covering jobs, procedures, symbolics, EXEC resolution,
  DD allocation, DISP, GDG, DCB/SPACE, condition codes, restart, utilities, scheduler directives,
  JES controls, subsystem boundaries, and RACF submission identity using all five governing classes.
- Separated ten gates for estate inventory, corpus provenance, parsing, job/procedure semantics,
  program resolution, dataset allocation, condition/restart behavior, utilities/scheduler/security,
  tamper resistance, and authorized JES/catalog/scheduler execution.
- Added frozen schemas, POSIX/PowerShell entry points, release-gate integration, deterministic
  receipts, exact-corpus checks, diagnostic-location checks, and rehashed-overclaim tests.
- Kept native JCL, JES, catalog/SMS, scheduler, runtime, restart, mainframe equivalence, and
  production readiness false; no customer or IBM source is included in the synthetic corpus.

## 0.37.0 — 2026-08-30

- Consolidated the PL/I conformance lab, mixed-language development proof, mutation evidence, and
  candidate build attestation into ten independent qualification gates.
- Added a 20-entry PL/I compatibility ledger covering declarations, numeric and character
  semantics, storage, preprocessing, calls, conditions, files, Db2, CICS, IMS, and IBM runtime
  boundaries using all five governing classifications.
- Expanded the conformance corpus from 27 to 52 cases with 25 targeted boundaries for storage
  classes, arrays, pointers, picture/decimal arithmetic, conditions, preprocessing, record layouts,
  parameter conventions, SQL cursors, CICS, and IMS; unsupported behavior fails closed.
- Bound the qualification to 52 synthetic cases, 22 supported construct categories, seven mutation
  cases, 16 blocked cases, and the bounded `ACCTPL1` reference workload.
- Added deterministic qualification artifacts, frozen schemas, Linux/Windows wrappers, release
  verification integration, and fail-closed overclaim tests.
- Kept general Enterprise PL/I, native compiler, z/OS runtime, mainframe equivalence, and production
  readiness false; the corpus contains no customer source.

## 0.36.0 — 2026-08-30

- Added a graph-bound COBOL qualification contract covering 55 programs, 927 paragraphs, 75
  copybooks, 7,817 fields, 56 file handles, and their static dependency relationships.
- Separated nine qualification gates for inventory, syntax/source format, copybook closure, data
  layout/numerics, control flow/calls, file behavior, DB2/CICS/IMS boundaries, local differential
  behavior, and authorized native compile/link/execute evidence.
- Added a COBOL compatibility ledger covering source format, copybooks, PIC layouts,
  REDEFINES/OCCURS, decimal behavior, arithmetic, control flow, linkage, file status, embedded DB2,
  CICS, IMS, compiler options, and LE runtime semantics.
- Required every COBOL boundary to resolve to exactly one of the five governing classifications and
  rejected silent policy acceptance or unsupported behavior without explicit exclusion.
- Kept native compiler qualification, runtime equivalence, mainframe equivalence, and production
  readiness false; generated COBOL planning cells remain planning scopes only.

## 0.35.1 — 2026-08-30

- Added a concrete Db2 for z/OS `SourceAdapter` implementing schema discovery, bounded profiling,
  contract-bound row extraction, content-bound CDC resume, and transaction-capability projection.
- Added a DB2 source compatibility ledger covering all 26 AUTHFRDS columns plus encoding, padding,
  null/empty-string behavior, isolation, CDC position, DDL CDC, and package/bind semantics.
- Required every DB2 entry to use exactly one governing classification: `exact`,
  `normalized-equivalent`, `policy-decision-required`, `lossy`, or `unsupported`.
- Added deterministic source-adapter discovery, profile, ledger, and conformance artifacts with
  source-only/synthetic evidence labels and explicit false live-catalog, CDC, mainframe-equivalence,
  and production-readiness claims.
- Recorded the corrected MS #33–#41 roadmap and retained v0.35.0 stored-logic work as supporting
  MS #34 evidence rather than treating it as fulfillment of DB2 hardening.

## 0.35.0 — 2026-08-30

- Added an independent Oracle-to-PostgreSQL stored-logic qualification core covering procedures,
  functions, packages, triggers, views, materialized views, and application SQL.
- Added seven fail-closed gates for inventory completeness, dependency closure, translation,
  results/side effects, transactions/exceptions, security context, and performance/operability.
- Inventoried the two bounded AUTHFRDS data-changing application SQL statements and classified both
  as `policy-decision-required` pending Oracle and PostgreSQL execution evidence.
- Prevented an empty source-only Oracle object inventory from being treated as proof that no stored
  logic exists; live catalog, deployment DDL, scheduler, grant, and application-source capture remain
  mandatory.
- Bound the MS #34 stored-logic gate to the new content-addressed qualification artifact while
  keeping inventory, stored-logic completion, database completion, and production readiness false.

## 0.34.0 — 2026-08-30

- Added the first platform-neutral database path: a deterministic Oracle-to-PostgreSQL proof bound
  to the MS #33 canonical schema, mappings, compatibility ledger, and rehearsal evidence.
- Separated schema translation, data conversion, constraints/indexes, query equivalence,
  transaction behavior, CDC/resume, cutover/rollback, and stored logic into eight independent gates.
- Passed the first four bounded development gates and the simulated CDC/resume and
  cutover/rollback mechanisms without promoting them to live production evidence.
- Kept transaction isolation at `policy-decision-required` until concurrent live probes and an
  approved policy exist.
- Kept stored procedures, triggers, and arbitrary application SQL in an independent
  `excluded-unqualified` gate; `database_migration_complete` and `production_ready` remain false.

## 0.33.0 — 2026-08-30

- Added independent source- and target-adapter interfaces plus a 17-kind canonical database type
  system with explicit numeric, null, time-zone, and truncation rules.
- Added deterministic data-profile and schema-transformation contracts, typed normalized rows,
  query/result comparison, transaction comparison, a content-bound CDC envelope, and fail-closed
  cutover and rollback contracts.
- Added a content-addressed AUTHFRDS compatibility ledger covering every column for PostgreSQL and
  Oracle plus transaction isolation, DDL CDC, sequence state, and stored logic.
- Required exactly one of `exact`, `normalized-equivalent`, `policy-decision-required`, `lossy`, or
  `unsupported` for every ledger entry; unresolved policy or loss blocks equivalence and unsupported
  behavior is excluded from the claim scope.
- Added a deterministic adapter conformance suite and committed receipt for the existing PostgreSQL
  and Oracle adapters, with explicit non-promotion and non-production boundaries.
- Added frozen JSON schemas and tamper tests for semantic contracts, normalized rows, CDC events,
  compatibility coverage, policy decisions, query/transaction behavior, and cutover/rollback gates.

## 0.32.0 — 2026-08-30

- Added a content-addressed human pilot-selection contract bound to the exact MS #31 assessment and
  source-only dossier.
- Required business and technical ownership, rationale, outcomes, success criteria, bounded data
  policy, and one explicit disposition for every unresolved source boundary.
- Compiled the selected mixed ACCOUNTV slice into five deterministic development cells spanning
  COBOL, PL/I, JCL, Db2, and HLASM with exact source, graph, dependency, output, deliverable,
  acceptance-evidence, and live-evidence scopes.
- Added four governed planning waves from boundary verification through blocked authorized-native
  validation, with automatic dispatch disabled in every wave.
- Added standalone `select` and `package` commands plus POSIX and PowerShell parity, frozen selection
  and work-package schemas, committed reference artifacts, and fail-closed tamper tests.
- Kept every generated cell in `draft-scope-not-admitted` state; no signed work order, model
  qualification, authorized native execution, mainframe equivalence, or production readiness is
  claimed.

## 0.31.1 — 2026-08-30

- Added one shared fail-closed contract for `qualification_eligible`, `promotion_allowed`,
  `production_ready`, and `mainframe_equivalent`, then applied it to the historical model-evidence
  bridge and pinned all four claims in regression tests.
- Added a repository-wide audit that rejects committed receipt overclaims and literal source
  promotions without an explicit authority implementation.
- Made the pinned AWS CardDemo fixture a visible prerequisite for complete tests; missing data can
  only be accepted through an explicitly labelled `unit-only` mode.
- Added a content-addressed catalog for all 33 paired POSIX and PowerShell entry points, including
  purpose, role, and verification ownership, plus restored missing `oracle.sh` and `test.sh` twins.
- Added mainframe-access and z/OSMF adapter verification to the complete verifier and restored the
  missing Windows migration-rehearsal and collection-appliance stages.
- Added a JDK 17-or-newer compiler preflight with actionable diagnostics for old runtimes and JREs
  that do not expose `jdk.compiler`.
- Kept all live-system, model-qualification, mainframe-equivalence, promotion, and production claims
  false; this patch hardens proof boundaries but does not create new live evidence.

## 0.31.0 — 2026-08-29

- Added a deterministic customer estate assessment bound to the exact intake, source-analysis
  receipt, graph identity, and published assessment policy.
- Partitioned the typed source graph into connected application slices with stable identifiers,
  source files, technologies, relationship types, unresolved references, and evidence needs.
- Added an explicit boundary-closure wave for absent or ambiguous targets, followed by
  human-governed pilot selection, development proof, and blocked authorized-native validation.
- Added technology-specific modernization patterns and development/live evidence backlogs for
  COBOL, PL/I, JCL, Db2, CICS, HLASM, IMS, and VSAM.
- Added fail-closed controls preventing assessment tampering, hidden unresolved references,
  business-priority inference, automatic factory dispatch, or live-readiness promotion.
- Added JSON and Markdown assessment artifacts, POSIX and PowerShell `assess` commands, a v3 pilot
  dossier, frozen v1 assessment and v3 dossier schemas, and an eight-artifact deterministic rehearsal.
- Kept every planning result advisory and source-only; model qualification, authorized original
  execution, signed live equivalence, mainframe equivalence, and production readiness remain false
  or blocked.

## 0.30.0 — 2026-08-29

- Added a deterministic customer source analysis workcell bound to each approved intake rather than
  projecting the repository's CardDemo graph as customer evidence.
- Added a dedicated content-addressed relationship ontology spanning bounded COBOL, copybook, PL/I,
  JCL, Db2 DDL/SQL, HLASM control flow, IMS DBD/PSB structure, VSAM IDCAMS definitions, and approved
  CICS configuration relationships.
- Added customer-specific gzip graph snapshots and analysis receipts with parser coverage, entity
  counts, graph statistics, exact source identities, and visible unresolved or ambiguous references.
- Added native COBOL-to-PL/I calls, JCL-to-PL/I/HLASM execution, HLASM branch targets, IMS
  DBD-to-segment and PSB-to-PCB lineage, and VSAM cluster-to-AIX-to-path relationships inside the
  pilot analysis contract without changing the canonical CardDemo graph identity.
- Added fail-closed source re-hashing, graph/ontology validation, size bounds, analysis tamper tests,
  and explicit rejection of behavior, live-system, mainframe-equivalence, and production claims.
- Added a v2 pilot dossier that binds the customer analysis while preserving the v1 intake,
  preflight, and analysis contracts and the historical v1 dossier schema.
- Extended POSIX and PowerShell pilot flows with an explicit `analyze` stage and made the six-artifact,
  nine-source-class reference rehearsal byte-reproducible on Linux, macOS, and Windows.

## 0.29.0 — 2026-08-29

- Added one supported no-network Python 3.11+ source-tree launch and release path for a governed
  source-only pilot, without requiring a package build backend or third-party runtime dependency.
- Added a bounded, credential-safe intake for approved COBOL, copybooks, PL/I, JCL, Db2 DDL, and
  configuration exports with deterministic raw and logical source identities.
- Rejected symlinks, hidden paths, unsupported files, binary content, unsafe sizes, path drift, and
  credential-shaped material before evidence assembly.
- Added a gates 6–8 preflight covering global authorization, identity, TLS, signing, test-data,
  retention, execution, rollback, recovery, and technology-specific live-evidence prerequisites.
- Added a content-addressed JSON and Markdown pilot dossier binding 16 runtime, graph, capability, language,
  build, qualification, data, migration, appliance, readiness, and audit artifacts by raw SHA-256.
- Added beginner, senior-engineer, security/operations, and auditor guides plus POSIX and PowerShell
  operator entry points.
- Froze v1 intake, preflight, and dossier schemas for the 0.29.x pilot line and added fail-closed
  upgrade, tamper, unsupported-input, secret, artifact-drift, and overclaim tests.
- Added a clean-environment rehearsal that reproduces the six-class reference intake and complete
  dossier byte-for-byte.
- Kept model qualification, authorized original-system execution, signed live equivalence,
  mainframe equivalence, and production readiness explicitly false or blocked.

## 0.28.0 — 2026-08-28

- Added a content-addressed enterprise collection-appliance profile bound to the existing
  three-adapter mainframe access campaign.
- Added bounded bearer, externally issued OAuth bearer, and mTLS-plus-bearer authentication
  profiles with TLS 1.2 minimum transport and credential-free configuration.
- Added continuation-only pagination, bounded retry and `Retry-After`, global response limits,
  and fail-closed redirect and continuation validation.
- Proved a forced interruption after page two followed by content-addressed checkpoint resume
  without repeating completed adapter work.
- Added digest-and-redacted-claims-only retention with seven-day checkpoint and thirty-day evidence
  policy bounds; raw bodies and credentials are never retained.
- Added an eight-scenario deterministic fault laboratory covering DNS, TLS, timeout, redirects,
  pagination loops, rate limits, truncation, and checkpoint tampering.
- Published the appliance posture in the unified capability projection while keeping all live,
  mainframe-equivalence, enterprise-IdP, customer-vault, purge-scheduler, and production claims
  blocked.

## 0.27.0 — 2026-08-28

- Added a content-addressed five-event Db2-shaped AUTHFRDS change journal covering insert, update,
  and delete operations.
- Added deterministic PostgreSQL- and Oracle-shaped target application with normalized row,
  checksum, and identity reconciliation.
- Forced an interruption after event two and proved exact checkpoint resume plus idempotent duplicate
  replay with no lost or repeated change.
- Added a plan-bound, development-only human cutover approval that cannot authorize production.
- Injected a unilateral post-cutover divergence, detected it, and restored both targets to their
  exact pre-cutover state identities.
- Recorded bounded zero-event fixture RPO and three-step recovery while explicitly excluding
  wall-clock production RPO/RTO claims.
- Added fail-closed journal, before-image, checkpoint, mapping, approval, fault, receipt, and live-
  overclaim tests plus Bash and PowerShell verification entry points.
- Published the rehearsal in the unified Db2/Data capability and data control-tower projections;
  live Db2, customer-data, real cutover, production, and mainframe-equivalence gates remain blocked.

## 0.26.1 — 2026-08-28

- Added a fail-closed bridge for the exact retained v0.12 live OpenAI evaluation archive.
- Pinned the external archive and evaluation identities without committing the archive, credentials,
  raw prompts, or raw model responses.
- Verified legacy content hashes, artifact references, event-ledger chaining, model-call provenance,
  workspace reconstruction, and original baseline/final gate decisions.
- Published a schema-validated historical receipt and made it visible in the model-evidence dashboard.
- Kept public calibration, legacy schema, missing independent sealing, current-manifest gaps, token
  policy, workload repetition, and portfolio approval as explicit qualification blockers.
- Added Bash and PowerShell import commands plus tamper, secret, relabelling, traversal, and manifest-
  drift regression tests.

## 0.26.0 — 2026-08-27

- Added trusted workload profiles and public calibration catalogs for INTCALC, POSTTRAN,
  CREASTMT, and the mixed PL/I–COBOL–Db2 ACCTPL1 cell.
- Added workload-specific private gates and deterministic repairs covering 23 published mutations
  plus eight clean accept-unchanged cases with zero false acceptance.
- Added a content-addressed qualification manifest and safety-first aggregate receipt requiring at
  least two distinct sealed model runs per workload.
- Bound qualification to exact evaluation, factory-run, model-call, request-manifest, portfolio,
  approval, checkpoint, latency, token, retry, resume, and cost evidence.
- Made one critical false acceptance block promotion regardless of aggregate repair rate.
- Expanded the portfolio to four work cells with graph/dependency conflict detection, two parallel
  waves, high-risk approval barriers, and checkpointed recovery that does not repeat passed cells.
- Added POSIX and PowerShell verification/qualification entry points and versioned JSON schemas.
- Kept model qualification, production authorization, native z/OS equivalence, and general
  workload coverage as separate claims; no model is qualified by committed public calibration.

## 0.25.1 — 2026-08-27

- Made deterministic PL/I artifact verification survive a squash merge without weakening the
  committed source-tree, signature, workflow, or artifact bindings.
- Preserved exact receipt and attestation comparison whenever the recorded pre-evidence commit is
  reachable; otherwise compare the four portable build products byte-for-byte.

## 0.25.0 — 2026-08-27

- Added a JDK-17-only reproducible builder for the bounded PL/I modernization service JAR.
- Added five deterministic execution checks with a JUnit-compatible XML report.
- Added a content-addressed dependency inventory and CycloneDX 1.5 SBOM.
- Added SLSA-shaped provenance binding the clean source commit, compiled JAR, test report, SBOM,
  dependency inventory, and MS #22 behavior evidence.
- Added asymmetric RSA development signatures with a hard non-release boundary and pure-Python
  verification against a pinned public trust anchor.
- Added GitHub workload-identity build and SBOM attestations using repository OIDC.
- Made missing, stale, tampered, foreign-workflow, replayed, or incorrectly signed build evidence
  demote PL/I development readiness.
- Added tamper tests for the JAR, JUnit XML, dependency inventory, commit, workflow, and release
  overclaim while keeping live PL/I equivalence and production readiness blocked.

## 0.24.0 — 2026-08-27

- Replaced the PL/I language pack's line-oriented pattern extraction boundary with a tokenized,
  statement-aware supported-subset front end that preserves source locations.
- Published a content-addressed PL/I support matrix spanning 22 construct categories and explicit
  unsupported syntax.
- Added a synthetic 27-case conformance corpus with 25 program cases, two include cases, five
  expected blockers, and seven mutation-oriented cases.
- Added deterministic golden parse/reference results and a graph-bound coverage receipt recording
  recognized constructs, explicit gap codes, provenance, and claim boundaries.
- Made comments, strings, casing, spacing, continuation lines, missing includes, shadowed calls,
  malformed comments, unsupported preprocessors, and unsupported storage fail safely.
- Upgraded the PL/I pack contract to v1.2 and made the unified capability view depend on the
  conformance receipt before PL/I discovery can remain ready.
- Added PL/I breadth metrics to the customer/auditor projection while explicitly labelling the
  corpus synthetic, non-customer, and non-runtime evidence.
- Added Bash and PowerShell conformance entry points plus fail-closed tamper, graph-drift, and
  overclaim tests.
- Kept authorized z/OS execution, IBM compiler equivalence, arbitrary Enterprise PL/I support,
  mainframe equivalence, and production readiness blocked.

## 0.23.0 — 2026-08-27

- Added a content-addressed semantic-input manifest that limits canonical modern-source identity to
  explicitly declared candidates and mappings while retaining fail-closed drift behavior.
- Added a deterministic read-only composite estate that overlays validated PL/I nodes and edges on
  the canonical graph without changing its identity or evidence contract.
- Added PL/I relationship ontology coverage and a complete Explorer perspective for
  `ACCTPL1 → CBACT04C` and `ACCTPL1 → Db2 AUTHFRDS` lineage.
- Added a separately content-addressed composite source pack so PL/I evidence excerpts are
  inspectable without modifying the canonical evidence pack.
- Preserved canonical runtime and audit bindings inside the composite Explorer and added an
  explicit UI banner showing canonical/composite hashes and the non-equivalence claim boundary.
- Added `doctor`, `demo`, `explorer`, and `verify` developer entry points for POSIX and PowerShell,
  with required-versus-optional prerequisite diagnostics and actionable remediation.
- Added fail-closed tests for semantic input drift, undeclared implementation changes, fragment
  drift, projection tampering, cross-estate navigation, and canonical runtime/audit compatibility.
- Kept gates 6 and 8 blocked, gate 7 mechanism-ready, `mainframe_equivalent: false`, and
  `production_ready: false`.

## 0.22.0 — 2026-08-26

- Advanced the bounded mixed `ACCTPL1` PL/I–COBOL–Db2 workload from discovery-only to a
  content-addressed local development proof.
- Made the PL/I source explicit about `OPTIONS(COBOL)`, the `CBACT04C` parameter aggregate, and
  `DIVIDE(...,5,2)` truncation semantics.
- Added a curated behavior contract, seven boundary fixtures, a source-faithful executable oracle,
  and an independently implemented Python modernization candidate.
- Added nine mutation probes covering Db2 overwrite behavior, risk calculation and rounding, COBOL target and
  parameters, and fail-closed error side effects.
- Added a production-shaped Java service and JUnit suite for the same bounded service seam.
- Added deterministic POSIX and PowerShell build/verify launchers plus a fail-closed development
  receipt binding graph, fragment, contract, fixtures, comparison, and candidate sources.
- Promoted PL/I capability gates 3–5 to passed and gate 7 to mechanism-ready while keeping
  authorized z/OS execution, signed equivalence, mainframe equivalence, and production readiness
  explicitly blocked.

## 0.21.1 — 2026-08-26

- Replaced the four-cell capability view with one evidence-bound projection spanning runtime,
  language, and data capabilities: CICS, VSAM, IMS, HLASM, PL/I, and Db2/Data.
- Added explicit capability kinds so discovery, development proof, and live-mainframe equivalence
  are compared without treating languages, runtimes, and data platforms as interchangeable.
- Bound the projection to the canonical graph, extension catalog, PL/I fragment, PostgreSQL and
  Oracle offline receipts, and the mainframe-access campaign receipt.
- Made the PL/I reference proof visible as discovery-ready but not development-ready, and made the
  Db2 multi-target proof visible as development-ready but not live-mainframe-equivalent.
- Added the MS #21 access campaign as a separate collection mechanism so simulated collector
  readiness cannot be mistaken for a technology equivalence gate.
- Added stale-evidence and tampered-fragment regression tests while preserving the canonical graph
  identity and every existing fail-closed production boundary.

## 0.21.0 — 2026-08-26

- Turned the z/OSMF, Db2 for z/OS catalog, and CICS CMCI contracts into one executable read-only
  mainframe access campaign with an exact-adapter-set aggregate receipt.
- Added a no-redirect, verified-HTTPS, GET-only transport with bounded response reads, external
  bearer credentials, sanitized failures, and no raw-body retention.
- Added IBM-shaped z/OSMF step-data and CICS CMCI resource parsing plus a deliberately bounded
  customer-approved Db2 catalog REST projection.
- Added a credential-free access profile that binds remote observations to exact graph entities
  and rejects extra adapters, unsafe paths, secret-shaped configuration, and unbounded settings.
- Added separate live evidence signing, graph-bound per-adapter envelopes, and aggregate validation
  for missing, duplicate, mixed-class, invalid, unsigned, or drifted captures.
- Added deterministic simulated campaign evidence, POSIX and PowerShell launchers, JSON schemas,
  a customer access runbook, and adversarial transport/parser/receipt tests.
- Kept `production_ready: false`: passing collection proves bounded read-only observations, not
  source equivalence, performance, CDC, cutover, rollback, or production promotion.

## 0.20.0 — 2026-08-26

- Added a versioned adapter evidence envelope that binds every claim to an exact graph identity and
  classifies evidence as live, recorded, simulated, or inferred.
- Added recursive credential redaction, bounded artifact metadata, optional HMAC signatures, and
  fail-closed validation for drift, tampering, missing graph entities, unsafe scope, and untrusted
  signing keys.
- Added a deterministic record/replay adapter that downgrades live captures to recorded evidence
  and can never promote simulated or inferred evidence.
- Added an adapter registry with implemented fixture, replay, and z/OSMF contracts plus explicit
  pre-access contracts for Db2 for z/OS catalog and CICS CMCI collectors.
- Added a hash-bound graph extension-fragment contract so new language packs do not silently mutate
  the verified base graph or invalidate downstream audit and runtime evidence.
- Added the first PL/I language pack proof for programs, procedures, includes, file access,
  embedded Db2 SQL, and a mixed-language call into the existing CardDemo COBOL graph.
- Added deterministic POSIX and PowerShell verification, JSON schemas, adversarial tests, and
  committed development receipts while keeping live-mainframe and production-readiness claims
  blocked.

## 0.19.2 — 2026-08-23

- Generalized data-target generation and catalog expectations behind a versioned adapter contract.
- Added an Oracle Database 26ai Free adapter, schema projection, boundary-fixture loader, Docker runner, and explicit Oracle semantic gaps.
- Replaced coarse PostgreSQL object counts with exact column, type, length, precision, scale, nullability, key-order, and index-order evidence.
- Added normalized row-level checksums, bounded query comparisons, and independent commit/rollback probes for both targets.
- Added fail-closed parsing for missing, malformed, unknown, and duplicate evidence markers plus adversarial mutation tests.
- Bound model, mapping, fixture, schema SQL, fixture SQL, verification SQL, adapter version, and container image identity into live receipts.
- Added a multi-target aggregate receipt that cannot pass unless both PostgreSQL and Oracle receipts pass.
- Added a side-by-side target evidence matrix to the Control Tower while retaining `production_ready: false`.
- Corrected Oracle SQL/JSON generation after the first live 26ai Free probe: apply `NULL ON NULL` once per object, emit bounded one-line `VARCHAR2` evidence, and exit SQL*Plus on the first database error.

## 0.19.1 — 2026-08-23

- Wait for the requested PostgreSQL database to accept a real query before running the live equivalence proof.
- Record bounded live-proof failure reason and `psql` exit code without persisting raw database output.
- Add regression coverage for the PostgreSQL entrypoint initialization race.

## 0.19.0 — 2026-08-22

- Added deterministic Db2 DDL, DCL, and embedded-SQL parsing for the CardDemo AUTHFRDS vertical slice.
- Added first-class Db2 table, column, constraint, index, DCL, and SQL-statement entities to the evidence graph.
- Added paragraph-to-SQL, SQL-to-table, and SQL-to-column lineage plus four curated data business rules.
- Added a target-neutral canonical model, PostgreSQL 16 adapter, schema, migration mapping, and boundary fixtures.
- Added fail-closed schema/data/query/transaction equivalence checks and a tamper-evident signed development receipt.
- Added an isolated Docker PostgreSQL proof command and customer-key receipt signing path.
- Added a Control Tower Data panel for lineage posture, equivalence checks, and unresolved production gaps.
- Added 17 focused tests, including empty-input, duplicate-key, incomplete-row, missing-marker, and signature-tamper cases.

## 0.18.5 — 2026-08-22

- Pinned the direct-construction default for private gate output so a future dataclass-default
  inversion is rejected even when no JSON deserialization path is involved.
- Pinned the comparator's first-observed duplicate diagnostic policy while preserving independent
  duplicate and population-count failures.
- Turned the normalization ledger into an executable governance control: schema, comparator,
  runtime scope, behavior, owner, reason, and ISO review date are validated fail-closed.
- Made a normalization review date expire on the stated date and wired validation into both the
  focused verifier gauntlet and full cross-platform verification.
- Clarified that the tracked-evidence clean-tree assertion is a preventive CI control; it was not
  remediation of an independently observed artifact-mutation defect.

## 0.18.4 — 2026-08-22

- Replaced dictionary-only comparator indexing with explicit duplicate detection on both expected
  and actual records, plus independent population-count checks.
- Added a three-state differential contract: equivalent exits `0`, verified differences exit `1`,
  and comparisons with no evidence return `indeterminate` and exit `2`.
- Removed timestamp suppression because the oracle and candidate already receive the same pinned
  clock; malformed, blank, or different timestamps now fail comparison.
- Added a versioned, content-addressed comparison report and an owned normalization ledger.
- Made `baseline_first`, `allow_network`, and `expose_output_to_builder` reject quoted or numeric
  pseudo-booleans; deserialized reports require an exact `true` before exposing gate output.
- Added comparator escape and holdout-boundary suites with positive controls, bare-pytest source
  discovery, cross-platform verifier launchers, dedicated CI jobs, and a tracked-evidence clean-tree
  assertion.
- Kept the separately observed oracle duplicate-account/CardXref behavior change out of scope until
  it receives an independent source and z/OS semantics review.

## 0.18.3 — 2026-08-21

- Added one adaptive PowerShell Python runtime resolver across every Windows entry point, with an
  explicit `LIGHTYEAR_PYTHON` override and tested support for Python 3.11 and newer.
- Made managed AWS CardDemo checkouts line-ending neutral and added repository-wide Git attributes
  for stable text and binary handling.
- Added dual source identity: raw transport hashes preserve forensic custody while normalized-LF
  logical hashes drive graph and evidence-pack semantic identity.
- Made canonical JSON and Markdown writers emit UTF-8/LF on every platform.
- Added Windows and Linux CI plus regression tests for LF/CRLF equivalence, canonical receipt
  identity, shared launcher adoption, and executable shell entry points.

## 0.18.2 — 2026-08-21

- Added a bounded logical proof for the `CBPAUP0C` IMS BMP authorization-expiry workload through
  `PSBPAUTB`, `PAUTBPCB`, `DBPAUTP0`, `PAUTSUM0`, and `PAUTDTL1`.
- Curated eight source-grounded rules for BMP routing, hierarchy, GN/GNP traversal, inverted-date
  expiry, summary adjustments, DLET behavior, checkpoints, and the duplicated approved-count root
  deletion quirk.
- Added a source-faithful candidate, independent private mutation gate, deterministic local
  capture, differential comparator, z/OS capture contract, operational runbook, and signed IMS
  readiness receipt.
- Advanced IMS readiness gates 3–5 to passed and gate 7 to mechanism-ready while keeping live BMP
  execution and mainframe equivalence blocked until externally attested z/OS evidence exists.

## 0.18.1 — 2026-08-21

- Added deterministic HLASM parsing for programs, instructions, symbols, branches, macros, DSECTs, and fields.
- Added native IMS DBD/PSB parsing for databases, dataset groups, segments, fields, PCBs, sensitive segments, and program-to-PSB bindings.
- Added a bounded, source-faithful COBDATFT modernization candidate with private mutation gates.
- Added a graph-bound CICS, VSAM, IMS, and HLASM capability projection across readiness gates 1–8.
- Kept every technology fail-closed for mainframe equivalence until signed z/OS evidence exists.

## 0.18.0 — 2026-08-21

- Added deterministic native extraction for CICS CSD transactions, programs, files and mapsets;
  BMS maps and fields; EXEC CICS command spans; and IDCAMS VSAM clusters, components, alternate
  indexes and paths, each with exact source evidence.
- Added typed routing and lineage relationships from `CAVW` through `COACTVWC`, `CACTVWA`, CICS
  file resources, and the underlying CardXref, account, and customer VSAM objects.
- Curated eight graph-grounded account-view behavior rules and a bounded read-only modernization
  candidate with an independent private gate and mutation/negative coverage.
- Added an operator-safe real-CICS capture contract, redacted artifact manifest, mainframe identity
  requirements, differential comparator, and fail-closed signed readiness receipt.
- Added cross-platform launchers, JSON schemas, an operational runbook, deterministic development
  evidence, and full verification integration. Local proof cannot satisfy z/OS equivalence.

## 0.17.0 — 2026-08-16

- Added a canonical operational event envelope and append-only SQLite WAL reference ledger with
  monotonic sequence, correlation, trust, severity, time, previous-hash and content-hash fields.
- Added source observers for Factory, Portfolio, Recovery, Quality, Memory, Runtime and Audit with
  explicit expected latency, freshness, last observation, last identity change and trust class.
- Added resumable Server-Sent Events, bounded replay, heartbeat and live-status APIs so the local
  Control Tower updates without polling or manual refresh.
- Added operational alerts for dead letters, expired leases, stale runtime evidence, unavailable
  recovery projections and blocked release promotion, including opened/resolved ledger events.
- Upgraded the Graph Explorer into an Evidence Control Tower with connection, sequence, freshness,
  trust and active-alert indicators while keeping every operational surface strictly read-only.
- Added live runtime/audit snapshot reloading, portable event/status schemas, cross-platform
  launchers, production hardening guidance and Windows Python 3.12/3.13/3.14 discovery.
- Added event replay, chain tampering, source-change, freshness, alert, SSE and no-command-authority
  tests plus full verification integration.

## 0.16.0 — 2026-08-15

- Added a transactional durable control plane with a SQLite WAL reference backend and explicit
  contracts suitable for PostgreSQL and immutable object-store production adapters.
- Added atomic worker leasing, opaque bearer tokens stored only as SHA-256 digests, bounded
  heartbeats, lease expiry recovery, retry backoff and terminal dead-letter handling.
- Added crash-safe wave barriers and idempotent completion: passed cells are never dispatched
  twice and successor waves remain unavailable until every predecessor has passed.
- Added exactly-once consumption of human portfolio approvals, exact work-order identity checks,
  content-addressed receipt indexing and a tamper-evident durable event chain.
- Added cross-platform durable queue commands, versioned lease/state/snapshot schemas, operator
  guidance and a strictly read-only Recovery Control Tower with no dispatch authority.
- Added concurrent lease, worker termination, stale-token, replay, retry, dead-letter, wave-barrier,
  artifact-index and event-tampering tests plus full verification integration.

## 0.15.0 — 2026-08-15

- Added a deterministic portfolio controller that loads multiple bounded work orders, binds them to
  the exact knowledge-graph identity, and emits a content-addressed execution plan.
- Added file-scope, graph-scope, graph-dependency and declared-dependency conflict detection with
  stable serialization decisions and bounded parallel wave scheduling.
- Added explicit low, medium, high and critical risk classification; high-risk work and critical
  conflicts fail closed until approved by an external human authority.
- Added HMAC-signed, expiring, tamper-evident human approvals bound to the exact plan, required work
  orders and acknowledged conflicts; agent identities cannot approve portfolios.
- Added wave barriers, parallel cell dispatch, stop-on-failure behavior and composite portfolio run
  receipts while preserving independent private acceptance gates for every cell.
- Expanded the demo to bounded INTCALC, POSTTRAN and CREASTMT policy surfaces grounded in the
  existing CardDemo graph without claiming live z/OS equivalence.
- Added versioned portfolio manifest, plan, approval and run-receipt schemas, cross-platform CLI
  launchers, a read-only Portfolio Control Tower, and adversarial approval/scheduling tests.

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
