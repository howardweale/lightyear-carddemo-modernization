# LIGHTYEAR release evidence dossier

**Release:** `release:carddemo-intcalc:v0.16-demo`

**Decision:** **BLOCKED**

**Dossier identity:** `b1d4b1d63f93ac6371c7dc68685ab9cf86734a64c689d808ab11b4b0488338f5`

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
| `portfolio_plan` | `carddemo:modernization:v0.15` | `5b87d98d6b939087…` |
| `source_evidence_pack` | `evidence:source-pack` | `3c6fdf1d7aeeb7c3…` |
| `decision_input` | `execution:carddemo-hardened-plane` | `83d937880f17192b…` |
| `durable_conformance_receipt` | `factory:durable-conformance` | `e2aa93dfc11d1969…` |
| `durable_execution_policy` | `factory:durable-control-plane` | `72b0c927dc60dc8b…` |
| `graph_snapshot` | `lightyear:carddemo-modernization` | `a08b05b5f01df478…` |
| `semantic_memory_snapshot` | `memory:verified-experiences` | `42000f0e821e12b7…` |
| `decision_input` | `release:carddemo-intcalc:v0.16-demo` | `a08b05b5f01df478…` |
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
- Plan: `5b87d98d6b939087c7ec1ede85b936520a9bba7ab06769386793f9de9f985ae8`

## Audit checkpoint

- Ledger: `lightyear:carddemo:audit`
- Events: 18
- Ledger head: `91061cfc918cbb572c9d0b30919a32e93129b49de7083c42720d97eb5d2e2f99`
- Signature algorithm: `none`

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
