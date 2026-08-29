# LIGHTYEAR source-only pilot dossier

**Release:** 0.31.0
**Pilot:** `lightyear-carddemo-source-only-v0.31`
**Dossier identity:** `69ccf5da08daa188e7999f2f907e1c51cdb05ad0eed4a491b48f390b66408b2f`

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
| runtime-dependency-contract | `pilot/runtime-manifest.json` | `50422731bfc7d5dd5a4bfdbbd52ce987e46dbb7fd030d5cfb1efa6fb099da1dc` |
| advisory-modernization-planning-contract | `pilot/assessment-policy.json` | `a60489ddfc849e3e3e41d9d7e84bcd94b4ef9e4195153caaf86c2efe477af938` |
| estate-discovery | `knowledge/graph.receipt.json` | `f12ee5dee079a2e612f4875df75020dac12eb2f52f7d5f8698fbddf9f44cc3fc` |
| composite-lineage | `knowledge/composite/estate.receipt.json` | `629c3078e42d6d5dc7d0b23ea1a3d72f86077d97df562d08b115ed4e8a75f262` |
| capability-gates | `knowledge/capabilities/mainframe-readiness.json` | `caa3249f5b299bbe9cf19dfca3d5d8f15c1da62bf1f58414f6a1fd233aa42dc2` |
| language-coverage | `extensions/pli/conformance/coverage.receipt.json` | `31a40aa4b100bd3ce4fb111a6e13dc2ee49654f2588e44b1ff4cd71f3c91503d` |
| mixed-language-development-proof | `extensions/pli/modernization/development.receipt.json` | `9de70abd3d460c0fbd9ae5428e5ed9157e534ec1ff9dcd33f99ec82f7154082a` |
| reproducible-build | `extensions/pli/attestation/build.receipt.json` | `eae569443ea4d9c5e292906cfc89f2e7b6a1e5b002447ca5d21a3131138b1f34` |
| model-qualification-boundary | `factory/qualification/manifest.json` | `13cc4353a228fd3266e9ed11163dfbe478c7a559fe031eff20a927029c64d91b` |
| data-development-proof | `data-modernization/receipts/authfrds.offline.receipt.json` | `2a2e94f80d2c606b86c23eac276bcc01f46a74b92ba92ac0d3e061b4c3534a4f` |
| data-development-proof | `data-modernization/receipts/authfrds.oracle-offline.receipt.json` | `ae8453104e8745628a6cad8893f8d22849a34847a5ffbfeb5a6d56eae61897b6` |
| cdc-cutover-recovery-rehearsal | `data-modernization/rehearsal/receipt.json` | `d2f0d194f39325a86063bd6609fdb631190c6686c727e348c7f36c30fffff7fd` |
| mainframe-collection-mechanism | `extensions/adapters/appliance/appliance.receipt.json` | `228190bdbe87912eb0c38e3fe0537d7a2dd66819f0e01cb2c0f93afd5c55cc29` |
| bounded-runtime-readiness | `readiness/cics-vsam/readiness-receipt.json` | `2dd8e24e7a23814b6e643ff186f1272071f220b7ac0e03cc57fffc1abcd7dc5a` |
| bounded-runtime-readiness | `readiness/ims-expiry/readiness-receipt.json` | `f95a3d2e5d06232ae2eb00671131a055c4024d6e1546152239c83b0de990a557` |
| bounded-language-readiness | `readiness/asm-date/readiness-receipt.json` | `faf7a3109e4f6308a4ac71c706c2725e272fac666b5bba3d1a57ea63633dad92` |
| auditor-projection | `audit/dossiers/carddemo-intcalc-v0.19-demo.json` | `aa49f4a4944a67f503b8d343e1195aace6a3cc9007c7ec06c9080c9fcd9cf6e8` |

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
