# MS94 prospective invoice-type contract extension

This extension adds only the approved rule that the original sales invoice retain
the invoice type configured by its completed order's document type. The prompt and
recorded public-contract tool expose the same shape declaration. No smoke execution
tool or wider private diagnostic is added. Support, observer and all 488 accepted
equipment-04 implementation files remain byte-identical in execution snapshots.

`tools.ms94_v5_gate` adds the relationship predicate after the unchanged complete
native gate. It compares configuration relationships, not fixture IDs. Both target
and completed invoice types must match. It refuses old declarations, preserves
execution/evidence/judge failures, and publishes no expected values to the builder.

The three reference variants alter only the original invoice construction in the
accepted operations reference:

1. `retained`: order constructor, retaining its resolved invoice type.
2. `equivalent`: explicit order-type relationship passed to the constructor.
3. `alternate`: deterministic selection of a different active ARI type.

Each runs on a fresh Oracle/PostgreSQL pair. All must pass the unchanged base gate;
the first two must pass the extension and the third must be rejected specifically
on both invoice-type fields in both lanes. Every native publication must replay,
and cleanup must succeed. Stop at the first unexpected outcome; no replacement.
Maximum three pairs/three hours, zero model calls. This qualifies the additive
acceptance boundary using inherited equipment-04 qualification; it is not a claim
that all 62 old controls were executed again. Human approval is for the prospective
rule; the records do not invent independent source review of the new variants.

After qualification, `tools.ms94_measure_v5` prepares a new declaration with three
excluded pilots and 20 fresh cohort trials. Limits: 115 total builder/analyst calls,
69 compilations, 26 hours; five calls and three compilations per trial. Public plan
publication precedes generation. Pilot and cohort outcomes/costs remain separate;
measurement is void on equipment/provenance failure. No Stage B 02 slots are reused.
