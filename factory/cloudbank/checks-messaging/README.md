# CloudBank Checks transactional messaging

MS #63 replaces the bounded Checks and Test Runner dependency on Oracle AQ/JMS with a durable
PostgreSQL work queue. The target preserves idempotent deposits and clearances, FIFO ordering inside
an aggregate, exclusive `FOR UPDATE SKIP LOCKED` claims, lease-based crash redelivery, bounded retry,
dead-letter quarantine, and governed replay.

The workcell starts from the MS #62 target, so Checks uses the qualified client-credentials provider
when it calls Account. The generated five-service package gate requires executable Authorization,
Account, Transfer, Checks, and Test Runner JARs with no Oracle or MicroTx runtime libraries.

The native runner captures Docker, Maven, and PostgreSQL command output as text before checking
image identity, package results, or queue observations. Raw command output stays in memory;
receipts retain Maven output hashes, and failure reports contain aggregate diagnostics.

Run deterministic verification:

```bash
./cloudbank-checks-messaging.sh verify
./cloudbank-checks-messaging.sh verify-source ../cloudbank-upstream
./cloudbank-checks-messaging.sh materialize ../cloudbank-upstream work/cloudbank-ms63
```

An authorized native run additionally requires the operator-held signed MS #62 receipt and the same
evidence key:

```bash
export LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY='operator-held-value'
./cloudbank-checks-messaging.sh run ../cloudbank-upstream /secure/ms62-receipt.json \
  work/cloudbank-ms63-run operator-name
```

The committed readiness receipt is not evidence that this native run occurred. A passing execution
receipt qualifies the PostgreSQL target queue mechanics and generated Checks workcell. It does not
claim a native Oracle AQ comparison, remaining-service completion, whole-application equivalence,
migration completion, production deployment, promotion, or production readiness.
