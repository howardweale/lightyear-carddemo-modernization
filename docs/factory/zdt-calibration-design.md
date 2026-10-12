# ZD&T calibration design — 2026-10-11, not a purchase or run

Proposed rung: **`ibm-zos-emulated`**, distinct from the provisional GnuCOBOL twin and from production IBM Z hardware. The scope is one preregistered execution of public INTCALC and POSTTRAN scenarios plus discriminating runtime probes. It must never be labelled a throughput benchmark, production validation, release approval or general z/OS equivalence.

## Host and licensing prerequisites

Plan a dedicated Intel-compatible Linux host on an IBM-supported Ubuntu or RHEL level selected from the version-specific Software Product Compatibility Report. Budget at least300GB for stock image files plus download, spool and work space; IBM specifies4.1GB of downloads and approximately300GB for stock images. Installation needs package-repository access and root/sudo. No host is installed or reconfigured by this proposal. [IBM prerequisites](https://www.ibm.com/docs/en/zdt/14.2.x?topic=edition-prerequisites).

For **Personal Edition**, obtain the separately ordered USB hardware licence device and its account-specific activation from IBM; do not assume a cloud VM can replace a USB-capable supported workstation. Enterprise has different licensing; legacy Enterprise/Sysplex USB licensing is end-of-market. No licence is purchased, activated, copied or read here. [IBM Personal Edition activation](https://www.ibm.com/docs/en/zdt/14.2.x?topic=edition-enabling-license-key), [IBM edition comparison](https://www.ibm.com/docs/en/zdt/14.2.x?topic=overview).

**Written IBM clarification is a prerequisite**, for both our internal engineering calibration and customer-facing conversion demonstrations. Ask IBM to identify the applicable edition, licence information document and permitted purpose, and confirm whether comparing converted output against preregistered scenarios is allowed. IBM describes development and demonstration uses but excludes production, robust development, production-module builds, preproduction testing, stress and performance testing. Therefore we do not infer that this calibration or a client demo is licensed merely because it is called non-production. A customer release/acceptance claim is outside this proposal. Record IBM's written response and exact licence terms before ordering or running. [IBM usage boundary](https://www.ibm.com/docs/en/zdt/14.2.x?topic=overview).

## Preregistered execution protocol

1. Freeze the public source/copybook commit, scenarios, EBCDIC code page037, compiler options, z/OS/Enterprise COBOL/LE levels, JCL/DD layouts, key definitions, input/output record lengths and expected branch outcomes. Hash the full manifest; no customer arrivals or learned answer generator enters it. Allocate disposable datasets with the pinned RECFM/LRECL and VSAM primary/alternate keys.
2. Use Zowe CLI to upload the frozen public members, submit reviewed compile/bind JCL, then the single run JCL; preserve job identifiers, JES completion codes, spool DDs, compiler/binder listings and output datasets as immutable evidence. Example command forms are `zowe jobs submit local-file reviewed.jcl` and `zowe files download ds HLQ.OUTPUT`; exact HLQ/profile belongs to the later authorized plan. This document does not execute them. [IBM compile/link/run tutorial](https://www.ibm.com/docs/en/developer-for-zos/16.0.x?topic=tutorial-submitting-jcl-compile-link-run-jobs).
3. Assemble **COBDATFT and MVSWAIT** from separately pinned licensed/public source members using HLASM; bind object modules with the recorded LE libraries and the source-required AMODE/RMODE. Compile minimal COBOL callers with frozen argument layouts and call each module, including boundary dates and zero/positive wait values. Keep assembly return codes, binder maps, entry names, module hashes, caller stdout/RC and observed effects. An assemble-only result is incomplete. Do not guess an AMODE from the name: inspect original declarations and caller ABI; IBM warns that attributes alone do not determine a mismatched direct caller's addressing mode. [IBM addressing-mode rules](https://www.ibm.com/docs/en/zos/3.2.0?topic=mode-amode-rmode-combinations-execution-time).
4. Run the current preregistered INTCALC/POSTTRAN cases exactly once per declared scenario; compare raw EBCDIC record hashes first, then a separate pinned decoding/normalization stage. Preserve disagreements. The decimal-only restriction remains until the mixed-key probe and real-program keyed operations pass on this rung and Howard explicitly accepts the narrower conclusion.

## Which limits can change

| Existing twin limitation | Targeted ZD&T evidence | Remaining boundary |
|---|---|---|
| Indexed bridge/backend | VSAM READ/NEXT/START/WRITE/REWRITE, duplicate/missing/EOF, primary and alternate mixed keys | Only preregistered operations; no locking/recovery/concurrency or exhaustive VSAM claim |
| ASCII/cp037 and program collation | Raw EBCDIC records; runtime/literal comparison, SORT/MERGE and indexed order independently | No automatic expansion to untested domains |
| INTCALC parameter ABI | Real JCL PARM length/date reaching the compiled caller | Only this argument layout and compiler level |
| CEE3ABD shim / LE propagation | Actual LE abend, timing parameter, JES/step RC and dump policy | Host RC12 shim remains explicitly different |
| Runtime clock and COBDATFT | Frozen date/time setup, assembler caller and output timestamp observation | No host clock change inferred; precision/timezone conclusion is specific |
| MVSWAIT | Assembler+bind+caller proves wait/return behavior and parameter ABI | No scheduler or performance equivalence claim |
| File-status fault substitutes | Actual missing allocation, duplicate/missing key and declared failed update cases | Injected host30/37/etc stay unknown unless directly matched |
| Java service / candidate | Independent Java comparison may be added to the same frozen scenarios later | No absent POSTTRAN candidate is invented by a z/OS result |

This can move particular register entries from unknown to observed-at-specific-z/OS-level. It cannot make the entire twin authoritative. Purchase/licensing, supported hardware, exact source for both assembler modules, a provisioned instance, signed plan and explicit execution approval remain external prerequisites.
