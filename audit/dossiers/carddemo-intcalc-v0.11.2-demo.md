# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.11.2-demo`  
**Decision:** **BLOCKED**  
**Dossier identity:** `4bfa08119b903d6051b3024216bafeb3fe7988c5834acd23ac845ee86f798b52`

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
| `source_evidence_pack` | `evidence:source-pack` | `2c5ccbaaaf0d2d89…` |
| `decision_input` | `execution:carddemo-hardened-plane` | `36bd915c65150ad7…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `b2393f5cfee4d92d…` |
| `decision_input` | `release:carddemo-intcalc:v0.11.2-demo` | `b2393f5cfee4d92d…` |
| `decision_input` | `runtime-run:local-oracle-intcalc-reference` | `9ada6983de37a9aa…` |
| `decision_input` | `runtime-run:recorded-zos-intcalc-replay` | `d7d2cb1562f26f1c…` |
| `decision_input` | `runtime-run:zosmf-intcalc-job00001` | `c821cdbcd2ba17c4…` |

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 15
- Ledger head: `089aa9f4d519a8c54805916e9217ac7b7842da5f7268d8e1cf504fe3e726820b`
- Signature algorithm: `none`

## Limitations

- The committed canonical checkpoint is unsigned; live environments should configure a signing key.
- Simulated and local observations do not establish production mainframe equivalence.
- Execution policy conformance or an OCI probe alone is not signed factory-run proof.
- This dossier is a deterministic evidence summary, not a substitute for organizational approval policy.
