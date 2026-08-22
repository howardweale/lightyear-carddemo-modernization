# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.18-demo`

**Decision:** **BLOCKED**

**Dossier identity:** `28390ad5ca65c3769c16f1b21fa5c6f09feb15c2178ed8b0cb90d66ea8e7fb75`

## Promotion rationale

Release is blocked until every independent runtime and execution-security gate has evidence.

## Unresolved gaps

- `hardened-execution-enforcement`
- `mainframe-equivalence`


## Runtime and execution policy decisions

| Policy | Subject | Status | Gaps |
|---|---|---:|---:|
| `runtime.development_readiness` | `runtime-run:local-oracle-intcalc-reference` | **passed** | 0 |
| `runtime.mainframe_equivalence` | `runtime-run:local-oracle-intcalc-reference` | **blocked** | 4 |
| `runtime.development_readiness` | `runtime-run:recorded-zos-intcalc-replay` | **passed** | 0 |
| `runtime.mainframe_equivalence` | `runtime-run:recorded-zos-intcalc-replay` | **blocked** | 8 |
| `runtime.development_readiness` | `runtime-run:zosmf-intcalc-job00001` | **passed** | 0 |
| `runtime.mainframe_equivalence` | `runtime-run:zosmf-intcalc-job00001` | **blocked** | 8 |
| `execution.hardened_readiness` | `execution:carddemo-hardened-plane` | **blocked** | 4 |

## Evidence inventory

| Kind | Identifier | SHA-256 |
|---|---|---|
| `work_order` | `carddemo:intcalc:bounded-repair` | `71e7e34d92dd056a…` |
| `portfolio_plan` | `carddemo:modernization:v0.15` | `e4550120899fac23…` |
| `operational_control_policy` | `control-tower:live-evidence-plane` | `b4c43578b6cb7060…` |
| `source_evidence_pack` | `evidence:source-pack` | `1ade0d7a2645c75f…` |
| `decision_input` | `execution:carddemo-hardened-plane` | `83d937880f17192b…` |
| `durable_conformance_receipt` | `factory:durable-conformance` | `6c1c810e62a25de3…` |
| `durable_execution_policy` | `factory:durable-control-plane` | `72b0c927dc60dc8b…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `4fab83d8a18c08ba…` |
| `semantic_memory_snapshot` | `memory:verified-experiences` | `42000f0e821e12b7…` |
| `decision_input` | `release:carddemo-intcalc:v0.18-demo` | `4fab83d8a18c08ba…` |
| `decision_input` | `runtime-run:local-oracle-intcalc-reference` | `9ada6983de37a9aa…` |
| `decision_input` | `runtime-run:recorded-zos-intcalc-replay` | `d7d2cb1562f26f1c…` |
| `decision_input` | `runtime-run:zosmf-intcalc-job00001` | `c821cdbcd2ba17c4…` |
| `cics_vsam_readiness_receipt` | `workload:carddemo-cics-vsam-account-view` | `6bbe74439aa51d14…` |

## Verified semantic memory

- Status: `verified`
- Experiences: 3
- Snapshot: `42000f0e821e12b7716717db7aaa3de6e6ad75eea00d7fa5b18f67c35344fa38`

## Modernization portfolio

- Status: `approval_required`
- Work cells: 3
- Execution waves: 2
- Detected conflicts: 1
- Approval authority: `human`
- Plan: `e4550120899fac23872577609189c5d45789c9c889189c391a0da806e6ba9321`

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 20
- Ledger head: `c2312585c7db4274ebf41a6ca51379a3eef7decbf08e8c67a0af5c37456beda8`
- Signature algorithm: `none`

## CICS/VSAM readiness

- Status: `blocked`
- Development ready: `True`
- Mainframe equivalent: `False`
- Signed: `False`
- Receipt: `6bbe74439aa51d147bcb266f95af048a357f2e44dc32bcc200406a7884424389`
- Gap: No authorized zos_observed CAVW baseline is bound to this comparison.
- Gap: No external equivalence signing key was configured.

## Durable recovery control plane

- Status: `contract_published`
- Reference backend: `sqlite-wal-reference`
- Approval consumption: `exactly-once`
- Event integrity: `sha256-chain`
- Production adapter: `postgresql-object-store`
- Crash-recovery conformance: `passed`
- Policy: `72b0c927dc60dc8b8c0412c79f9fa9db19e8984f70d32007aa63dbed89eeaf4d`

## Limitations

- The committed canonical checkpoint is unsigned; live environments should configure a signing key.
- Simulated and local observations do not establish production mainframe equivalence.
- Execution policy conformance or an OCI probe alone is not signed factory-run proof.
- This dossier is a deterministic evidence summary, not a substitute for organizational approval policy.
