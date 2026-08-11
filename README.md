# LIGHTYEAR CardDemo Modernization Factory

Release: **v0.8.0 — runtime evidence plane**

An evidence-aware knowledge graph, source-faithful local oracle, differential harness, and
Java/Spring Batch candidate for AWS CardDemo. Together they form the first engineering cell of a
verified modernization factory.

v0.7 adds the first autonomous modernization loop. A deterministic controller accepts a bounded
work order, gives evidence-scoped context to planner and builder agents, runs independent private
gates, routes failures back without leaking holdout answers, and emits a content-addressed receipt
plus a hash-chained event ledger. The included offline mutation gauntlet injects five known INTCALC
faults and requires the factory to reject each defect before repairing it.

The oracle runs on Windows, macOS, or Linux with Python 3.11 or newer and has no runtime
dependencies outside the Python standard library. macOS/Linux launchers automatically select a
supported interpreter and reject Apple's bundled Python 3.9 before starting; set
`LIGHTYEAR_PYTHON` to override the selection. The candidate uses Java 17, Spring Boot 4.1,
Spring Batch 6, Maven Wrapper, and an in-memory H2 Batch metadata store.

The knowledge graph deterministically indexes the complete pinned CardDemo estate—COBOL programs,
paragraphs, copybooks, fields, JCL jobs and steps, datasets, Java types, methods, tests, and software
dependencies. The `INTCALC` workload is the first vertical slice with explicit traceability from
legacy source to business rules, Java implementation, and verification scenarios.

v0.8 adds an append-only runtime evidence plane. Local executions and recorded adapter fixtures
are bound to exact graph entities, hash chained, reconciled into runtime truth states, and evaluated
under separate development-readiness and mainframe-equivalence policies. Synthetic replay can
exercise the machinery, but only evidence classified as `zos_observed` can satisfy mainframe
equivalence.

## What it does

1. Builds a deterministic, provenance-rich graph of the entire CardDemo application estate.
2. Maps `INTCALC` business rules from COBOL evidence to Java code and independent tests.
3. Produces audience-filtered context packages so implementers cannot see private verifier assets.
4. Serves bounded, searchable visual perspectives of the graph from a local web application.
5. Explains the purpose, direction, evidence policy, and sources behind every visible relationship.
6. Opens content-addressed source excerpts with exact evidence lines highlighted.
7. Answers who, what, where, when, why, how, impact, lineage, and verification questions about
   selected nodes, relationships, or the estate.
8. Exports a lossless, disposable Neo4j projection without surrendering graph ownership.
9. Executes bounded planner, builder, and verifier roles under a deterministic run controller.
10. Isolates each run, enforces edit budgets, protects verifier-private evidence, and records every
    transition and artifact by hash.
11. Shows factory runs, acceptance gates, changes, and receipts in the local control room.
12. Reads CardDemo-compatible fixed-width ASCII datasets and COBOL signed zoned decimals.
13. Executes and differentially verifies the source-faithful `CBACT04C` behavior.
14. Records graph-addressed runtime observations through a replaceable adapter contract.
15. Distinguishes static-only, runtime-observed, and runtime-contradicted graph claims.
16. Blocks mainframe-equivalence claims until every required entity has z/OS-observed evidence.

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
audience-safe run history. This is deliberately observable autonomy: “dark” means unattended
execution, not invisible decisions.

## Runtime evidence

Build the deterministic local capture and recorded z/OS-shaped replay fixture:

```bash
./runtime-evidence.sh build
PYTHONPATH=src python3 -m lightyear_runtime inspect
```

Open the explorer's **Runtime** tab to inspect adapter runs, chained events, trust policy results,
and limitations. Node and edge inspectors show the projected runtime state, confidence class,
observed operation, and run identity. The included replay fixture is explicitly `simulated`; it
cannot satisfy the `mainframe_equivalence` policy. See `knowledge/runtime/README.md` for the
adapter boundary and the future z/OS capture contract.

Repeated collections may reuse a human-readable run ID. The API and control room address each
physical run through a stable, path-opaque `run_key`, preventing collisions without exposing local
filesystem paths.

Execute a specific approved work order with the local reference workers:

```bash
PYTHONPATH=src python3 -m lightyear_factory run \
  --work-order factory/work-orders/intcalc-repair.example.json \
  --source-root . \
  --runs-root work/factory-runs \
  --provider local
```

To use model-backed planner, builder, and verifier adapters, keep the API key in the launching
terminal and select the OpenAI provider:

```bash
export OPENAI_API_KEY="your-api-key"
export LIGHTYEAR_FACTORY_MODEL="gpt-5.6"
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

It opens `http://127.0.0.1:8765` and provides five curated perspectives, full-graph search,
bounded neighborhoods, node and edge inspection, source-code evidence, and implementer/verifier
views. The server binds only to the local machine by default and uses Python's standard library; it
does not upload graph data.

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

The relationship catalog lives in `knowledge/ontology/relationships.json`. The self-contained
source pack and receipt live under `knowledge/evidence/`.

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

The command returns exit code `0` when equivalent and `1` when differences exist. Timestamps are
normalized out of the comparison; financial fields, identifiers, account mutations, and all other
business fields are compared exactly.

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

## Next factory increment

Once a candidate can pass the visible cases:

1. Capture independent z/OS executions and attach runtime observations to graph entities.
2. Replace copy isolation and advisory network denial with an enforced container or microVM policy.
3. Add authenticated worker identities, signed work orders, admission policy, and secret brokering.
4. Expand private holdouts and verified rule mappings to posting and statement-generation workloads.
5. Add conflict-aware parallel work cells, graph-delta memory, and human approval for high-risk
   changes.
6. Issue a production acceptance receipt only after structural, behavioral, security, operational,
   and mainframe-backed verification policies pass.

The pinned workload specification is in `spec/carddemo-intcalc.json`.
