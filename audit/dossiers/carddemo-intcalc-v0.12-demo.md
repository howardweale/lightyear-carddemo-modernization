# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.12-demo`

**Decision:** **BLOCKED**

**Dossier identity:** `3ffc365eae9bc41688fa0db19a4e7159c69a8962094b0a583331e0b1e75a1057`

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
| `source_evidence_pack` | `evidence:source-pack` | `bad2410356663c38…` |
| `decision_input` | `execution:carddemo-hardened-plane` | `83d937880f17192b…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `d5891ab03fb3dcaf…` |
| `decision_input` | `release:carddemo-intcalc:v0.12-demo` | `d5891ab03fb3dcaf…` |
| `decision_input` | `runtime-run:local-oracle-intcalc-reference` | `9ada6983de37a9aa…` |
| `decision_input` | `runtime-run:recorded-zos-intcalc-replay` | `d7d2cb1562f26f1c…` |
| `decision_input` | `runtime-run:zosmf-intcalc-job00001` | `c821cdbcd2ba17c4…` |

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 15
- Ledger head: `54059f30e69dabb892227e666c0d97500fe36c5ebd083b28287ce83b510ba9f9`
- Signature algorithm: `none`

## Limitations

- The committed canonical checkpoint is unsigned; live environments should configure a signing key.
- Simulated and local observations do not establish production mainframe equivalence.
- Execution policy conformance or an OCI probe alone is not signed factory-run proof.
- This dossier is a deterministic evidence summary, not a substitute for organizational approval policy.
