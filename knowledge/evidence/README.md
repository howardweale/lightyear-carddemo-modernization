# LIGHTYEAR source evidence capsules

`source.pack.json.gz` is a deterministic, self-contained read model for source inspection. It
contains only graph-referenced excerpts and bounded context—not arbitrary filesystem access.

Every capsule records the source repository ID, relative path, evidence line range, highlighted
context, parser method, confidence, full-file SHA-256, excerpt SHA-256, and the graph owners it
supports. The pack is bound to the canonical graph and relationship-ontology hashes and has its own
content address in `source.receipt.json`.

The explorer resolves an excerpt with `owner_type`, `owner_id`, and `evidence_index`. It never
accepts a path from the browser. The server first applies the implementer/verifier visibility
boundary to the owner, then returns the corresponding capsule without its cross-owner support list.

Build and validate:

```bash
./knowledge-graph.sh build ../carddemo-upstream
PYTHONPATH=src python3 -m lightyear_knowledge_graph validate-evidence
```

Production deployments should additionally authenticate users, authorize source repositories,
encrypt source packs at rest, record evidence-access events, apply retention policy, and issue
signed source-view receipts.
