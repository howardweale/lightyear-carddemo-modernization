# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.11-demo`  
**Decision:** **BLOCKED**  
**Dossier identity:** `56d95fe4296a65397e79c93c4e66f8e9e5cebdd691631b918406cfd570488d13`

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
| `execution.hardened_readiness` | `execution:carddemo-hardened-plane` | **blocked** | 2 |

## Evidence inventory

| Kind | Identifier | SHA-256 |
|---|---|---|
| `work_order` | `carddemo:intcalc:bounded-repair` | `c48d9721373c8deb…` |
| `source_evidence_pack` | `evidence:source-pack` | `6a22a46bcf00c42c…` |
| `decision_input` | `execution:carddemo-hardened-plane` | `36bd915c65150ad7…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `e6d502533a20d41e…` |
| `decision_input` | `release:carddemo-intcalc:v0.11-demo` | `e6d502533a20d41e…` |
| `decision_input` | `runtime-run:local-oracle-intcalc-reference` | `9ada6983de37a9aa…` |
| `decision_input` | `runtime-run:recorded-zos-intcalc-replay` | `d7d2cb1562f26f1c…` |
| `decision_input` | `runtime-run:zosmf-intcalc-job00001` | `c821cdbcd2ba17c4…` |

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 15
- Ledger head: `9257a15af3dad5d03fd2983f0fa327502c19766cd90b002b24898d081734a9fb`
- Signature algorithm: `none`

## Limitations

- The committed canonical checkpoint is unsigned; live environments should configure a signing key.
- Simulated and local observations do not establish production mainframe equivalence.
- Execution policy conformance is not proof that a live container runtime enforced it.
- This dossier is a deterministic evidence summary, not a substitute for organizational approval policy.
