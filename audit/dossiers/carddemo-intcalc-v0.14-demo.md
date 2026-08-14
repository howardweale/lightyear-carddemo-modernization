# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.14-demo`

**Decision:** **BLOCKED**

**Dossier identity:** `e67dad20aa475dd6a07a72a24c24a89f6d27a4ae57ebdc07660f3c749fbf8423`

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
| `source_evidence_pack` | `evidence:source-pack` | `ed0f2387aed68ef6…` |
| `decision_input` | `execution:carddemo-hardened-plane` | `83d937880f17192b…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `6c999445e3530cff…` |
| `semantic_memory_snapshot` | `memory:verified-experiences` | `42000f0e821e12b7…` |
| `decision_input` | `release:carddemo-intcalc:v0.14-demo` | `6c999445e3530cff…` |
| `decision_input` | `runtime-run:local-oracle-intcalc-reference` | `9ada6983de37a9aa…` |
| `decision_input` | `runtime-run:recorded-zos-intcalc-replay` | `d7d2cb1562f26f1c…` |
| `decision_input` | `runtime-run:zosmf-intcalc-job00001` | `c821cdbcd2ba17c4…` |

## Verified semantic memory

- Status: `verified`
- Experiences: 3
- Snapshot: `42000f0e821e12b7716717db7aaa3de6e6ad75eea00d7fa5b18f67c35344fa38`

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 16
- Ledger head: `a2c5aba7db42de0ee6825fd2831127a1351d4a56e67522fb66c431880d4cde6b`
- Signature algorithm: `none`

## Limitations

- The committed canonical checkpoint is unsigned; live environments should configure a signing key.
- Simulated and local observations do not establish production mainframe equivalence.
- Execution policy conformance or an OCI probe alone is not signed factory-run proof.
- This dossier is a deterministic evidence summary, not a substitute for organizational approval policy.
