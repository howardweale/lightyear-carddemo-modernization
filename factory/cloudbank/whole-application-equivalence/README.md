# CloudBank whole-application dual-lane equivalence

MS #66 closes the bounded whole-application comparison that earlier milestones deliberately left
open. It admits the signed MS #61 Oracle/PostgreSQL core comparison and the signed MS #64 complete
target, then requires separately signed observations from two isolated runtime lanes.

The source lane runs the exact pinned eight-service CloudBank application with native Oracle,
Transactional Event Queue, and MicroTx LRA. The target lane runs the exact MS #64 eight-service
materialization with native PostgreSQL, its durable work queue, and atomic transaction replacement.
Both lanes must start every deployable, run the same 18 normalized business, negative, failure,
concurrency, restart, and recovery scenarios, restart the complete stack, and finish ready.

```bash
./cloudbank-whole-application-equivalence.sh verify
./cloudbank-whole-application-equivalence.sh verify-source /path/to/cloudbank-upstream
./cloudbank-whole-application-equivalence.sh materialize /path/to/cloudbank-upstream work/ms66-target
```

The operator-owned lane harnesses emit signed observations conforming to
`whole-application-equivalence-lane-observation.schema.json`. Admit a pair only after both native
runs finish:

```bash
export LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY='operator-held-value'
./cloudbank-whole-application-equivalence.sh run \
  /path/to/cloudbank-upstream ms61.receipt.json ms64.receipt.json \
  oracle.observation.json postgresql.observation.json work/ms66-evidence operator@example
```

The committed readiness receipt does not say the native lanes ran. A passing execution receipt
establishes bounded, normalized whole-application equivalence for the 18 declared scenarios. It does
not claim identical internals, a real credit decision, model-answer quality, production data,
production deployment, migration completion, or production readiness. MS #67 owns platform
qualification; MS #68 owns customer production-readiness certification.
