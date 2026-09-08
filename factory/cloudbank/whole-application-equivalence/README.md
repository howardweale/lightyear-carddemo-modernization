# CloudBank whole-application dual-lane equivalence

MS #66 closes the bounded whole-application comparison that earlier milestones deliberately left
open. It admits the signed MS #61 Oracle/PostgreSQL core comparison and the signed MS #64 complete
target, then requires separately signed observations from two isolated runtime lanes.

The source lane validates the exact pinned checkout, leaves that checkout unchanged, and applies the
reviewed, content-addressed `oracle-hardening/source-hardening.patch` only in a fresh build workspace.
That materialization is explicitly identified as `pinned-source-plus-governed-hardening`; it is not
the exact unchanged upstream application. The patch makes synthetic seed replay restart-safe, adds
Oracle AQ message identity and an observation ledger, makes Account journal commands idempotent,
and preserves insufficient-funds rejection without a zero-value journal. Oracle Free, Oracle AQ/JMS,
and MicroTx LRA remain native in this lane.

The target lane runs the exact MS #64 eight-service materialization with native PostgreSQL, its
durable work queue, and atomic transaction replacement. Both lanes must start every deployable, run
the same 18 normalized business, negative, failure, concurrency, restart, and recovery scenarios,
restart the complete stack, and finish ready.

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

For the supported live GKE execution, use the asynchronous launcher in
`factory/cloudbank/platform-qualification/gke/submit-ms66-dual-lane.sh`. It builds eight immutable
governed source images, mirrors explicitly tagged Oracle and MicroTx runtime images into the private
Artifact Registry, signs a source image lock, creates a run-labelled isolated namespace, executes
the Oracle lane, proves cleanup, then runs the same harness against the deployed PostgreSQL target.
It writes signed recovery intent before each isolated mutation. If the build is forcibly terminated,
use `submit-ms66-recovery.sh` with the downloaded signed recovery state; cleanup refuses a namespace
or model policy whose UID or ownership labels drift. See `LIVE-RUNBOOK.md` for exact inputs,
monitoring, receipt verification, and PostgreSQL target recovery.

The isolated lane consumes the same four-client authorization contract as the deployed target:
DEFAULT grants `cloudbank.read`, `cloudbank.write`, and `cloudbank.transfer`; SERVICE grants
`cloudbank.internal` and `cloudbank.test`; CREDITSCORE and CHATBOT each grant only
`cloudbank.read`. The runner validates these exact scope sets and the corresponding client
credentials before starting services. It does not require legacy TEST-client secret fields, expand
grants, rotate credentials, or persist secret values.

The committed readiness receipt does not say the native lanes ran. A passing execution receipt
establishes bounded, normalized whole-application equivalence for the 18 declared scenarios. It does
not claim unchanged upstream identity, identical internals, a real credit decision, model-answer
quality, production data, production deployment, migration completion, or production readiness.
MS #67 owns platform qualification; MS #68 owns customer production-readiness certification.
