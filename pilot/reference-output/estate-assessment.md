# LIGHTYEAR customer estate assessment

**Assessment identity:** `51b11dd9ad8f9813a539c8ed16517aaaa8233cc1b8f64baec628df00ec48acd7`

## Result

LIGHTYEAR can partition an approved source estate into explainable connected slices and produce an evidence-first modernization planning backlog.

The plan is advisory. Business priority is not inferred, factory dispatch is disabled, and live validation remains blocked.

## Connected application slices

| Slice | Source files | Technologies | Nodes | Unresolved | Human decision |
|---|---:|---|---:|---:|---:|
| CICS-EXPORT connected application slice (`cluster:2b329d62ba6b900a`) | 1 | CICS, Configuration | 3 | 1 | required |
| ACCOUNTV connected application slice (`cluster:6a02c2ea6de7831e`) | 6 | COBOL, Db2, HLASM, JCL, PL/I | 33 | 1 | required |
| AUTHDB connected application slice (`cluster:c9b7311508da5951`) | 2 | IMS | 10 | 0 | required |
| AUTHCAT connected application slice (`cluster:f05aab4a016a5627`) | 1 | VSAM | 6 | 0 | required |

## Planning waves

### Wave 0: boundary-closure

Referenced source targets are supplied or explicitly accepted as external boundaries.

Affected slices: `cluster:2b329d62ba6b900a`, `cluster:6a02c2ea6de7831e`

### Wave 1: human-pilot-selection

After required boundary closure, a business owner selects a bounded slice and approves success criteria and data policy.

Affected slices: `cluster:2b329d62ba6b900a`, `cluster:6a02c2ea6de7831e`, `cluster:c9b7311508da5951`, `cluster:f05aab4a016a5627`

### Wave 2: development-proof

Selected slices have executable contracts, candidates, differential checks, and negative tests.

Affected slices: `cluster:2b329d62ba6b900a`, `cluster:6a02c2ea6de7831e`, `cluster:c9b7311508da5951`, `cluster:f05aab4a016a5627`

### Wave 3: authorized-native-validation — **blocked**

Customer-authorized original execution and independently signed comparison evidence exist.

Affected slices: `cluster:2b329d62ba6b900a`, `cluster:6a02c2ea6de7831e`, `cluster:c9b7311508da5951`, `cluster:f05aab4a016a5627`

## Evidence backlog

- Enterprise PL/I compile, Db2 bind, and authorized PL/I-to-COBOL execution
- Resolve cics-program COACTVWC referenced by config/cics-export.json:1
- Resolve program-call CBACT04C referenced by pli/ACCTPL1.pli:5
- assembler and binder listings, load-module digest, and authorized caller execution
- authorized BMP region, DBD/PSB, database, status, checkpoint, restart, and JES evidence
- authorized CICS transaction, installed-resource, and side-effect capture
- authorized catalog, package, source-row, log, cutover, and rollback observation
- authorized clusters, alternate indexes, record bytes, locking, and recovery observation
- authorized compiled original execution with input, output, and side-effect capture
- authorized installed configuration, consumer binding, change history, and deployment observation
- authorized job execution, JES output, dataset effects, conditions, and restart capture

## Limitations

- Connected components describe static coupling, not business criticality, transaction volume, runtime behavior, or ownership.
- The planner does not automatically approve or dispatch modernization work.
- Live original-system execution and signed equivalence remain blocked until separately authorized and observed.
