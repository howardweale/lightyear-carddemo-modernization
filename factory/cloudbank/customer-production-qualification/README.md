# CloudBank customer production-readiness qualification

Milestone 57 deepens the single Customer-service workcell proven by MS #56. It repeats one shared
five-test contract against native Oracle and PostgreSQL, exercises HTTP authentication and
authorization, checks error responses, observes two-connection `READ COMMITTED` behavior and
rollback/commit visibility, and verifies declared data boundaries.

The PostgreSQL lane also packages the Spring Boot application and inspects the executable JAR. The
gate requires one PostgreSQL driver and no Oracle runtime library. A deterministic 10,000-row
synthetic aggregate profile and an offline simulated checkpoint/cutover/rollback rehearsal provide
production-shaped planning evidence without reading or persisting production data.

## Static verification

```bash
./cloudbank-production-qualification.sh verify
./cloudbank-production-qualification.sh verify-source ../cloudbank-upstream
```

## Native qualification run

Keep `LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY` set to the value used to sign the passing MS #56
receipt, then run:

```bash
./cloudbank-production-qualification.sh run \
  ../cloudbank-upstream \
  work/cloudbank-dark-factory/cloudbank-customer-dark-factory.receipt.json \
  work/cloudbank-production-qualification \
  operator-id

./cloudbank-production-qualification.sh verify-receipt \
  work/cloudbank-production-qualification/cloudbank-customer-production-qualification.receipt.json
```

Replace `operator-id` with a stable identifier for the person or automation that performed the run,
for example `howard-local` or `github-actions`. The runner emits progress messages while the Oracle
container starts and signs only hashes, counts, booleans, and bounded metadata.

If a final acceptance gate fails, the runner writes
`cloudbank-customer-production-qualification.failure.json` in the selected output directory. That
report identifies the failed lane, test names and exception types, Maven phase, marker counts, and
packaged database libraries without persisting raw Maven output or credentials.

## Exact boundary

A passing receipt qualifies the Customer workcell more deeply. It does not exercise native CDC,
build or scan an OCI image, inspect production data, qualify another CloudBank service, authorize a
cutover, establish whole-CloudBank equivalence, complete a migration, or declare production
readiness. Those claims require later portfolio and authorized deployment milestones.
