# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.10-demo`  
**Decision:** **BLOCKED**  
**Dossier identity:** `0007f2f61bdb69bb7ca0cccf5bd6f28136fbf1bf3e176198471a52c9f682b0f8`

## Promotion rationale

Release is blocked until independently observed z/OS equivalence evidence exists.

## Unresolved gaps

- `mainframe-equivalence`


## Runtime policy decisions

| Policy | Subject | Status | Gaps |
|---|---|---:|---:|
| `runtime.development_readiness` | `runtime-run:local-oracle-intcalc-reference` | **passed** | 0 |
| `runtime.mainframe_equivalence` | `runtime-run:local-oracle-intcalc-reference` | **blocked** | 4 |
| `runtime.development_readiness` | `runtime-run:recorded-zos-intcalc-replay` | **passed** | 0 |
| `runtime.mainframe_equivalence` | `runtime-run:recorded-zos-intcalc-replay` | **blocked** | 8 |
| `runtime.development_readiness` | `runtime-run:zosmf-intcalc-job00001` | **passed** | 0 |
| `runtime.mainframe_equivalence` | `runtime-run:zosmf-intcalc-job00001` | **blocked** | 8 |

## Evidence inventory

| Kind | Identifier | SHA-256 |
|---|---|---|
| `work_order` | `carddemo:intcalc:bounded-repair` | `c48d9721373c8deb…` |
| `source_evidence_pack` | `evidence:source-pack` | `b375a4ab12746e54…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `f292fc48412c4f72…` |
| `decision_input` | `release:carddemo-intcalc:v0.10-demo` | `f292fc48412c4f72…` |
| `decision_input` | `runtime-run:local-oracle-intcalc-reference` | `9ada6983de37a9aa…` |
| `decision_input` | `runtime-run:recorded-zos-intcalc-replay` | `d7d2cb1562f26f1c…` |
| `decision_input` | `runtime-run:zosmf-intcalc-job00001` | `c821cdbcd2ba17c4…` |

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 13
- Ledger head: `2e473a7165d156a7106023f287131282d8df993372ddd3e7b06d5cf37a942e69`
- Signature algorithm: `none`

## Limitations

- The committed canonical checkpoint is unsigned; live environments should configure a signing key.
- Simulated and local observations do not establish production mainframe equivalence.
- This dossier is a deterministic evidence summary, not a substitute for organizational approval policy.
