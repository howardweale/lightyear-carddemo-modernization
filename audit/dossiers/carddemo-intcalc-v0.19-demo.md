# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.19-demo`

**Decision:** **BLOCKED**

**Dossier identity:** `b99af3e6c6c50c78b6ee3780bedb788a92fd7d16fd4cc1eaf1102a1452bcfacf`

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
| `data_equivalence_receipt` | `carddemo-authorization-authfrds` | `8e2e2dc30cffa320…` |
| `work_order` | `carddemo:intcalc:bounded-repair` | `71e7e34d92dd056a…` |
| `portfolio_plan` | `carddemo:modernization:v0.15` | `7f06fbe59159d487…` |
| `operational_control_policy` | `control-tower:live-evidence-plane` | `943f4c1626a3ac66…` |
| `source_evidence_pack` | `evidence:source-pack` | `9f60bb4b8de022a8…` |
| `decision_input` | `execution:carddemo-hardened-plane` | `83d937880f17192b…` |
| `durable_conformance_receipt` | `factory:durable-conformance` | `6d7cba4bcd1b5153…` |
| `durable_execution_policy` | `factory:durable-control-plane` | `72b0c927dc60dc8b…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `48da03518cd2fb81…` |
| `semantic_memory_snapshot` | `memory:verified-experiences` | `42000f0e821e12b7…` |
| `decision_input` | `release:carddemo-intcalc:v0.19-demo` | `48da03518cd2fb81…` |
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
- Plan: `7f06fbe59159d4873c7e76da42a9a90edf625a973da43d806317c5bd6b64b1cb`

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 21
- Ledger head: `d900843c197522626fae1f2befb80be38ac5825869e0782cee9a959c71120a16`
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
