# Senior engineer architecture and extension guide

## Release composition

The pilot layer is intentionally an assembler, not a second modernization engine:

```text
approved source -> content-addressed intake
existing receipts -> raw-byte evidence registry
capability gates + appliance -> live-evidence preflight
all three -> JSON/Markdown pilot dossier
```

`pilot/pilot.profile.json` fixes intake bounds, supported file classes, required reference classes,
and the exact evidence registry. `pilot/compatibility.policy.json` freezes the v1 contract family
for the 0.29.x pilot line. The generated dossier binds both policies plus every evidence file by
raw SHA-256.

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

The 0.29.x line accepts only the v1 intake, preflight, and dossier schemas. A foreign major version,
stale content identity, unknown required field, or attempted promotion of live/production posture
must fail. A future v2 migration must preserve prior content identities as evidence and rerun all
validation; it must not rewrite historical receipts in place.

## Authority boundary

The pilot can declare offline pilot readiness. It cannot authorize a mainframe run, qualify a model,
sign customer equivalence, approve cutover, or promote production. Those authorities remain owned
by their respective evidence and policy planes.
