# Offline AUTHFRDS migration rehearsal (v0.27)

MS #27 rehearses the operational data-migration lifecycle without pretending that deterministic
fixtures are a live Db2 change stream. The committed artifacts are:

- `plan.json`: exact model, fixture, mapping, receipt, journal, recovery, and cutover bindings;
- `cutover.approval.json`: simulated human approval signed by a published development-only key;
- `checkpoint.json`: the completed state after a forced interruption and one resume;
- `receipt.json`: the fail-closed reconciliation, cutover, fault-detection, and rollback result.

The journal contains five contiguous events: two inserts, two updates, and one delete. Every event
has a before/after identity and a previous-event hash. The controller rejects gaps, reordering,
stale before-images, foreign mappings, duplicate keys, checkpoint drift, or altered approval.

The bounded execution sequence is:

1. Load the two-row canonical AUTHFRDS fixture state.
2. Project it independently through the PostgreSQL and Oracle mappings.
3. Apply two changes and persist an interrupted checkpoint.
4. Resume, suppress duplicate replay, and apply the remaining three changes.
5. Normalize both target states and require exact source reconciliation.
6. Validate the exact development-only human approval and open simulated cutover.
7. Inject an uncommitted row into only the PostgreSQL-shaped target.
8. Detect divergence, restore both targets, and re-run reconciliation.

Run the deterministic rebuild and adversarial suite with:

```bash
./migration-rehearsal.sh verify /path/to/aws-carddemo
```

```powershell
.\migration-rehearsal.ps1 verify C:\path\to\aws-carddemo
```

The receipt's zero-event RPO and three-step RTO are fixture measurements, not production service
levels. Live Db2 log capture, customer data, actual target databases, operational network/security
faults, production-scale timing, real cutover authorization, and native z/OS equivalence remain
explicitly unproven.
