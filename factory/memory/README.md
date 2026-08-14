# Verified semantic memory

This directory defines the controller-owned memory policy and canonical demonstration snapshot for
v0.14. Memory is a read-optimized projection of independently verified factory outcomes. It is not
an agent transcript, a substitute for source evidence, or a model-training corpus.

An experience can enter implementer memory only when:

1. the controller has a terminal factory receipt and deterministic gate result;
2. its evidence class is admitted by `policy.json`;
3. graph and source-evidence identities are recorded;
4. verifier-private artifacts are omitted; and
5. the run is not a sealed holdout.

Passed repairs become positive memories. Correct unchanged runs become `accept_unchanged`
memories. Failed runs can become negative memories, but exact failed replacement text is removed so
an anti-pattern cannot be replayed as an executable edit. Controller failures are quarantined.

Retrieval is graph-first, then path- and vocabulary-aware. A graph or evidence-pack identity change
makes the experience stale immediately. Retrieved cards remain advisory: source evidence and fresh
acceptance gates always have higher authority.

```bash
./semantic-memory.sh validate
./semantic-memory.sh summary
./semantic-memory.sh query factory/work-orders/intcalc-repair.example.json
./semantic-memory.sh ingest work/factory-runs/<run-id>
```

The tracked `store/` is a local demonstration derived from synthetic CardDemo gates. It proves
memory mechanics and privacy boundaries, not z/OS equivalence or blind model generalization.
