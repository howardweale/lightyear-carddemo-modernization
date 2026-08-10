# LIGHTYEAR CardDemo Modernization Factory

Release: **v0.4.0 — visual graph explorer and optional Neo4j projection**

An evidence-aware knowledge graph, source-faithful local oracle, differential harness, and
Java/Spring Batch candidate for AWS CardDemo. Together they form the first engineering cell of a
verified modernization factory.

v0.4 makes the factory model directly explorable in a local browser and adds a deterministic
Neo4j projection. The canonical graph remains LIGHTYEAR-controlled, portable, content-addressed,
and independent of any graph database.

The oracle runs on Windows, macOS, or Linux with Python 3.11 or newer and has no runtime
dependencies outside the Python standard library. The candidate uses Java 17, Spring Boot 4.1,
Spring Batch 6, Maven Wrapper, and an in-memory H2 Batch metadata store.

The knowledge graph deterministically indexes the complete pinned CardDemo estate—COBOL programs,
paragraphs, copybooks, fields, JCL jobs and steps, datasets, Java types, methods, tests, and software
dependencies. The `INTCALC` workload is the first vertical slice with explicit traceability from
legacy source to business rules, Java implementation, and verification scenarios.

## What it does

1. Builds a deterministic, provenance-rich graph of the entire CardDemo application estate.
2. Maps `INTCALC` business rules from COBOL evidence to Java code and independent tests.
3. Produces audience-filtered context packages so implementers cannot see private verifier assets.
4. Serves bounded, searchable visual perspectives of the graph from a local web application.
5. Exports a lossless, disposable Neo4j projection without surrendering graph ownership.
6. Reads CardDemo-compatible fixed-width ASCII datasets and COBOL signed zoned decimals.
7. Executes the source-faithful `CBACT04C` interest-calculation behavior.
8. Writes canonical output and hashed evidence receipts.
9. Compares the modernization candidate with the oracle exactly on business fields.

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
bounded neighborhoods, evidence inspection, and implementer/verifier views. The server binds only
to the local machine by default and uses Python's standard library; it does not upload graph data.

Do not expose the verifier view to implementation agents. It includes private holdout metadata.
The current local audience selector demonstrates the policy boundary; it is not authentication.

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
2. Add private holdout fixtures and mutation tests under the verifier-only boundary.
3. Expand verified rule mappings to the posting and statement-generation workloads.
4. Put separate implementation and inspection agents behind authenticated, signed graph context
   packages rather than the v0.4 local audience selector.
5. Retain graph deltas, decisions, failed attempts, and verification outcomes as compounding memory.
6. Route structured differences through an automated repair loop.
7. Issue a LIGHTYEAR acceptance receipt only after structural, behavioral, security, and private
   verification policies pass.

The pinned workload specification is in `spec/carddemo-intcalc.json`.
