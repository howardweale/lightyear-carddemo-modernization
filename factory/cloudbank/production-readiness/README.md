# CloudBank production-readiness rehearsal

MS #65 turns the MS #64 eight-service target into a site-parameterized, immutable-image Kubernetes
deployment bundle and admits only a signed, non-production cutover/rollback rehearsal.

The committed readiness receipt is intentionally negative evidence: the controller and contracts
are ready, but no operator cluster, image lock, secret store, backup, traffic switch, or rollback
observation is committed. A passing execution receipt can establish only that the production-like
rehearsal ran against its bound non-production cluster and synthetic data.

## Required operator inputs

- A passing signed MS #64 execution receipt produced with the same evidence key.
- An image lock containing one immutable registry digest for each of the eight services.
- A non-production environment profile containing only cluster identity, namespace, bounded CIDRs,
  and external secret object names.
- A signed observation containing all 24 scenario results, eight rollout states, backup/restore
  hashes, the exact cutover state sequence, and the bounded SLO window.

## Commands

```bash
./cloudbank-production-readiness.sh verify
./cloudbank-production-readiness.sh verify-source /path/to/cloudbank-upstream
./cloudbank-production-readiness.sh materialize /path/to/cloudbank-upstream work/cloudbank-ms65
./cloudbank-production-readiness.sh render MS64_RECEIPT IMAGE_LOCK ENVIRONMENT OUTPUT_ROOT
./cloudbank-production-readiness.sh run SOURCE_ROOT MS64_RECEIPT IMAGE_LOCK ENVIRONMENT OBSERVATION OUTPUT_ROOT SIGNER
./cloudbank-production-readiness.sh verify-receipt RECEIPT
```

No secret values, production data, raw logs, prompts, responses, or database backup bodies are
admitted to repository evidence. Production deployment, production authorization, native CDC,
whole-application equivalence, migration completion, and production readiness remain false.

The shared network policy allows only internal, selected-ingress, DNS, and PostgreSQL traffic. A
separate policy grants the model endpoint path to Chatbot alone.
