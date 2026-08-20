# COBDATFT HLASM readiness cell

This package advances the bounded COBDATFT routine through readiness gates 1–5 and supplies the
mechanics for gates 6–8. The committed local capture proves the candidate and comparison machinery;
it does not execute HLASM and cannot satisfy mainframe equivalence.

## Current status

- typed HLASM program, instruction, branch, symbol, macro, DSECT, and field graph: passed;
- COBOL caller and shared parameter-layout connections: passed;
- five curated behavior rules: passed;
- bounded Python candidate and private mutation gate: passed;
- local differential comparison: passed;
- authorized z/OS assembly, bind, and caller execution: blocked;
- independent live comparison: mechanism ready, evidence pending;
- signed equivalence receipt: blocked.

## Commands

```bash
./asm-readiness.sh verify
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

See [OPERATOR-RUNBOOK.md](OPERATOR-RUNBOOK.md) before requesting execution.
