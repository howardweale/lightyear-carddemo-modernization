# CICS/VSAM qualification gate

This qualification has two bound evidence layers:

- the existing `CAVW` → `COACTVWC` → `COACTVW/CACTVWA` proof, including the ordered read-only
  access to `CXACAIX`, `ACCTDAT`, and `CUSTDAT`; and
- a deterministic synthetic conformance plane spanning CICS file-control and bounded VSAM
  semantics without representing itself as a CICS or VSAM emulator.

## Eleven gates

1. The canonical graph binds 240 CICS commands, 25 transactions, 16 file resources, 15 VSAM
   clusters, three alternate indexes, three PATHs, and their typed relationships.
2. A content-addressed 38-case synthetic corpus supplies four positive, 30 targeted boundary, and
   four fail-closed mutation cases; it contains no customer or IBM source.
3. KSDS, ESDS, and RRDS organization, key, slot, record, and end-of-file behavior are covered as a
   bounded supported subset. LDS record access is excluded.
4. Unique and non-unique alternate-index lookup, duplicate collision, and PATH resolution have
   explicit semantic vectors.
5. READ, file status, RESP/RESP2, STARTBR, READNEXT, READPREV, and ENDBR behavior is deterministic
   and independently receipted.
6. WRITE, REWRITE, DELETE, duplicate record, missing record, and update-token behavior includes
   before/after mutation counts.
7. ENQ, DEQ, contention, syncpoint commit, and rollback are development vectors only; native lock,
   journal, unit-of-work, and recovery equivalence require authorized execution.
8. HANDLE CONDITION, BMS SEND/RECEIVE MAP, LINK, XCTL, RETURN, and secondary response behavior have
   bounded command-level contracts.
9. RLS, TSQ, TDQ, security, routing, journals, and exits remain explicitly unqualified or require
   policy decisions.
10. The private read-only account-view gate, deterministic comparison, and readiness receipt remain
    bound without weakening their existing evidence or attestation rules.
11. Native equivalence stays blocked until authorized CICS-region, VSAM-catalog, concurrency,
    journal, recovery, and independently signed differential evidence exists.

The 27-entry compatibility ledger assigns every material boundary exactly one of `exact`,
`normalized-equivalent`, `policy-decision-required`, `lossy`, or `unsupported`. Local success is
development evidence, not native CICS, VSAM, recovery, mainframe, or production equivalence.

```bash
./cics-vsam-readiness.sh verify
PYTHONPATH=src python3 -m lightyear_readiness.cics_vsam_qualification verify

# Prepare the separately governed, read-only CAVW live capture.
./cics-vsam-readiness.sh template work/cavw-live
export LIGHTYEAR_EQUIVALENCE_SIGNING_KEY="$(openssl rand -hex 32)"
export LIGHTYEAR_MAINFRAME_ATTESTATION_KEY="$(openssl rand -hex 32)"
python -m lightyear_readiness attest-capture \
  --capture work/cavw-live/zos-capture.filled.json \
  --output work/cavw-live/zos-capture.json
./cics-vsam-readiness.sh compare work/cavw-live work/cavw-live/zos-capture.json
```

The mainframe evidence custodian and release-equivalence signer should use different keys and, in
production, different identities. Never put either signing key, credentials, production data, or
unredacted screen captures in the repository.
