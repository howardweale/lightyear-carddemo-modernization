# Authorized IMS BMP evidence runbook

## Objective

Run `CBPAUP0C` with `PSBPAUTB` against an isolated, synthetic `DBPAUTP0` dataset and return enough
evidence to independently compare segment mutations, DL/I operation order, counters, checkpoints,
and return status with the FactoryDark logical candidate.

## Safety prerequisites

1. Obtain written customer authorization naming the test LPAR, IMS region, database, program, PSB,
   operator, time window, and evidence-retention boundary.
2. Use a disposable test database populated only with the synthetic fixture described by the
   generated capture template. Never point the proof JCL at production authorization data.
3. Confirm image copies or unloads can restore the database and that the job is excluded from the
   production scheduler.
4. Bind the exact `CBPAUP0C` load module, `PSBPAUTB`, `DBPAUTP0`, and JCL hashes into the capture.
5. Assign different people or control identities as evidence custodian and equivalence signer.

## Capture procedure

1. Generate `zos-capture.template.json` with `ims-readiness`.
2. Record synthetic before images for `PAUTSUM0` and `PAUTDTL1` and hash their canonical exports.
3. Execute the job in BMP mode with SYSIN `05,00001,00001,Y` or the specifically approved values.
4. Retain JES output, load-module digest, PSB/DBD digests, IMS log or trace, checkpoint evidence,
   and normalized after images.
5. Redact infrastructure identifiers only according to the agreed evidence policy; do not alter
   behavioral fields used by the comparator.
6. Complete `mainframe_identity` and set `operator_attestation.authorized` to true with its ticket.
7. Sign the capture using `LIGHTYEAR_IMS_ATTESTATION_KEY`; transmit the key separately from the
   evidence package.

## FactoryDark comparison

```bash
export LIGHTYEAR_IMS_ATTESTATION_KEY='provided-out-of-band'
export LIGHTYEAR_IMS_EQUIVALENCE_SIGNING_KEY='independent-verifier-key'
./ims-readiness.sh compare work/cbpaup0c-live work/cbpaup0c-live/attested-zos-capture.json
```

Any mismatched program identity, missing artifact, invalid signature, data difference, absent live
baseline, or missing independent signing key keeps the equivalence receipt blocked.
