# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.11.1-demo`  
**Decision:** **BLOCKED**  
**Dossier identity:** `f5b47bab58ba152030802387f96f8a708efe46815335822fca584599b93f08a4`

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
| `work_order` | `carddemo:intcalc:bounded-repair` | `c48d9721373c8deb…` |
| `source_evidence_pack` | `evidence:source-pack` | `edd74eda832a4559…` |
| `decision_input` | `execution:carddemo-hardened-plane` | `36bd915c65150ad7…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `d9e7cdf8054188f2…` |
| `decision_input` | `release:carddemo-intcalc:v0.11.1-demo` | `d9e7cdf8054188f2…` |
| `decision_input` | `runtime-run:local-oracle-intcalc-reference` | `9ada6983de37a9aa…` |
| `decision_input` | `runtime-run:recorded-zos-intcalc-replay` | `d7d2cb1562f26f1c…` |
| `decision_input` | `runtime-run:zosmf-intcalc-job00001` | `c821cdbcd2ba17c4…` |

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 15
- Ledger head: `0ec4cb5c61d22bdf8bda089c5fea7f422152950b9b8372f7fad7af3bd30efdbd`
- Signature algorithm: `none`

## Limitations

- The committed canonical checkpoint is unsigned; live environments should configure a signing key.
- Simulated and local observations do not establish production mainframe equivalence.
- Execution policy conformance or an OCI probe alone is not signed factory-run proof.
- This dossier is a deterministic evidence summary, not a substitute for organizational approval policy.
