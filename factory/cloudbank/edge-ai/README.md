# CloudBank Credit Decision and AI boundary

MS #64 completes the remaining-service wave without turning a demo random number or an unevaluated
model response into a production claim. The generated target carries the MS #57 PostgreSQL Customer
service and the MS #63 five-service target into one isolated eight-service package. It explicitly
records `azn-server`, `checks`, `testrunner`, `creditscore`, and `chatbot` as migrated, regenerates
each target workcell, and executes a dedicated Java test class for every one in the MS #64 lane.

Credit Score requires an issuer-, audience-, lifetime-, signature-, and scope-valid JWT. It replaces
the random demo response with a stable, subject-and-date-bound HMAC result labelled `synthetic-v1`.
The runtime pepper is never persisted. This proves the application boundary, not a real credit-bureau
decision or regulated scoring model.

Chatbot uses a distinct audience and rejects blank, oversized, and recognizable instruction-override
inputs before invoking the model. It filters unsafe and oversized outputs, rate-limits by authenticated
subject, returns safe failures without upstream details, and permits model egress only to an allowlisted
HTTPS host or an explicitly allowlisted loopback HTTP endpoint. Raw prompts, responses, tokens, and
secrets are not written to receipts.

Run deterministic verification:

```bash
./cloudbank-edge-ai.sh verify
./cloudbank-edge-ai.sh verify-source ../cloudbank-upstream
./cloudbank-edge-ai.sh materialize ../cloudbank-upstream work/cloudbank-ms64
```

An authorized signed run also requires the operator-held MS #63 and MS #57 receipts created with the
same evidence key and PostgreSQL image:

```bash
export LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY='operator-held-value'
./cloudbank-edge-ai.sh run ../cloudbank-upstream /secure/ms63-receipt.json \
  /secure/ms57-receipt.json work/cloudbank-ms64-run operator-name
```

A passing receipt qualifies all five remaining target workcells and the eight-service target package.
It does not call a credit bureau or external model, qualify model-answer quality, establish
whole-application Oracle/PostgreSQL equivalence, complete a migration, authorize promotion, or prove
production readiness.
