# HLASM qualification and COBDATFT readiness cell

This package binds the pinned `COBDATFT` and `MVSWAIT` assembler estate to a deterministic
qualification contract while retaining the authorized-live-evidence mechanics for the bounded
`COBDATFT` date routine. The committed corpus and local capture do not execute HLASM, invoke
`STIMER`, produce object code, run a binder, or satisfy mainframe equivalence.

## Current status

- typed HLASM program, instruction, branch, symbol, macro, DSECT, and field graph: passed;
- COBOL caller and shared parameter-layout connections: passed;
- 40-case synthetic conformance corpus with four diagnostic blocks: passed;
- 28-entry five-class compatibility ledger: passed;
- eleven independent qualification gates: passed or explicitly blocked;
- bounded Python candidate and private mutation gate: passed;
- local differential comparison: passed;
- authorized z/OS assembly, bind, and caller execution: blocked;
- independent live comparison: mechanism ready, evidence pending;
- signed equivalence receipt: blocked.

## Commands

```bash
./asm-readiness.sh verify
PYTHONPATH=src python3 -m lightyear_readiness.hlasm_qualification verify
./asm-readiness.sh template work/cobdatft-live
```

On Windows PowerShell:

```powershell
.\asm-readiness.ps1 verify
.\asm-readiness.ps1 template -OutputDir work\cobdatft-live
```

The mainframe evidence custodian signs a completed capture with
`LIGHTYEAR_ASM_ATTESTATION_KEY`. A separate equivalence authority signs the final receipt with
`LIGHTYEAR_ASM_EQUIVALENCE_SIGNING_KEY`. Do not use the same key or operator identity for both.

The corpus qualifies only the bounded behaviors named in `qualification.json`. It does not authorize
`MVSWAIT`, `STIMER`, privileged services, or any assembler program outside the pinned graph.

See [OPERATOR-RUNBOOK.md](OPERATOR-RUNBOOK.md) before requesting execution.
