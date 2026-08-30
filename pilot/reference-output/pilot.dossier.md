# LIGHTYEAR source-only pilot dossier

**Release:** 0.33.0
**Pilot:** `lightyear-carddemo-source-only-v0.33.0`
**Dossier identity:** `6b01c5d2c365c858345b0ade986eb73a6d092ebf4cffed87c4ba58b8e2593bcb`

## Executive result

The governed source-only pilot is ready. This result proves deterministic offline intake,
customer-specific static estate analysis, evidence assembly, and mainframe-onboarding preflight. It does not prove live
mainframe equivalence or production readiness.

| Posture | Result |
|---|---:|
| Source-only pilot ready | **true** |
| Model qualified | **false** |
| Mainframe equivalent | **false** |
| Production ready | **false** |

## Estate summary

The customer-specific estate binds **52 nodes** and **58 relationships**
to **10 approved source files**, with **2 unresolved references** retained for review.

## Modernization plan

The assessment identifies **4 connected application slices**; **2** need boundary closure.
Business priority is not inferred, automatic dispatch is disabled, and every pilot selection requires a human decision.

| Wave | Purpose | Slices | Status |
|---:|---|---:|---|
| 0 | boundary-closure | 2 | advisory |
| 1 | human-pilot-selection | 4 | advisory |
| 2 | development-proof | 4 | advisory |
| 3 | authorized-native-validation | 4 | blocked |

## Capability gates

| Capability | Kind | Discovery | Development | Gate 6 | Gate 8 | Equivalent |
|---|---|---:|---:|---|---|---:|
| CICS | runtime | true | true | blocked | blocked | false |
| VSAM | data | true | true | blocked | blocked | false |
| IMS | runtime | true | true | blocked | blocked | false |
| HLASM | language | true | true | blocked | blocked | false |
| PL/I | language | true | true | blocked | blocked | false |
| Db2/Data | data | true | true | blocked | blocked | false |

## Model and migration posture

Model qualification requires **8**
independently sealed evaluations plus an approved successful portfolio run. None are
committed as current qualifying evidence, so no model is declared qualified.

The data-movement rehearsal passed against deterministic Db2-shaped events, but no live
Db2 log or production cutover authorization was observed.

## Bound evidence

| Role | Artifact | SHA-256 |
|---|---|---|
| runtime-dependency-contract | `pilot/runtime-manifest.json` | `5c2c0bb8677d82c71e6f6087dbc9d48c2e4162d76edaf5ee2217d730df9b5c4c` |
| advisory-modernization-planning-contract | `pilot/assessment-policy.json` | `a60489ddfc849e3e3e41d9d7e84bcd94b4ef9e4195153caaf86c2efe477af938` |
| human-selection-and-development-packaging-contract | `pilot/work-package-policy.json` | `36eabc9a698380f2aaecce8eadf719207070c6cc489b5e1edf78163bb0e3fec3` |
| estate-discovery | `knowledge/graph.receipt.json` | `43a0fa2326b496c6d1a0ef44159e724bb66d00acfd48a01ad89d8d3cec4007c0` |
| composite-lineage | `knowledge/composite/estate.receipt.json` | `ef8276fdb0fed4896ce9c91ca9488e2ca4ae36b255dae062cd4d17d3766a72cd` |
| capability-gates | `knowledge/capabilities/mainframe-readiness.json` | `4b346cf3274057a7ed7222a4a44d55508433aebd2e8e53f395c9a8a19e85d224` |
| language-coverage | `extensions/pli/conformance/coverage.receipt.json` | `9e599183e771caf1057d6f6425bdfe449ee2ca35006fb313b39de44e17918a79` |
| mixed-language-development-proof | `extensions/pli/modernization/development.receipt.json` | `8c1f760da5957810a0f9f6ceae74dd83e0b07aa229a7c6107517cb127d4e0de6` |
| reproducible-build | `extensions/pli/attestation/build.receipt.json` | `29718321c6dbb59e5c433e39de15d3cdc5b177cc821dbae906e103f724027ec3` |
| model-qualification-boundary | `factory/qualification/manifest.json` | `13cc4353a228fd3266e9ed11163dfbe478c7a559fe031eff20a927029c64d91b` |
| data-development-proof | `data-modernization/receipts/authfrds.offline.receipt.json` | `2a2e94f80d2c606b86c23eac276bcc01f46a74b92ba92ac0d3e061b4c3534a4f` |
| data-development-proof | `data-modernization/receipts/authfrds.oracle-offline.receipt.json` | `ae8453104e8745628a6cad8893f8d22849a34847a5ffbfeb5a6d56eae61897b6` |
| cdc-cutover-recovery-rehearsal | `data-modernization/rehearsal/receipt.json` | `d2f0d194f39325a86063bd6609fdb631190c6686c727e348c7f36c30fffff7fd` |
| mainframe-collection-mechanism | `extensions/adapters/appliance/appliance.receipt.json` | `f2f83902a02f65c76b2bd87a4ef3ad742f90df6a0921f50eb23b06f2d9360053` |
| bounded-runtime-readiness | `readiness/cics-vsam/readiness-receipt.json` | `2dd8e24e7a23814b6e643ff186f1272071f220b7ac0e03cc57fffc1abcd7dc5a` |
| bounded-runtime-readiness | `readiness/ims-expiry/readiness-receipt.json` | `f95a3d2e5d06232ae2eb00671131a055c4024d6e1546152239c83b0de990a557` |
| bounded-language-readiness | `readiness/asm-date/readiness-receipt.json` | `faf7a3109e4f6308a4ac71c706c2725e272fac666b5bba3d1a57ea63633dad92` |
| auditor-projection | `audit/dossiers/carddemo-intcalc-v0.19-demo.json` | `c79879a2321183c06edbf8233667801d1aac96b561b319e9222e556822603269` |
| database-platform-contract | `data-modernization/semantic-core/database-semantic-core.json` | `ca3114709057e766b26a5eb339c72ba80fc1620cd4f2d070a9bc92e852d803d8` |
| database-semantic-difference-authority | `data-modernization/semantic-core/authfrds.compatibility-ledger.json` | `0cbd98a780b53a0b18977819f5115800ba1067612625e42075fa1f8a05b5586e` |
| database-adapter-development-conformance | `data-modernization/semantic-core/authfrds.adapter-conformance.receipt.json` | `b3cde64bc0ac1ae9327bbf41a295af65ed167d770693e505fdb1b0d94f7972a7` |

## Prohibited claims

- LIGHTYEAR is production-ready.
- LIGHTYEAR has completed a live modernization.
- A model is qualified for autonomous modernization.
- Offline rehearsal proves customer Db2 CDC or cutover.

## Limitations

- All original-system execution and signed live-equivalence gates remain blocked.
- Customer-specific estate results are bounded static analysis; unresolved references remain visible.
- Planning waves are advisory and cannot infer business priority, authorize execution, or dispatch factory work.
- Development readiness applies only to explicitly bounded proof cells and supported subsets.
- The pilot dossier retains hashes and bounded summaries, not customer credentials or raw runtime responses.
