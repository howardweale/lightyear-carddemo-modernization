# Authorized COBDATFT z/OS evidence runbook

## Purpose

Produce a minimal, auditable observation of the original `COBDATFT` load module called by
`CBACT01C`. This run closes the execution-evidence gap only; the independent comparison and
equivalence authority remain separate.

This procedure is not authorization to assemble or execute `MVSWAIT`, invoke `STIMER`, test
privileged or authorized services, or generalize the result to other HLASM programs. Those
qualification gates remain blocked and require separately approved evidence.

## Required approvals and isolation

1. Use an approved non-production LPAR and synthetic CardDemo data.
2. Record the change or test ticket, system ID, LPAR, JES job ID, step, operator, and UTC time.
3. Pin the exact AWS CardDemo source commit and assembler/macro members.
4. Do not include credentials, customer records, terminal secrets, or unredacted dumps.
5. Preserve the assembly listing, binder map, load-module digest, and COBOL caller output.

## Build and execute

1. Assemble `app/asm/COBDATFT.asm` with `app/maclib/COCDATFT.mac` available in SYSLIB.
2. Confirm zero severe assembler diagnostics and retain the complete listing.
3. Bind the object into an isolated load library; retain the binder map and return code.
4. Record the SHA-256 of the resulting load module or an authorized export of its bytes.
5. Run `CBACT01C` with the synthetic input represented in `zos-capture.template.json`.
6. Capture the exact twenty-byte input and output date areas, thirty-eight-byte error area, and
   caller/job return code. Preserve spaces and encoding metadata.
7. Repeat negative direction/type cases if permitted; do not alter the production module.

## Complete and attest the capture

Replace every `REPLACE` value and every zero digest in the generated template. Then set the
operator attestation to authorized and sign it outside the repository:

```bash
export LIGHTYEAR_ASM_ATTESTATION_KEY="<external-secret>"
PYTHONPATH=src python3 -m lightyear_readiness.asm attest-capture \
  --capture /secure/cobdatft-capture.json \
  --output /secure/cobdatft-capture.signed.json \
  --key-id customer-evidence-custodian
```

The independent verifier imports the signed capture and runs:

```bash
export LIGHTYEAR_ASM_ATTESTATION_KEY="<verification-copy>"
export LIGHTYEAR_ASM_EQUIVALENCE_SIGNING_KEY="<separate-external-secret>"
./asm-readiness.sh compare work/cobdatft-live /secure/cobdatft-capture.signed.json
```

Any validation error, output difference, missing artifact, unsigned attestation, or identity gap
blocks equivalence. The factory and UI cannot waive the block.
