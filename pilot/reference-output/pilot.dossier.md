# LIGHTYEAR source-only pilot dossier

**Release:** 0.33.0
**Pilot:** `lightyear-carddemo-source-only-v0.33.0`
**Dossier identity:** `56b4dc55a0f0f7fc2136a9f22150dd0e2c7281c021b93abbc7af0b0ce7d36bbb`

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
| estate-discovery | `knowledge/graph.receipt.json` | `21a61a8e7b1a2a7847ba3096e1d6a04fed8a80320ec5ce426f363038cff382e6` |
| composite-lineage | `knowledge/composite/estate.receipt.json` | `caa37a0437aa64b80cdfdf7928e7be2aaf6e8bef3d69d4ceeb9725ce41b4f4a6` |
| capability-gates | `knowledge/capabilities/mainframe-readiness.json` | `73c654676c190178387ec48beddfac8cd6211438c1d3c041a7547eebf868ec95` |
| language-coverage | `extensions/pli/conformance/coverage.receipt.json` | `06d02d73f0469129fa44183758e9faa9b2cd0fd347df27d0c4df83ef98f90b16` |
| mixed-language-development-proof | `extensions/pli/modernization/development.receipt.json` | `872019174d86fae5e79958efdc07726739982ff6129a1f88778c1acd64527578` |
| reproducible-build | `extensions/pli/attestation/build.receipt.json` | `23ad46c400ec728cdc658890d75b50e8d2a7d7a4e8cb9d3cc3368684f4a6f3cb` |
| model-qualification-boundary | `factory/qualification/manifest.json` | `13cc4353a228fd3266e9ed11163dfbe478c7a559fe031eff20a927029c64d91b` |
| data-development-proof | `data-modernization/receipts/authfrds.offline.receipt.json` | `2a2e94f80d2c606b86c23eac276bcc01f46a74b92ba92ac0d3e061b4c3534a4f` |
| data-development-proof | `data-modernization/receipts/authfrds.oracle-offline.receipt.json` | `ae8453104e8745628a6cad8893f8d22849a34847a5ffbfeb5a6d56eae61897b6` |
| cdc-cutover-recovery-rehearsal | `data-modernization/rehearsal/receipt.json` | `d2f0d194f39325a86063bd6609fdb631190c6686c727e348c7f36c30fffff7fd` |
| mainframe-collection-mechanism | `extensions/adapters/appliance/appliance.receipt.json` | `2e8b9f9e4e54243facb9685026c62afbd26b60c71277aa2f3a152e508287479b` |
| bounded-runtime-readiness | `readiness/cics-vsam/readiness-receipt.json` | `2dd8e24e7a23814b6e643ff186f1272071f220b7ac0e03cc57fffc1abcd7dc5a` |
| bounded-runtime-readiness | `readiness/ims-expiry/readiness-receipt.json` | `f95a3d2e5d06232ae2eb00671131a055c4024d6e1546152239c83b0de990a557` |
| bounded-language-readiness | `readiness/asm-date/readiness-receipt.json` | `faf7a3109e4f6308a4ac71c706c2725e272fac666b5bba3d1a57ea63633dad92` |
| auditor-projection | `audit/dossiers/carddemo-intcalc-v0.19-demo.json` | `ecfb78627f806bea77cf5711eb0f80d6fcf7387d5f2e6d6c82f2e86fd1ef1c65` |
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
