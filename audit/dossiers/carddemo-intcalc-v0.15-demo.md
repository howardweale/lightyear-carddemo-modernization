# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.15-demo`

**Decision:** **BLOCKED**

**Dossier identity:** `472e3aebe26f907b452709b63bb65a84f91a65da150e9f5aff28d9522f57c240`

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
| `portfolio_plan` | `carddemo:modernization:v0.15` | `e72cf47cf39e0fec…` |
| `source_evidence_pack` | `evidence:source-pack` | `71e640297349eb7b…` |
| `decision_input` | `execution:carddemo-hardened-plane` | `83d937880f17192b…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `4b8141cf27d91fd7…` |
| `semantic_memory_snapshot` | `memory:verified-experiences` | `42000f0e821e12b7…` |
| `decision_input` | `release:carddemo-intcalc:v0.15-demo` | `4b8141cf27d91fd7…` |
| `decision_input` | `runtime-run:local-oracle-intcalc-reference` | `9ada6983de37a9aa…` |
| `decision_input` | `runtime-run:recorded-zos-intcalc-replay` | `d7d2cb1562f26f1c…` |
| `decision_input` | `runtime-run:zosmf-intcalc-job00001` | `c821cdbcd2ba17c4…` |

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
- Plan: `e72cf47cf39e0fecb9156db76410f4f0d51d0741d3e1a037c06d41ca48182609`

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 17
- Ledger head: `df816bb5108e25c80e19830e0c97eb4f3567717193b547fad0a211303942274a`
- Signature algorithm: `none`

## Limitations

- The committed canonical checkpoint is unsigned; live environments should configure a signing key.
- Simulated and local observations do not establish production mainframe equivalence.
- Execution policy conformance or an OCI probe alone is not signed factory-run proof.
- This dossier is a deterministic evidence summary, not a substitute for organizational approval policy.
