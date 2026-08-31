# CBPAUP0C IMS logical proof cell

This package preserves the bounded IMS BMP proof and binds it into the broader v0.40 IMS
qualification plane. The original cell follows
`CBPAUP0J -> CBPAUP0C -> PSBPAUTB/PAUTBPCB -> DBPAUTP0 -> PAUTSUM0/PAUTDTL1`; the qualification
adds graph-bound DBD/PSB/PCB inventory, a deterministic 40-case corpus, a five-class compatibility
ledger, and eleven independent gates.

The committed capture is a deterministic logical model. It does not schedule the PSB or execute
against IMS and therefore cannot establish mainframe equivalence.

## Current status

- native DBD, PSB, PCB, segment, program, and JCL graph: passed;
- eight curated behavior rules: passed;
- source-faithful in-memory BMP candidate: passed;
- private mutation and negative gate: passed;
- local logical comparison: passed;
- graph-bound 40-case semantic conformance: passed;
- 28-entry compatibility ledger: passed with unresolved and excluded boundaries;
- IMS qualification mechanism: development-ready;
- authorized z/OS BMP execution: blocked;
- independent live comparison: mechanism ready, evidence pending;
- signed equivalence receipt: blocked.

The candidate deliberately preserves the source's duplicated approved-count root deletion test.
That behavior is highlighted as a source quirk and must be explicitly accepted or changed under a
separate business decision after live characterization.

## Commands

```bash
./ims-readiness.sh verify
PYTHONPATH=src python3 -m lightyear_readiness.ims_qualification verify
./ims-readiness.sh template work/cbpaup0c-live
```

On Windows PowerShell:

```powershell
.\ims-readiness.ps1 verify
.\ims-readiness.ps1 template -OutputDir work\cbpaup0c-live
```

The mainframe evidence custodian signs a completed capture with `LIGHTYEAR_IMS_ATTESTATION_KEY`.
A separate equivalence authority signs the final receipt with
`LIGHTYEAR_IMS_EQUIVALENCE_SIGNING_KEY`.

See [OPERATOR-RUNBOOK.md](OPERATOR-RUNBOOK.md) before requesting a live run.

The synthetic corpus does not authorize additional native activity. Fast Path, MSDB, IMS TM,
shared queues, DBRC, logging, restart/recovery equivalence, and production readiness remain outside
the qualified claim until separately approved native evidence is captured.
