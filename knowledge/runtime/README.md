# Runtime evidence plane

The runtime evidence plane is an append-only trust layer beside the deterministic source graph.
It records what an adapter observed, binds every observation to an existing graph node or edge,
chains events by SHA-256, and materializes a disposable projection for the explorer.

## Evidence classes

| Class | Meaning | Maximum confidence |
|---|---|---:|
| `simulated` | Recorded fixture used to test factory mechanics | 0.45 |
| `local_observed` | Direct execution of the source-derived local oracle or modern candidate | 0.70 |
| `zos_observed` | Evidence captured from an authorized z/OS adapter | 0.95 |

Simulated or local evidence can pass the development-readiness policy. It can never satisfy the
mainframe-equivalence policy. This prevents a replay fixture from being promoted into a production
equivalence claim.

## Build and inspect

```bash
./runtime-evidence.sh build
PYTHONPATH=src python3 -m lightyear_runtime inspect
PYTHONPATH=src python3 -m lightyear_runtime inspect --edge edge:0594254ade360b961aef
```

The build executes the deterministic local oracle and replays the recorded z/OS-shaped fixture.
The resulting `runtime.snapshot.json.gz` is content addressed and targets one exact static graph
identity. The explorer exposes the run receipts and overlays node and edge state as
`static_only`, `runtime_observed`, or `runtime_contradicted`.

## Future z/OS adapter

The adapter must emit the same capture bundle contract as the local and fixture adapters. The
first connection should collect JES job and step results, spool messages, dataset allocations,
program identity, return codes, timestamps, and artifact hashes. Credentials remain outside
events and receipts. Raw production records must be minimized or tokenized before ingestion.

The current fixture proves ingestion and policy mechanics only. It is not mainframe evidence.
