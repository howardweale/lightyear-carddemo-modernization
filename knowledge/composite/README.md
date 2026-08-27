# Read-only composite estate

The v0.23 composite estate overlays separately validated extension fragments on the canonical graph
for search, tracing, source inspection, and visualization. It does not merge extensions into
`knowledge/graph.snapshot.json.gz` and cannot promote runtime or production claims.

## Identities

- `estate.snapshot.json.gz` has its own composite content identity.
- `estate.receipt.json` binds the canonical graph, extension fragments, capability projection,
  statistics, and explicit claim boundary.
- `source.pack.json.gz` and `source.receipt.json` add extension source excerpts to the canonical
  source evidence used by the Explorer.
- Runtime, audit, portfolio, factory, and adapter receipts continue to bind the canonical graph.

## Commands

```bash
./composite-estate.sh build ../carddemo-upstream
./composite-estate.sh verify ../carddemo-upstream
./lightyear.sh demo
./lightyear.sh explorer
```

PowerShell equivalents are provided. Validation rejects a stale base graph, stale capability
projection, fragment drift, unresolved cross-estate endpoint, node/edge shadowing, missing source
capsule, or any attempt to set `mainframe_equivalent` or `production_ready` to true.
