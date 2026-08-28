# FactoryDark.ai CardDemo Modernization Factory

Release: **v0.27.0 — offline data movement, dual-run, cutover, and rollback rehearsal**

v0.27 turns the bounded `AUTHFRDS` data proof into an operational migration rehearsal. A
content-addressed Db2-shaped journal applies five ordered inserts, updates, and deletes to
independent PostgreSQL- and Oracle-shaped projections. The controller stops after event two,
resumes from an exact checkpoint, detects duplicate replay without applying it twice, and requires
both targets to reconcile with the source before a simulated human approval can open cutover.

After cutover, the rehearsal injects a unilateral target divergence, detects it, restores both
targets to their exact pre-cutover identities, and confirms zero-event fixture RPO and a bounded
three-step recovery. The unified capability and data control-tower views expose this operational
posture without treating it as live Db2 evidence.

```bash
./migration-rehearsal.sh verify /path/to/aws-carddemo
./lightyear.sh verify
```

The source journal, target engines, approval, RPO, and RTO are deterministic development evidence.
No live Db2 log, customer data, production-scale timing, real cutover authorization, or mainframe
equivalence is claimed; `production_ready` and `mainframe_equivalent` remain false.

Previous milestone: **v0.26.1 — legacy live-model evidence bridge**

v0.26.1 recovers the retained v0.12 live OpenAI evaluation as independently inspectable historical
evidence. A fail-closed ZIP importer verifies the pinned archive identity, every content-addressed
run artifact, the event ledger, model-call provenance, reconstructed before/after workspaces, and
the original private-gate result. It then emits a current, schema-validated
`historical-model-evidence` receipt that appears in the quality dashboard.

The recovered run used `gpt-5.6-terra` through `openai-responses` for one INTCALC public-calibration
case. It passed after three model calls, using 101,127 input tokens and 701 output tokens at an
estimated cost of $0.210666. The archive contains hashes rather than raw prompts or model responses
and no retained credential. Its status is therefore `verified` and `historical-only`, never
`qualified`: it is one public legacy-schema run, not eight independently sealed evaluations across
four workloads or an approved portfolio execution.

```bash
./factory-qualification.sh history \
  /secure/archive/model-evaluation-20260813T072624Z.zip \
  work/legacy-model-evidence/historical-model-evidence.receipt.json
./factory-qualification.sh verify
```

Previous milestone: **v0.26.0 — multi-workload factory qualification**

v0.26 expands the governed model work cell from one INTCALC calibration surface into a bounded
four-workload qualification plane: `INTCALC`, `POSTTRAN`, `CREASTMT`, and the mixed PL/I–COBOL–Db2
`ACCTPL1` cell. Four public catalogs exercise 23 injected defects and eight clean cases through
workload-specific private gates. The deterministic reference worker repairs all published defects,
preserves every clean candidate, and records zero false acceptances.

Actual model promotion is stricter. It requires at least two distinct, independently sealed,
model-backed runs per workload and a passed four-cell portfolio execution. The qualification
receipt binds exact evaluation, run, model-call, prompt/context manifest, portfolio plan, approval,
checkpoint, and completion identities while measuring repair, correct-no-change, first-attempt,
false-acceptance, false-rejection, escalation, retry, resume, latency, token, and cost behavior. A
single critical false acceptance blocks promotion.

The portfolio now detects cross-workload conflicts, dispatches safe cells in parallel waves,
requires human approval for high-risk cells, and resumes without rerunning cells that already
passed. No model credential or independently retained holdout is committed, so the repository
proves the qualification mechanism but does not claim that a particular model is qualified.

```bash
./factory-qualification.sh verify
./portfolio-factory.sh verify
```

Model qualification remains distinct from native z/OS equivalence and production authorization;
`mainframe_equivalent` and `production_ready` remain false.

Previous milestone: **v0.25.1 — squash-safe reproducible build verification**

v0.25 closes the source-only delivery gap in the bounded mixed PL/I modernization cell. A
JDK-17-only build now compiles `MixedPliAuthorizationService`, creates a byte-reproducible
standalone JAR, executes five bounded tests into JUnit-compatible XML, inventories dependencies,
and emits a CycloneDX 1.5 SBOM. SLSA-shaped provenance binds those artifacts to a clean source
commit and to the MS #22 contract, fixtures, differential comparison, mutations, and development
receipt.

v0.25.1 makes that verification portable across repository history. It still rebuilds and compares
the full provenance envelope when the recorded source commit is reachable. After a squash merge,
it validates the unchanged signed source-tree binding and compares the JAR, JUnit report,
dependency inventory, and SBOM byte-for-byte against a rebuild from the equivalent merged source.
It never substitutes the squash commit into the original development receipt.

The committed proof uses an openly published development test key with release authorization
hard-disabled. GitHub Actions rebuilds the same evidence and adds GitHub workload-identity build
and SBOM attestations. Missing artifacts, edited reports, dependency changes, substituted commits,
foreign workflows, invalid signatures, and development-key release claims all fail closed and
demote PL/I development readiness.

```bash
./pli-build-attestation.sh verify
./lightyear.sh verify
```

This unlocks the bounded claim that the delivered Java artifact was compiled, tested, and
cryptographically bound to its evidence. It does not prove execution or equivalence of an IBM
Enterprise PL/I load module; `mainframe_equivalent` and `production_ready` remain false.

Earlier milestone: **v0.24.0 — PL/I discovery coverage and conformance lab**

v0.24 replaces the PL/I pack's line-oriented pattern boundary with a tokenized, statement-aware
front end for a published supported subset. A synthetic 27-case corpus exercises 22 construct
categories across programs, procedures, declarations, structures, includes, entry points, fixed
and varying records, SQL/SQLCA, file I/O, COBOL calls, decimal assignments, conditional/error
control, and bounded CICS/IMS references. Five intentionally blocked cases and seven mutation-
oriented cases prove that missing includes, shadowed calls, unsupported preprocessors/storage,
malformed comments, comments and strings, casing, spacing, and continuation lines cannot silently
create or omit graph facts.

The content-addressed coverage receipt records every recognized construct and located gap, binds
the corpus, support matrix, golden results, parser version, and canonical graph, and is now required
for PL/I discovery readiness. The unified capability projection publishes the breadth metrics while
labelling them `synthetic-static-supported-subset`. This does not claim arbitrary Enterprise PL/I
coverage, IBM compiler semantics, customer-source coverage, runtime behavior, or mainframe
equivalence.

```bash
./pli-conformance.sh verify
./lightyear.sh verify
```

PowerShell equivalents are provided through `pli-conformance.ps1` and `lightyear.ps1`.

Previous milestone: **v0.23.0 — stable composite estate and developer golden path**

v0.23 makes the separately governed PL/I extension naturally visible beside the canonical COBOL,
JCL, CICS, IMS, HLASM, VSAM, and Db2 estate without merging it into the canonical graph. A
content-addressed semantic-input manifest now declares the exact modern candidate files allowed to
influence the canonical semantic identity. Viewer, validator, documentation, and unrelated test
edits therefore no longer force every graph-bound receipt to be regenerated; declared candidate,
mapping, ontology, or legacy-source changes still invalidate evidence as intended.

The read-only composite projection contains 11,328 nodes and 13,470 relationships, including the
complete `ACCTPL1 → CBACT04C` call and `ACCTPL1 → SQL → CARDDEMO.AUTHFRDS` lineage. It has its own
hash and source evidence pack while retaining the exact canonical graph binding used by runtime and
audit evidence. The Explorer visibly labels this boundary and does not present composition as live
runtime proof, mainframe equivalence, or production readiness.

Start with the developer golden path:

```bash
./lightyear.sh doctor
./lightyear.sh demo
./lightyear.sh explorer
./lightyear.sh verify
```

PowerShell equivalents are available through `lightyear.ps1`. Missing Java, Maven, or Docker are
reported as optional-path limitations; missing Python, Git, semantic artifacts, or invalid evidence
contracts fail diagnostics with a remediation. The full claim boundary remains unchanged:
`mainframe_equivalent: false` and `production_ready: false`.

Earlier milestone: **v0.22.0 — mixed PL/I modernization proof cell**

v0.22 advances the bounded `ACCTPL1` mixed PL/I–COBOL–Db2 workload from discovery to a complete
local development proof. It pins fixed-width records, Db2 lookup behavior, decimal truncation, the
`OPTIONS(COBOL)` call contract into `CBACT04C`, ordered effects, and fail-closed error behavior. An
independent executable oracle and Python candidate compare seven boundary cases; nine deliberate
mutations prove the comparator rejects semantic drift. A production-shaped Java service and JUnit
suite provide the modernization seam used by CI.

The content-addressed receipt promotes only PL/I readiness gates 3–5. PL/I is now
`development_ready: true`, but gates 6 and 8 remain blocked because no customer-authorized,
compiled and executed PL/I baseline or signed live equivalence receipt exists. Gate 7 reports only
`mechanism_ready`. This is a complete proof for one bounded mixed workload—not general PL/I
coverage, production readiness, or live-mainframe equivalence.

```bash
./extension-foundation.sh verify
./pli-modernization.sh verify
./knowledge-graph.sh verify /path/to/aws-carddemo
```

Previous milestone: **v0.21.1 — unified capability projection**

v0.21.1 gives customers and auditors one evidence-bound readiness view across CICS, VSAM, IMS,
HLASM, PL/I, and Db2/Data. It distinguishes discovery, development proof, and live-mainframe
equivalence and binds every displayed status to exact graph, extension, data, and campaign evidence.

Previous milestone: **v0.21.0 — mainframe access readiness campaign**

v0.21 turns the MS #20 adapter contracts into one credential-safe, read-only customer campaign.
The campaign collects exact, graph-addressed observations from z/OSMF Jobs, a customer-approved
Db2 for z/OS catalog REST projection, and CICS CMCI. The three envelopes must share the exact
adapter set, graph identity, evidence class, and read-only posture before the aggregate receipt can
pass. Missing, duplicate, malformed, mixed-class, oversized, redirected, insecure, or tampered
evidence fails closed.

Credentials are read only from environment variables and are never written to profiles, captures,
receipts, errors, or logs. Live access requires verified HTTPS and a separate customer evidence
signing key. Raw response bodies are hashed and discarded. The identical parsers run against
committed IBM-shaped development responses today:

```bash
./mainframe-access.sh verify
./mainframe-access.sh simulate
```

When authorized access is available:

```bash
export LIGHTYEAR_MAINFRAME_BEARER='...'
export LIGHTYEAR_EXTENSION_EVIDENCE_KEY='at-least-32-bytes...'
./mainframe-access.sh live https://mainframe.example customer-campaign-key
```

PowerShell equivalents are provided. A passing live campaign proves bounded observations from the
configured source; it does not prove full source equivalence or production readiness. Customer-
authorized baselines, independent comparison, performance, CDC, cutover, rollback, and promotion
approval remain explicit gates, so `production_ready` remains `false`. See
[the mainframe access runbook](extensions/adapters/README.md).

Previous milestone: **v0.20.0 — trusted extension foundation**

v0.20 turns the verified factory into an extensible product boundary without pretending that
recorded or simulated evidence is live. Every adapter capture declares its evidence class, read-only
scope, source attestation, bounded artifacts, limitations, and exact graph identity. Content hashes,
optional signatures, recursive credential redaction, and fail-closed entity validation protect the
boundary. Deterministic replay preserves captured facts but can never increase their trust class.

The first language-pack proof adds PL/I programs, internal procedures, includes, file access,
embedded Db2 SQL, and a mixed-language call into the existing COBOL estate. It is emitted as a
content-addressed extension fragment bound to the exact v0.19 graph hash. This avoids silently
changing the canonical graph and invalidating its runtime, audit, portfolio, and control-tower
evidence.

```bash
./extension-foundation.sh verify
```

The bundled PL/I workload and adapter captures are reference fixtures. Live z/OSMF, Db2 catalog,
CICS CMCI, customer PL/I compilation, runtime equivalence, CDC, cutover, and production readiness
remain explicitly blocked until authorized customer evidence is available. See
[extensions/README.md](extensions/README.md).

Previous milestone: **v0.19.2 — multi-target data equivalence cell**

v0.19.2 turns the PostgreSQL-only live check into a target-adapter contract and adds Oracle
Database 26ai Free as the second implementation. Both adapters must report exact column metadata,
primary-key order, secondary-index order, normalized row values, bounded query results, commit
behavior, and rollback behavior. Missing, malformed, duplicate, or mismatched evidence fails
closed. Every live receipt binds the adapter version, canonical model, mapping, fixtures, generated
schema SQL, fixture SQL, verification SQL, container image identity, and observed results.

```bash
./data-modernization.sh live-postgres
./data-modernization.sh live-oracle
./data-modernization.sh live-all
```

The Oracle command expects the official Oracle Database Free image to exist locally. The default
is `oracle/database:23.26.1-free`; override it with `--oracle-image` when invoking the Python CLI.
Building or using the image requires accepting Oracle's license. No Oracle credential or database
output is persisted in the receipt. The Control Tower shows PostgreSQL and Oracle side by side and
clearly distinguishes offline development evidence from a live container receipt.

This milestone does not make Oracle a production migration target and does not prove source Db2
equivalence. Live Db2 catalog/data capture, PL/I lineage for this bounded workload, CDC, performance,
cutover, and rollback on customer infrastructure remain explicit gaps; `production_ready` stays
`false`.

Previous milestone: **v0.19.1 — Db2-to-PostgreSQL data modernization proof cell**

v0.19 adds a bounded, evidence-first modernization of the CardDemo `CARDDEMO.AUTHFRDS`
authorization table. It parses Db2 DDL/DCL and COPAUS2C embedded SQL, projects schema and
statement lineage into the knowledge graph, emits a target-neutral canonical model and PostgreSQL
schema, exercises mainframe encoding boundary fixtures, and issues a signed development-equivalence
receipt. The Control Tower now shows data checks and migration gaps. Run:

```bash
./data-modernization.sh verify /path/to/aws-carddemo
./data-modernization.sh live-postgres  # requires Docker
```

The live command runs PostgreSQL 16 in an ephemeral, network-isolated container. This is strong
offline development evidence, not live Db2/z/OS equivalence; `production_ready` therefore remains
`false` until the v0.20 mainframe campaign.

v0.18.5 converts the independent mutation-review findings into executable invariants. Directly
constructed private gates now have a regression test that pins output exposure to `false`; the
comparator's first-observed duplicate diagnostic policy is behavior-tested; and the normalization
ledger must match runtime scope and behavior exactly. Normalization owners, reasons, and ISO review
dates are mandatory, with reviews expiring fail-closed on the stated date. Both the focused
gauntlet and the full verifier run the governance check. The tracked-evidence clean-tree assertion
is retained as a preventive CI control, not described as a previously observed defect repair.

```powershell
.\verifier-gauntlet.ps1
.\verify.ps1
```

```bash
./verifier-gauntlet.sh
./verify.sh
```

Previous milestone: **v0.18.4 — verifier trust hardening**

v0.18.4 closes false-green paths in the load-bearing differential verifier. Duplicate keys and
record-count mismatches now fail independently, deterministic timestamps are compared exactly, and
a comparison with no records returns `indeterminate` with exit code `2` rather than claiming
equivalence. Security-relevant work-order flags accept JSON booleans only, while direct positive and
negative tests protect the builder holdout boundary. A separate CI escape gauntlet attacks the
verifier on Windows and Linux before the full factory suite runs.

| Claim | Current evidence | Boundary |
|---|---|---|
| INTCALC comparator rejects known escape classes | `tests/test_comparator_escape.py` and verifier-gauntlet CI | Development evidence only |
| Builder cannot see private holdout output by default | `tests/test_trust_boundaries.py` | Explicit per-gate exposure remains possible |
| CICS, VSAM, IMS, HLASM, PL/I, and Db2/Data readiness is visible in one projection | `knowledge/capabilities/mainframe-readiness.json` | PL/I and Db2/Data development-ready; none mainframe-equivalent |
| Live mainframe equivalence | No qualifying customer capture yet | **Blocked** |
| Production readiness | No production pilot evidence yet | **`production_ready: false`** |

```powershell
.\verifier-gauntlet.ps1
.\verify.ps1
```

```bash
./verifier-gauntlet.sh
./verify.sh
```

Previous milestone: **v0.18.3 — cross-platform deterministic evidence contract**

v0.18.3 hardens the complete factory for repeatable Windows and Linux operation. Every PowerShell
entry point now uses one Python 3.11+ resolver, managed CardDemo checkouts explicitly materialize
LF source, and canonical JSON/Markdown writers always emit UTF-8 with LF. Source evidence records
both the raw transport hash and a normalized logical-source hash; only the logical identity enters
semantic graph and evidence-pack receipts. Git attributes, dual-platform CI, and regression tests
prevent Python pinning, newline conversion, or lost shell executable bits from silently changing a
release. Raw hashes remain available for forensic chain of custody.

```powershell
.\verify.ps1
```

```bash
./verify.sh
```

Previous milestone: **v0.18.2 — bounded IMS logical proof cell**

v0.18.2 advances IMS from structural discovery to a bounded development proof. The cell follows
`CBPAUP0J -> CBPAUP0C -> PSBPAUTB/PAUTBPCB -> DBPAUTP0 -> PAUTSUM0/PAUTDTL1`, models its normal-path
GN/GNP/DLET/CHKP behavior, and preserves the source's duplicated approved-count root deletion test
as an explicit, mutation-tested legacy quirk. CICS, VSAM, IMS, and the bounded COBDATFT HLASM cell
are now development-proven; none is claimed mainframe-equivalent without live z/OS evidence.
The graph now parses CSD resources, BMS maps and fields, EXEC CICS commands, and IDCAMS KSDS,
ESDS, RRDS, alternate-index, path, and component definitions. The first proof follows `CAVW` to
`COACTVWC`, its `CACTVWA` screen, and ordered reads of `CXACAIX`, `ACCTDAT`, and `CUSTDAT`.
It also parses IMS DBD/PSB macros and HLASM programs, instructions, branches, macros, DSECTs, and
fields. The second bounded proof follows the COBOL call into `COBDATFT` and preserves its exact
fixed-position date conversion behavior, including the source's commented-out separator check.
The third proof models CBPAUP0C's expired pending-authorization purge against its IMS hierarchy.

```bash
./cics-vsam-readiness.sh verify
./cics-vsam-readiness.sh template work/cavw-live
./asm-readiness.sh verify
./ims-readiness.sh verify
./ims-readiness.sh template work/cbpaup0c-live
PYTHONPATH=src python3 -m lightyear_knowledge_graph capabilities
```

The local proof is mutation-tested and development-ready. The signed release gate intentionally
remains blocked until authorized operators supply `zos_observed` captures from real CICS, IMS, and
z/OS execution environments, independent comparators find no differences, and external signing
keys are present. See [readiness/cics-vsam/README.md](readiness/cics-vsam/README.md),
[readiness/asm-date/README.md](readiness/asm-date/README.md), and
[readiness/ims-expiry/README.md](readiness/ims-expiry/README.md).

Previous milestone: **v0.17.0 — live evidence and Control Tower plane**

v0.17 makes the existing Control Tower live. Factory, Portfolio, Recovery, Quality, Memory,
Runtime, and Audit remain independent authoritative stores; a new operational plane observes their
identities, emits hash-chained events, classifies freshness and trust, raises alerts, and streams
updates to the browser with resumable Server-Sent Events.

```bash
./live-control-tower.sh verify
./live-control-tower.sh serve
```

Open `http://127.0.0.1:8765`. The browser remains strictly read-only: it cannot approve, lease,
retry, dispatch, promote, or write exceptions. See
[control-tower/README.md](control-tower/README.md) for the production architecture and command-plane
hardening boundary.

An evidence-aware knowledge graph, source-faithful local oracle, differential harness, and
Java/Spring Batch candidate for AWS CardDemo. Together they form the first engineering cell of a
verified modernization factory.

v0.7 adds the first autonomous modernization loop. A deterministic controller accepts a bounded
work order, gives evidence-scoped context to planner and builder agents, runs independent private
gates, routes failures back without leaking holdout answers, and emits a content-addressed receipt
plus a hash-chained event ledger. The included offline mutation gauntlet injects five known INTCALC
faults and requires the factory to reject each defect before repairing it.

The oracle runs on Windows, macOS, or Linux with Python 3.11 or newer and has no runtime
dependencies outside the Python standard library. PowerShell and POSIX launchers automatically
select a supported interpreter and reject older runtimes before starting; set
`LIGHTYEAR_PYTHON` to an executable path to override the selection. The candidate uses Java 17,
Spring Boot 4.1, Spring Batch 6, Maven Wrapper, and an in-memory H2 Batch metadata store.

The knowledge graph deterministically indexes the complete pinned CardDemo estate—COBOL programs,
paragraphs, copybooks, fields, JCL jobs and steps, datasets, Java types, methods, tests, and software
dependencies. The `INTCALC` workload is the first vertical slice with explicit traceability from
legacy source to business rules, Java implementation, and verification scenarios.

v0.8 adds an append-only runtime evidence plane. Local executions and recorded adapter fixtures
are bound to exact graph entities, hash chained, reconciled into runtime truth states, and evaluated
under separate development-readiness and mainframe-equivalence policies. Synthetic replay can
exercise the machinery, but only evidence classified as `zos_observed` can satisfy mainframe
equivalence.

v0.9 turns that adapter boundary into a working read-only z/OSMF integration. An IBM-shaped local
server lets the complete Jobs/status/steps/spool flow run before a mainframe is available. The real
client enforces verified HTTPS, external credentials, response limits, content minimization, and an
explicit operator attestation before it can emit `zos_observed` evidence.

v0.10 adds an append-only governance layer across the factory. Hash-chained audit events bind
actors, actions, subjects, policy decisions, and evidence receipts to the exact graph identity.
Deterministic promotion policy, governed exceptions, optional signed checkpoints, release evidence
dossiers, and a read-only Evidence Control Tower make unattended execution inspectable without
allowing agents or dashboard state to declare their own success.

v0.11 closes the largest local autonomy boundary. Signed, expiring work orders pass a replay-safe
admission gate; planner, builder, failure analyst, provider, and verifier receive short-lived action-scoped
identities; protected values use one-use non-persistent leases; and deterministic gates can execute
through a digest-pinned Docker or Podman sandbox with no network, read-only filesystems, non-root
identity, dropped capabilities, no-new-privileges, and resource ceilings. Simulation proves policy
construction but cannot satisfy the new hardened-execution release gate.

v0.11.1 closes the live-evidence loop without weakening that gate. A Docker/Podman probe now proves
only the container boundary. Hardened readiness requires a passed factory receipt that binds the
signed admission, exact work order and policy, scoped agent-action attestations, protected-value
posture, and enforced acceptance-gate hashes. The audit plane normalizes all three evidence classes,
rejects partial or tampered proof, and can project a live run into the Control Tower and dossier.

v0.11.2 corrects the host-to-container workspace boundary discovered by the first Apple Silicon
live run. The controller now translates both `PYTHONPATH` and `LIGHTYEAR_FACTORY_WORKSPACE` to
their `/workspace` container paths before launching a gate, while retaining the read-only host bind.

v0.12 makes model-backed work measurable and bounded. A replaceable provider sits behind planner,
builder, and failure-analysis roles; a context assembler packages approved graph neighborhoods,
shared source excerpts, and candidate files; an atomic patch broker validates every proposed edit;
and independent call receipts record model, hashes, tokens, latency, cost estimate, and budgets.
A 36-fault public calibration suite exercises the work cell while remaining explicitly distinct
from externally controlled sealed holdouts and mainframe evidence.

v0.12.1 hardens live evaluations after the first successful model-driven smoke repair. Transient
rate limits use bounded Retry-After-aware backoff with jitter, while billing and hard-quota errors
stop immediately. Every case is checkpointed, global and per-case token/call/cost budgets fail
closed, partial receipts survive interruption, and a stopped evaluation can resume without
repeating completed cases. Model calls cap output at 25,000 tokens by default and receipt retry
metadata without storing prompts, credentials, or provider error bodies.

v0.12.2 removes the largest source of repeated model input. The planner now receives a compact
graph and evidence catalog, selects source capsule IDs in its plan, and the controller retrieves
only those full excerpts for the builder. The OpenAI adapter calls the Responses input-token count
endpoint before generation and rejects any call above its configured ceiling. Prompt-free request
manifests and an audience-safe transcript make the mediated role exchange inspectable without
exposing verifier-private output.

v0.13 turns model evaluation into a promotion-grade evidence plane. An independent evaluator can
HMAC-sign an expiring holdout envelope; the controller verifies its identity and runs opaque case
references without publishing mutation text, case names, or categories. The scorecard separately
measures rejected faults, repaired faults, correct no-change decisions, first-attempt repairs,
evidence-selection precision, privacy leaks, unauthorized edits, tokens, and cost. Public
calibration can never satisfy the sealed-evidence check, and the new Quality dashboard is a
read-only projection rather than a source of acceptance authority.

v0.14 gives the factory governed institutional memory. Passed repairs, correct no-change outcomes,
and verified failures become content-addressed experiences bound to their graph nodes, source
capsules, paths, gate hashes, and run identities. Positive memories can carry bounded edit
templates; negative memories retain only non-executable fingerprints. Sealed holdouts are excluded
entirely, verifier-private artifacts never cross the audience boundary, and a changed graph or
source-evidence identity immediately makes an experience stale. The Memory dashboard is a
read-only projection; current source and fresh gates remain authoritative.

v0.15 scales the controller from one work cell to a portfolio. A deterministic planner binds every
work order to the exact graph and source scope, detects file collisions, shared graph scope and
declared dependencies, then schedules non-conflicting cells into bounded parallel waves. High-risk
work and critical conflicts fail closed until an external human signs the exact plan hash. The
approval authorizes dispatch only: each cell must still pass its independent private gates. The
included CardDemo portfolio coordinates INTCALC, POSTTRAN and statement generation, and its
read-only dashboard cannot approve, resolve, or launch work.

## What it does

1. Builds a deterministic, provenance-rich graph of the entire CardDemo application estate,
   including native CICS, BMS, VSAM, IMS DBD/PSB, and HLASM structures.
2. Maps `INTCALC`, `CAVW`, `COBDATFT`, and `CBPAUP0C` business rules from legacy evidence to bounded
   candidates and independent tests.
3. Produces audience-filtered context packages so implementers cannot see private verifier assets.
4. Serves bounded, searchable visual perspectives of the graph from a local web application.
5. Explains the purpose, direction, evidence policy, and sources behind every visible relationship.
6. Opens content-addressed source excerpts with exact evidence lines highlighted.
7. Answers who, what, where, when, why, how, impact, lineage, and verification questions about
   selected nodes, relationships, or the estate.
8. Exports a lossless, disposable Neo4j projection without surrendering graph ownership.
9. Executes bounded planner, builder, failure-analyst, and verifier roles under a deterministic run controller.
10. Isolates each run, enforces edit budgets, protects verifier-private evidence, and records every
    transition and artifact by hash.
11. Shows factory runs, acceptance gates, changes, and receipts in the local control room.
12. Reads CardDemo-compatible fixed-width ASCII datasets and COBOL signed zoned decimals.
13. Executes and differentially verifies the source-faithful `CBACT04C` behavior.
14. Records graph-addressed runtime observations through a replaceable adapter contract.
15. Distinguishes static-only, runtime-observed, and runtime-contradicted graph claims.
16. Blocks mainframe-equivalence claims until every required entity has z/OS-observed evidence.
17. Rehearses the real z/OSMF REST integration against a deterministic local connection simulator.
18. Captures authorized JES job, step, program, DD-allocation, return-code, timestamp, and spool-hash evidence.
19. Unifies graph, source, factory, runtime, and release decisions in a hash-chained audit ledger.
20. Detects changed, deleted, reordered, duplicated, or stale audit events and projections.
21. Produces deterministic release dossiers and blocks promotion until governed evidence passes.
22. Shows trust posture, policy rationale, evidence lineage, exceptions, and checkpoints in a read-only Control Tower.
23. Verifies signed work orders against trusted issuers, expiry, policy identity, and one-use nonces.
24. Issues short-lived, action-scoped identities for planner, builder, failure analyst, provider, and verifier roles.
25. Brokers allowlisted protected values through one-use leases without persisting their contents.
26. Plans multiple graph-bound work cells into deterministic, conflict-free execution waves.
27. Requires an expiring human signature for high-risk work and critical conflicts.
28. Stops later waves when any cell fails and emits one composite portfolio receipt.

## Run the v0.15 portfolio locally

Planning and validation require no model, mainframe, or secret:

```bash
./portfolio-factory.sh plan
./portfolio-factory.sh verify
```

The sample includes a high-risk financial-posting cell, so dispatch requires an external key and a
named human approver:

```bash
export LIGHTYEAR_PORTFOLIO_APPROVAL_KEY="$(openssl rand -hex 32)"
export LIGHTYEAR_PORTFOLIO_APPROVER="your-name"
./portfolio-factory.sh sign
./portfolio-factory.sh run
```

The key and signature are not committed. Changing a work order, graph snapshot, conflict, wave or
policy changes the plan hash and invalidates the approval.
26. Runs acceptance gates through a digest-pinned, networkless, non-root Docker or Podman sandbox.
27. Blocks promotion when only simulated execution-policy conformance exists.
28. Prevents a successful container-only probe from impersonating a signed factory run.
29. Binds admitted work orders, agent-action attestations, and OCI gate evidence in one receipt.
30. Ingests live execution evidence while leaving mainframe equivalence independently blocked.
31. Assembles content-addressed model context from approved graph roots and source capsules.
32. Places replaceable model providers behind controller-enforced call, token, cost, byte, and time budgets.
33. Applies model proposals through an atomic allowlisted patch broker with line and file ceilings.
34. Returns sanitized failure envelopes without exposing private gate output to the builder.
35. Records every model call as a prompt-free provenance artifact linked into the run receipt.
36. Measures autonomous repair rate and false acceptance independently across public or sealed evaluations.
37. Retries transient model throttles within a bounded receipted policy and stops on hard quota errors.
38. Checkpoints each evaluation case and resumes without repeating completed model work.
39. Enforces evaluation-wide call, token, cost, and pacing limits in addition to per-case budgets.
40. Sends compact evidence catalogs to planners and only plan-selected source capsules to builders.
41. Counts exact Responses API input tokens before generation and rejects oversized calls.
42. Records request manifests with context statistics and selected evidence identities.
43. Renders a controller-mediated role transcript with verifier-private content redacted by default.
44. Admits externally signed, expiring sealed holdout catalogs without exposing case answers to agents.
45. Tests clean inputs so unnecessary changes count as failures rather than successful activity.
46. Applies a versioned factory-quality policy across repair, safety, evidence, privacy, and efficiency.
47. Compares evaluation receipts safety-first and projects qualified or blocked status in the Quality tab.
48. Promotes only controller-observed, independently verified outcomes into semantic memory.
49. Distinguishes verified repairs, correct no-change decisions, and non-executable negative memory.
50. Excludes sealed holdouts and verifier-private artifacts from implementer memory by construction.
51. Binds experiences to exact graph, evidence-pack, work-order, ledger, and workspace identities.
52. Invalidates retrieval when graph or source-evidence identities change.
53. Retrieves bounded graph-, path-, and vocabulary-matched experience cards for planners and builders.
54. Detects tampering, stale evidence, privacy contamination, and executable negative edits.
55. Projects memory coverage, outcomes, lessons, and identities in the read-only Memory tab.
56. Streams canonical operational events from every control-plane domain over resumable SSE.
57. Shows per-source freshness, observation age, identity change, trust class, and stream sequence.
58. Raises visible alerts for dead letters, expired leases, stale runtime evidence, and blocked releases.
59. Reloads runtime and audit projections when their authoritative snapshots change.
60. Keeps the live UI query-only until an authenticated, signed, policy-governed command API exists.

The included `candidate-java` module is the first modernization candidate. It consumes and emits
the same fixed-width records as the oracle, including COBOL signed zoned decimals.

This is a **temporary local oracle derived from source**, not independent proof of z/OS behavior.
It does not emulate VSAM locking, JES, Language Environment behavior, or EBCDIC collation. Replace
or corroborate it with captured z/OS executions before making production equivalence claims.

## Windows setup

Open PowerShell in the extracted project directory. The quickest path requires no package
installation:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\test.ps1
```

Run the deterministic demonstration:

```powershell
.\oracle.ps1 demo --work-dir .\work\demo
```

Build and differentially verify the Java/Spring Batch candidate:

```powershell
.\verify.ps1
```

This runs both Python and Java unit tests, packages the executable Spring Boot JAR, executes the
oracle and candidate on a deterministic fixture, rebuilds the knowledge graph, and fails if the
graph is stale, a rule loses traceability, or any business field differs.

## Knowledge graph

Build the full graph using a sibling clone of the pinned AWS CardDemo repository:

```powershell
.\knowledge-graph.ps1 build ..\aws-mainframe-modernization-carddemo
```

On macOS or Linux:

```bash
./knowledge-graph.sh build ../carddemo-upstream
```

Inspect graph statistics or ask for a rule-focused implementer context package:

```bash
PYTHONPATH=src python3 -m lightyear_knowledge_graph stats
PYTHONPATH=src python3 -m lightyear_knowledge_graph context \
  --node rule:intcalc:monthly-interest --depth 2 --audience implementer
```

The generated snapshot, its content-addressed receipt, curated mappings, and schema live under
`knowledge/`. See `knowledge/README.md` for the trust model, graph ontology, queries, and roadmap.

## Autonomous factory

Run the complete offline factory benchmark on macOS or Linux:

```bash
./factory-benchmark.sh
```

On Windows:

```powershell
.\factory-benchmark.ps1
```

The benchmark creates a new timestamped folder under `work/`, injects five different regressions
into isolated copies of the INTCALC policy surface, proves each faulty baseline fails a private
gate, permits a bounded repair, and reruns the gate. Its receipt reports repairs and false
acceptances independently.

Then start the explorer and open the **Factory** tab:

```bash
./graph-explorer.sh
```

The control room shows the station timeline, gates, attempts, changed paths, receipt hash, and
audience-safe run history. v0.12 also shows provider, model, model-call count, token usage, estimated
cost, and intelligence-receipt identity. This is deliberately observable autonomy: “dark” means
unattended execution, not invisible decisions.

Validate the 36-fault public calibration catalog without making an API call:

```bash
./model-workcell.sh validate
```

Run the live model evaluation after supplying the provider key outside the repository:

```bash
export OPENAI_API_KEY="..."
export LIGHTYEAR_FACTORY_MODEL="gpt-5.6-terra"
export LIGHTYEAR_MODEL_INPUT_USD_PER_MILLION="2.00"
export LIGHTYEAR_MODEL_OUTPUT_USD_PER_MILLION="12.00"
export LIGHTYEAR_MODEL_MAX_INPUT_TOKENS_PER_CALL="60000"
./model-workcell.sh evaluate
```

Live evaluations require environment-only token prices so the controller can enforce its cost
budget; update them whenever the selected model, service tier, region, or context price changes.
The checked-in suite is public calibration, not a blind benchmark. Supply an independently retained
catalog with `evaluation_class` set to `sealed-holdout` to measure blind generalization without
disclosing mutation details to workers. If a run stops, resume it without repeating completed cases:

```bash
./model-workcell.sh resume work/model-evaluation-YYYYMMDDTHHMMSSZ
```

Inspect what the controller passed between roles after a run. This is not direct agent-to-agent
chat; it is an ordered view of independently stored artifacts. Verifier-private content remains
redacted unless an authorized verifier explicitly requests it:

```bash
./model-workcell.sh transcript \
  work/model-evaluation-YYYYMMDDTHHMMSSZ/runs \
  eval-category-balance-length
```

Set `LIGHTYEAR_MODEL_TOKEN_PREFLIGHT=false` only for an offline compatible endpoint that does not
implement `POST /v1/responses/input_tokens`. Disabling it removes exact pre-generation token
admission and is recorded in model-call evidence.

## Runtime evidence

Build the deterministic local capture and recorded z/OS-shaped replay fixture:

```bash
./runtime-evidence.sh build
PYTHONPATH=src python3 -m lightyear_runtime inspect
```

Open the explorer's **Runtime** tab to inspect adapter runs, chained events, trust policy results,
and limitations. Node and edge inspectors show the projected runtime state, confidence class,
observed operation, and run identity. The included replay fixture and z/OSMF simulator are
explicitly `simulated`; neither can satisfy the `mainframe_equivalence` policy. See
`knowledge/runtime/README.md` for the evidence contract.

Rehearse the z/OSMF adapter locally:

```bash
./zosmf-adapter.sh simulate
./zosmf-adapter.sh verify
```

When access is available, configure credentials in the launching terminal, diagnose the read-only
connection, then capture one known job. The adapter does not submit or modify jobs:

```bash
export ZOSMF_BASE_URL="https://zosmf.example.com:10443"
export ZOSMF_SYSTEM_ALIAS="SY1"
export ZOSMF_USER="IBMUSER"
export ZOSMF_PASSWORD="..."

PYTHONPATH=src python3 -m lightyear_runtime zosmf-diagnose \
  --owner IBMUSER --prefix 'INTCALC*'

PYTHONPATH=src python3 -m lightyear_runtime capture-zosmf \
  --job-name INTCALC --job-id JOB00001 \
  --output work/zosmf-capture/intcalc.runtime.snapshot.json.gz \
  --attest-real-zos
```

`--attest-real-zos` is accepted only for non-loopback HTTPS and records a deliberate provenance
decision. Credentials, authentication headers, raw spool bodies, and returned server URLs are not
written to the evidence snapshot. See `knowledge/runtime/zosmf/README.md` for CA, mutual-TLS,
bearer-token, mapping, and first-connection guidance.

Repeated collections may reuse a human-readable run ID. The API and control room address each
physical run through a stable, path-opaque `run_key`, preventing collisions without exposing local
filesystem paths.

## Audit ledger and Evidence Control Tower

Build or verify the canonical audit snapshot and release dossier:

```bash
./audit-control-tower.sh build
./audit-control-tower.sh verify
```

Then run `./graph-explorer.sh` and open the **Audit** tab. The demo release is correctly shown as
blocked because local and simulated evidence proves neither mainframe equivalence nor live
hardened-runtime enforcement. The ledger is the source of truth; dashboard metrics and dossiers
are rebuildable projections. Configure
`LIGHTYEAR_AUDIT_SIGNING_KEY` only through the environment when signed checkpoints are required.
See `audit/README.md` for policy authority, exceptions, schemas, signing, privacy, and production
hardening gaps.

## Hardened execution

Verify the deterministic policy and OCI invocation contract without requiring Docker:

```bash
./hardened-execution.sh verify
```

When Docker Desktop or Podman is available, run a live container-boundary probe:

```bash
./hardened-execution.sh probe docker
```

The canonical receipt remains explicitly simulated and non-production-ready. A probe proves OCI
isolation but deliberately reports `production_ready: false` until a signed work order actually
runs. To execute the complete admitted path and generate a live audit projection:

```bash
export LIGHTYEAR_WORK_ORDER_SIGNING_KEY="$(openssl rand -hex 32)"
export LIGHTYEAR_IDENTITY_SIGNING_KEY="$(openssl rand -hex 32)"
./hardened-execution.sh admitted-run docker
```

The generated factory receipt is the evidence input that can pass hardened-execution readiness;
mainframe equivalence remains a separate gate. See `factory/README.md` for the trust boundary and
artifact locations.

Execute a specific approved work order with the local reference workers:

```bash
PYTHONPATH=src python3 -m lightyear_factory run \
  --work-order factory/work-orders/intcalc-repair.example.json \
  --source-root . \
  --runs-root work/factory-runs \
  --provider local
```

To use model-backed planner, builder, and failure-analysis adapters, keep the API key in the launching
terminal and select the OpenAI provider:

```bash
export OPENAI_API_KEY="your-api-key"
export LIGHTYEAR_FACTORY_MODEL="gpt-5.6-terra"
PYTHONPATH=src python3 -m lightyear_factory run \
  --work-order factory/work-orders/intcalc-repair.example.json \
  --provider openai
```

The agents do not decide acceptance. The controller validates their structured artifacts, applies
only authorized exact edits, and trusts only deterministic gates. See `factory/README.md` for the
architecture, contracts, security boundaries, receipts, and mainframe-evidence handoff.

## Visual Graph Explorer

On macOS or Linux, start the explorer from the repository root:

```bash
./graph-explorer.sh
```

On Windows:

```powershell
.\graph-explorer.ps1
```

It opens `http://127.0.0.1:8765` and provides seven curated perspectives, including the bounded
PL/I authorization-risk lineage, full-graph search,
bounded neighborhoods, node and edge inspection, source-code evidence, and implementer/verifier
views. The server binds only to the local machine by default and uses Python's standard library; it
does not upload graph data.

The default Explorer artifact is `knowledge/composite/estate.snapshot.json.gz`. Its visible trust
banner shows both the canonical and composite identities. Canonical runtime and audit evidence
continues to bind to `knowledge/graph.snapshot.json.gz`; the overlay cannot promote those claims.

Do not expose the verifier view to implementation agents. It includes private holdout metadata.
The current local audience selector demonstrates the policy boundary; it is not authentication.

### Edge and source inspection

Click a drawn edge or a relationship in the entity inspector. The Edge Inspector explains the
relationship in plain language, shows its direction and governed semantics, and lists direct plus
endpoint source evidence. Click an evidence card to open the content-addressed source excerpt with
the supporting lines highlighted. The browser supplies only an owner ID and evidence index; it
cannot request an arbitrary local path.

Select **Ask about relationship** to focus graph chat on the exact edge. Questions such as `Why
does this relationship exist?`, `What source supports it?`, and `What would be affected if this
connection changed?` remain bounded by the selected audience and evidence package.

The relationship catalog lives in `knowledge/ontology/relationships.json`. Canonical source
evidence lives under `knowledge/evidence/`; the composite source pack, including PL/I excerpts,
lives under `knowledge/composite/`.

### Grounded graph chat

Open the **Ask graph** tab, select a node, and ask questions such as:

- `What is the monthly interest rule?`
- `Where does INTCALC read and write data?`
- `Why is the final-account behavior preserved?`
- `How does INTCALC work end to end?`
- `What would be affected if the account copybook changed?`
- `What evidence verifies this node?`

Grounded local mode is available immediately. To enable higher-quality model synthesis, set an API
key only in the terminal that launches the server:

```bash
export OPENAI_API_KEY="your-api-key"
export LIGHTYEAR_OPENAI_MODEL="gpt-5.6"
./graph-explorer.sh
```

The key never reaches the browser. The OpenAI request contains only a bounded evidence package and
short conversation history, uses strict JSON Schema output, and disables API response storage.
Answers are rejected if they cite evidence outside their retrieval package. See
`knowledge/chat/README.md` for the answer pipeline, quality contract, and production security gaps.

### Optional Neo4j projection

Export the canonical snapshot into deterministic Neo4j bulk-import CSVs:

```bash
PYTHONPATH=src python3 -m lightyear_knowledge_graph export-neo4j \
  --output-dir work/neo4j-export
```

Use Neo4j for richer Cypher queries, Browser, or Bloom if useful, but treat that database as a
regenerable read model. LIGHTYEAR's proprietary value remains in the ontology, verified mappings,
evidence lineage, policies, graph history, and learning loop. See `knowledge/neo4j/README.md` for
the projection contract, import choices, example queries, and security boundary.

Optional editable installation for developers:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
carddemo-oracle demo --work-dir .\work\demo
```

The command creates:

```text
work/demo/
├── input/
│   ├── acctdata.txt
│   ├── cardxref.txt
│   ├── discgrp.txt
│   └── tcatbal.txt
└── oracle-output/
    ├── acctdata.txt
    ├── transactions.txt
    ├── canonical.json
    └── receipt.json
```

## Run against the upstream CardDemo ASCII fixtures

Clone and pin CardDemo separately:

```powershell
git clone https://github.com/aws-samples/aws-mainframe-modernization-carddemo.git
Set-Location aws-mainframe-modernization-carddemo
git checkout 59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e
Set-Location ..\lightyear-carddemo-oracle
```

Then run:

```powershell
.\oracle.ps1 run `
  --input ..\aws-mainframe-modernization-carddemo\app\data\ASCII `
  --output .\work\carddemo-oracle `
  --processing-date 2022071800 `
  --timestamp 2022-07-18-00.00.00.000000
```

The supplied CardDemo fixture is useful as a broad compatibility check. The synthetic demo adds
targeted coverage for explicit disclosure rates, default-rate fallback, and the final-account edge
case.

## Compare a candidate implementation

Your Java, Python, Go, or agent-generated candidate should write CardDemo-compatible
`acctdata.txt` and `transactions.txt` files. Compare them with:

```powershell
.\oracle.ps1 compare `
  --expected .\work\demo\oracle-output `
  --actual .\work\candidate-output `
  --report .\work\comparison.json
```

The command returns exit code `0` when equivalent, `1` when verified differences exist, and `2`
when the verifier cannot establish a meaningful result. Duplicate keys, population counts,
timestamps, financial fields, identifiers, account mutations, and all business fields are checked.
Only the documented rules in [spec/comparison-normalizations.json](spec/comparison-normalizations.json)
may normalize or exclude fields.

## Java/Spring Batch candidate

The candidate is intentionally small and auditable:

1. `InterestCalculationTasklet` owns the file-oriented batch boundary.
2. `CardDemoRecordCodec` parses and renders the upstream fixed-width layouts.
3. `ZonedDecimal` implements COBOL overpunch decoding and encoding.
4. `InterestCalculationService` contains the business transformation without framework coupling.
5. The Python comparator acts as the executable acceptance contract.

Run the JAR directly after `candidate-java\mvnw.cmd package`:

```powershell
java -jar .\candidate-java\target\carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar `
  --carddemo.input-dir=.\work\demo\input `
  --carddemo.output-dir=.\work\candidate-output `
  --carddemo.processing-date=2022071800 `
  --carddemo.timestamp=2022-07-18-00.00.00.000000 `
  --carddemo.final-account-policy=source-faithful
```

See `candidate-java/README.md` for the implementation design and standalone commands.

## Important discovered behavior

The source's final account is not rewritten in the normal loop. `CBACT04C` sets end-of-file inside
the final read after its outer `IF` has already been evaluated, so the associated `ELSE` does not
run. The default `source-faithful` mode preserves this source-derived behavior.

To compare with the likely intended behavior instead:

```powershell
.\oracle.ps1 demo --work-dir .\work\intended --final-account-policy intended
```

This difference is exactly why the modernization harness must reproduce observed behavior before
deciding whether a legacy behavior should be preserved or intentionally corrected.

## Next factory increments

Once a candidate can pass the visible cases:

1. Run the v0.14 work cell against an independently retained sealed holdout and establish the first
   honest model baseline: repair rate, false acceptance, escalations, latency, and cost.
2. Capture independent z/OS executions and attach runtime observations to graph entities.
3. Externalize the audit log to immutable retention with managed asymmetric signing and trusted time.
4. Move signed admission and identity credentials from HMAC to KMS-backed asymmetric trust.
5. Expand private holdouts and verified rule mappings to posting and statement-generation workloads.
6. Add conflict-aware parallel work cells, graph-delta memory, and human approval for high-risk
   changes.
7. Issue a production acceptance receipt only after structural, behavioral, security, operational,
   and mainframe-backed verification policies pass.

The pinned workload specification is in `spec/carddemo-intcalc.json`.
