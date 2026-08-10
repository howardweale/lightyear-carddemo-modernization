# Optional Neo4j projection

Neo4j is a visualization and query projection for the LIGHTYEAR graph. It is deliberately not the
authoritative store. The deterministic `knowledge/graph.snapshot.json.gz`, ontology, mappings,
evidence policy, and acceptance rules remain the product-controlled source of truth.

This boundary lets LIGHTYEAR benefit from Neo4j Browser, Bloom, Cypher, and operational graph
indexing without coupling the accumulated modernization knowledge to one database vendor.

## Export

From the repository root:

```bash
PYTHONPATH=src python3 -m lightyear_knowledge_graph export-neo4j \
  --output-dir work/neo4j-export
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m lightyear_knowledge_graph export-neo4j `
  --output-dir work\neo4j-export
```

The export is deterministic and contains:

| File | Purpose |
|---|---|
| `nodes.csv` | Every graph entity, stable ID, kind, properties, evidence, and labels |
| `relationships.csv` | Every directed relationship, its kind, properties, and evidence |
| `constraints.cypher` | Stable-identity uniqueness constraint for the imported database |
| `export-receipt.json` | Source graph hash and exported row counts |

`propertiesJson` and `evidenceJson` preserve the canonical nested values losslessly. They remain
JSON strings in Neo4j because bulk CSV formats do not represent arbitrary nested property values.
An application projection can materialize selected values as first-class Neo4j properties later.

## Import choices

For a local visual experiment, create a disposable database in Neo4j Desktop and import
`nodes.csv` and `relationships.csv` with Neo4j Data Importer. Map `nodeId:ID` as the node ID,
`:START_ID` and `:END_ID` as relationship endpoints, and retain the generated labels and types.
Run `constraints.cypher` after import.

For repeatable environments, use the `neo4j-admin database import full` command supplied by the
installed Neo4j version. Command-line switches differ between Neo4j releases, so use that
installation's help output and documentation, providing `nodes.csv` as the node input and
`relationships.csv` as the relationship input. Treat the database as disposable: regenerate it
from the canonical snapshot whenever the receipt hash changes.

## Useful Cypher

```cypher
// Find business rules and their directly connected implementation or verification assets.
MATCH (rule:BusinessRule)-[relationship]-(asset)
RETURN rule.name, type(relationship), asset.name, asset.kind
ORDER BY rule.name, type(relationship), asset.name;

// Explore an impact neighborhood around the account copybook.
MATCH path=(copybook:Copybook {nodeId: 'legacy:copybook:CVACT01Y'})-[*1..2]-(affected)
RETURN path
LIMIT 200;

// Trace the INTCALC workload without attempting to render the full estate.
MATCH path=(workload:ModernizationWorkload {nodeId: 'workload:carddemo-intcalc'})-[*1..3]-(entity)
RETURN path
LIMIT 250;
```

## Trust and security boundary

The full Neo4j projection includes verifier-private nodes. Do not expose it to implementation
agents or publish it as a shared development service. The built-in Graph Explorer defaults to an
implementer-safe view and applies visibility filtering in search, node lookup, neighborhoods, and
traces. A production graph service should enforce the same rule with authenticated principals,
policy evaluation, audit events, and signed context receipts.
