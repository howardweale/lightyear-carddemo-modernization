# LIGHTYEAR relationship ontology

`relationships.json` makes graph edges governed, portable claims. Each relationship defines its
plain-language purpose, direction, category, evidence policy, and exact allowed source/target node
kind pairs.

The graph snapshot carries the ontology content hash. Validation fails if an extractor invents an
undefined relationship, reverses an allowed direction, connects incompatible node kinds, or the
committed ontology drifts from the graph identity.

This catalog is part of LIGHTYEAR's canonical intellectual property. Neo4j and other databases may
project the relation labels, but the meaning, evidence expectations, validation rules, and evolution
history remain owned by the factory.
