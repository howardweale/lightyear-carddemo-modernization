# CloudBank whole-application transaction wave

MS #58 accounts for all eight root deployable CloudBank services and prepares the first connected
transaction wave: the already-qualified `customer` service plus `account` and `transfer`.

## Verify the committed contracts

```bash
./cloudbank-transaction-wave.sh verify
./cloudbank-transaction-wave.sh verify-source /path/to/cloudbank-upstream
```

## Admit the wave

Use the same `LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY` that signed and verified the MS #57
qualification receipt:

```bash
./cloudbank-transaction-wave.sh admit \
  /path/to/cloudbank-upstream \
  work/cloudbank-production-qualification/cloudbank-customer-production-qualification.receipt.json \
  work/cloudbank-transaction-wave/cloudbank-transaction-wave.receipt.json \
  operator-id

./cloudbank-transaction-wave.sh verify-receipt \
  work/cloudbank-transaction-wave/cloudbank-transaction-wave.receipt.json
```

Replace `operator-id` with a stable audit label for the person or automation performing the run,
for example `howard-macbook` or `github-actions`. It is not a password or secret.

Admission verifies the exact source checkout, all committed MS #58 artifacts, and the MS #57
signature. It does not modify CloudBank source or generate target code.

## Evidence boundary

The complete portfolio is inventoried and planned, but only Customer carries the prior bounded
native qualification. The Account mapping and recovery rehearsal are deterministic design evidence.
Account/Transfer native execution, Oracle AQ/JMS replacement, MicroTx LRA replacement, the remaining
service workcells, production data, whole-application equivalence, migration completion, and
production readiness remain false.
