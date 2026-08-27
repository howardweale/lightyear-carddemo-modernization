# Trusted extensions and mainframe access

## MS #24 PL/I discovery coverage and conformance lab

MS #24 upgrades `lightyear.pli` to v1.2 and places a tokenized, statement-aware front end in front
of graph extraction. The published support matrix is exercised by 27 synthetic cases, including
two include members, five expected blockers, and seven mutation-oriented cases. Golden results and
the coverage receipt list recognized constructs, references, diagnostics, and exact source
locations.

```bash
./pli-conformance.sh verify
```

The capability projection reports 27 corpus cases and 22 supported construct categories. These
are synthetic static-discovery breadth metrics. They do not establish customer-estate coverage,
IBM Enterprise PL/I compiler compatibility, runtime behavior, or mainframe equivalence. See
[`pli/conformance/README.md`](pli/conformance/README.md) for the precise supported subset and gaps.

## MS #22 mixed PL/I development proof

MS #22 advances the bounded `ACCTPL1` fixture beyond parsing. Its behavior contract covers the
PL/I fixed-width authorization record, `CARDDEMO.AUTHFRDS` lookup, explicit decimal truncation,
ordered `AUTHIN`/`AUTHOUT` effects, and the `OPTIONS(COBOL)` invocation of `CBACT04C`. The source-
faithful oracle and independent candidate must match seven normal and negative cases, while nine
mutations attack the Db2 overwrite, risk formula, COBOL target and parameter boundary, and error-
path side effects.

```bash
./extension-foundation.sh verify
./pli-modernization.sh verify
```

The committed development receipt binds the graph, PL/I fragment, contract, fixtures, comparison,
PL/I/include sources, Python candidate, and Java candidate/tests. It can promote gates 3–5 only.
No local or simulated artifact can satisfy authorized z/OS execution or signed live equivalence.
The proof is complete for this bounded workload, not for arbitrary PL/I programs or the full
`CBACT04C` interest-calculation estate.

MS #21 turns the MS #20 extension boundary into a complete access-readiness campaign. It runs three
read-only collectors—z/OSMF Jobs, Db2 for z/OS catalog, and CICS CMCI—through one credential-free
profile. Every capture is signed separately in live mode, bound to exact graph entities, and
aggregated only when the required adapter set is complete and internally consistent.

```bash
./mainframe-access.sh verify
./mainframe-access.sh simulate
```

The simulated campaign uses the same bounded parsers as live collection but remains classified as
`simulated`. It cannot satisfy a customer-mainframe evidence gate. See
[adapters/README.md](adapters/README.md) for the endpoint contracts, environment variables, and live
operator procedure.

## MS #20 foundation

MS #20 adds a versioned boundary for new evidence adapters and language packs without changing the
verified MS #19 graph in place. Adapter captures declare whether their evidence is `live`,
`recorded`, `simulated`, or `inferred`; bind every claim to one exact graph identity; retain only
bounded artifact metadata; and fail closed on missing entities, drift, tampering, or credential-
shaped fields.

The record/replay path never promotes trust. Replaying a live capture produces `recorded` evidence,
while simulated and inferred inputs retain their original classification.

The first language pack parses a bounded PL/I reference workload into a content-addressed graph
fragment. The fragment contributes PL/I programs, procedures, includes, file access, embedded Db2
SQL, and mixed-language calls. Cross-fragment references are resolved against the exact canonical
graph hash. A base-graph change invalidates the fragment until it is deliberately rebuilt.

```bash
./extension-foundation.sh verify
```

```powershell
.\extension-foundation.ps1 verify
```

The bundled PL/I and adapter captures are development fixtures. They do not claim customer source,
live z/OS observation, successful PL/I compilation, or production readiness. A passing MS #21 live
campaign would upgrade only the bounded observations it actually collected; it would not upgrade
the PL/I proof or the factory as a whole.
