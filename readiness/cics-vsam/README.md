# CICS/VSAM readiness gate

This vertical proof covers `CAVW` → `COACTVWC` → `COACTVW/CACTVWA` and the
ordered keyed reads of `CXACAIX`, `ACCTDAT`, and `CUSTDAT`.

## Eight gates

1. Native CSD, BMS, EXEC CICS, and IDCAMS assets become typed graph entities.
2. Transactions, programs, maps, fields, CICS files, paths, alternate indexes,
   clusters, and components are linked with line-addressable evidence.
3. Eight account-view behaviors are curated as graph-grounded rules.
4. A bounded read-only Python candidate provides the modernization seam.
5. A private gate and mutation/negative tests reject wrong routing, layout,
   lookup order, NOTFND behavior, and writes.
6. `zos-capture.template.json` and the operator runbook define an authorized
   execution capture from a real CICS region and VSAM estate.
7. The differential comparator checks terminal output, keyed access order, and
   zero mutations independently of the candidate builder.
8. The receipt issuer can sign a matching live comparison, but remains
   `blocked` until a `zos_observed` baseline and external signing key exist.

Local success is development evidence, not z/OS equivalence.

```bash
./cics-vsam-readiness.sh verify
./cics-vsam-readiness.sh template work/cavw-live
export LIGHTYEAR_EQUIVALENCE_SIGNING_KEY="$(openssl rand -hex 32)"
export LIGHTYEAR_MAINFRAME_ATTESTATION_KEY="$(openssl rand -hex 32)"
python -m lightyear_readiness attest-capture \
  --capture work/cavw-live/zos-capture.filled.json \
  --output work/cavw-live/zos-capture.json
./cics-vsam-readiness.sh compare work/cavw-live work/cavw-live/zos-capture.json
```

The mainframe evidence custodian and release-equivalence signer should use different keys and,
in production, different identities. Never put either signing key, credentials, production account data, or unredacted
screen captures in the repository.
