# Senior engineer architecture and extension guide

## Release composition

The pilot layer is a bounded customer analysis workcell, not a second modernization engine:

```text
approved source -> content-addressed intake
intake + source -> customer-specific typed graph + analysis receipt
existing receipts -> raw-byte evidence registry
capability gates + appliance -> live-evidence preflight
all four -> JSON/Markdown pilot dossier v2
```

`pilot/pilot.profile.json` fixes intake and graph bounds, supported file classes, the relationship
ontology, and the exact evidence registry. `pilot/compatibility.policy.json` preserves v1 intake,
preflight, and analysis contracts while introducing the customer-bound v2 dossier for the 0.30.x
pilot line. The generated dossier binds the dynamic customer analysis plus every release evidence
file by raw SHA-256.

The bounded ontology includes program calls and scheduling, Db2 SQL/data lineage, HLASM
instructions and branch targets, IMS DBD/segment/field plus PSB/PCB sensitivity relationships, and
VSAM cluster/component/alternate-index/path topology. These are static relationships only; macro
expansion, IMS runtime access, VSAM catalog state, and native execution remain outside this claim.

## Adding a supported source fixture

1. Add a UTF-8 fixture with no credential or customer data.
2. Add or reuse a file class in `pilot.profile.json`.
3. Recompute the profile content identity.
4. Add parser/graph tests outside the pilot package when the fixture changes product semantics.
5. Rebuild the reference output and run `./source-only-pilot.sh verify`.
6. Run the complete repository verifier to catch downstream graph or receipt coupling.

Do not add a new extension merely to make intake accept a filename. Intake classification, semantic
parsing, modernization behavior, and runtime equivalence are separate contracts.

## Compatibility rules

The 0.30.x line accepts v1 intake, preflight, and customer-analysis receipts plus the v2 dossier.
The historical v1 dossier schema remains committed for independent verification. A foreign major
version, stale content identity, unknown required field, or attempted promotion of live/production
posture must fail; historical receipts must never be rewritten in place.

## Authority boundary

The pilot can declare offline pilot readiness. It cannot authorize a mainframe run, qualify a model,
sign customer equivalence, approve cutover, or promote production. Those authorities remain owned
by their respective evidence and policy planes.
