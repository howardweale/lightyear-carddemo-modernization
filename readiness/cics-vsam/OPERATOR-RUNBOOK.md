# Authorized CAVW mainframe capture runbook

This runbook remains deliberately limited to the read-only `CAVW` differential proof. The broader
MS #39 corpus is synthetic; it does not authorize write, locking, RLS, queue, journal, recovery, or
other state-changing activity in a customer CICS region or VSAM estate.

## Before execution

1. Obtain the customer change/ticket approval and confirm the named LPAR, CICS
   region, test user, transaction, time window, and rollback owner.
2. Use synthetic test records only. Record the `CAVW` account identifier in the
   protected evidence system; do not commit it if it is customer data.
3. Hash the approved CSD, BMS, load module/source build, and relevant catalog
   definitions. Confirm `CAVW` resolves to `COACTVWC`.
4. Record before-run digests or approved record-level fingerprints for
   `CXACAIX`, `ACCTDAT`, and `CUSTDAT`.

## Execute and observe

1. Start the authorized terminal session and record system ID, LPAR, CICS
   region, operator, UTC time, and ticket.
2. Enter `CAVW`, submit the synthetic eleven-digit account number, and capture
   the redacted input/output screen or 3270 data stream.
3. Capture the CICS task ID and an approved trace/log showing program
   `COACTVWC` and ordered READs of `CXACAIX`, `ACCTDAT`, then `CUSTDAT`.
4. Exercise at least one valid account and one NOTFND account. Do not run update
   transactions as part of this read-only proof.
5. Record response/abend codes and hash each retained artifact before transfer.

## After execution

1. Record after-run dataset digests and prove that the three resources did not
   change. Escalate any mutation immediately; do not issue a receipt.
2. Populate `zos-capture.template.json`, set `operator_attestation.authorized`
   to true only after the evidence custodian verifies ticket and scope, then run
   `attest-capture` with the separately controlled mainframe-attestation key.
3. Transfer only redacted artifacts through the customer's approved channel.
4. Run the comparator and receipt issuer. A difference, missing artifact,
   unsigned receipt, or non-`zos_observed` baseline must remain blocked.
