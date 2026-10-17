# CMS IPPS FY2021 F0 feasibility

**NO-GO for cross-language payment equivalence.** The retained COBOL baseline is FY2021.5 and the Java probe reports FY2021.6. Their equivalence has not been established. This report limits the completed claim to the five-case COBOL F0 interface/compile investigation; it does not turn that limitation into a GO.

Recorded 17 October 2026. Authorized by Howard; performed by Codex. Public CMS software, independently tested. No CMS endorsement. No CMS source, binaries, rates or payment values are included.

## Durable retained evidence

[CI run 38955068672](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38955068672) used commit `70aa78b8743988445791d8633e9a23ea240500eb`. The paired JSON preserves counts, receipt hashes and the artifact digest beyond its fourteen-day artifact retention. These are retained results, not fresh CI for the follow-up harness.

| Check | Result |
|---|---|
| Compilation | 51 of 59 programs; 75 dialect attempts |
| IPPS compilation | 30 of 38 programs |
| ESRD compilation | 21 of 21 programs |
| Generated COBOL calls | 5 of 5 complete |
| Actual input-byte checks | 225 of 225 passed |
| Captured COBOL fields | 377 per case |

Eight terminal compiler failures remain explicit limitations, bound by program, source hash, dialect, return code and diagnostic hash. They are not successful compilations. A different or additional failure makes the new harness exit nonzero.

## Version and output gaps

The retained comparison metadata combines CI COBOL hashes with a retained private Java probe; it is not a new matched-version CI run. It maps 71 of 75 Java outputs. Each of the five cases has 37 equal values, 7 different values, 27 Java nulls and 4 unmapped outputs. Nulls were not coerced to zero. No payment-equivalence conclusion follows from these counts. The private comparison and alignment record are bound by hash in the JSON; their pricing values are not published.

## Compiler-log publication boundary

A formatting audit of 75 retained logs found 0 numbered source-excerpt candidates. That does not prove arbitrary compiler text contains no source fragments. The follow-up workflow therefore uploads no raw compiler logs or diagnostic strings. A strict allowlist emits metadata only; a fixture containing a quoted source line checks that the line cannot reach the public receipt.

## F1–F4 estimate

| Phase | Work | Engineer days |
|---|---|---:|
| F1 | Reusable driver, generated ABI mappings and version alignment | 3–5 |
| F2 | Matched-version corpus, error paths and field-level mapping review | 4–7 |
| F3 | Independent differential comparison, rounding boundaries and mutation probes | 5–10 |
| F4 | Reproducible packaging, durable receipts and governed review | 2–4 |

Planning estimate, not measured delivery time; excludes licensing review, CMS clarification and obtaining a matching release.

## Input field names for review

These are the 45 input bindings in the independently written F0 harness: 8 claim fields and 37 provider fields. Identifiers are listed without CMS source statements or rate values.

| Group | JSON input | CMS field identifier |
|---|---|---|
| CLAIM | `providerCcn` | `B-21-PROVIDER-NO` |
| CLAIM | `coveredCharges` | `B-21-CHARGES-CLAIMED` |
| CLAIM | `coveredDays` | `B-21-COVERED-DAYS` |
| CLAIM | `diagnosisRelatedGroup` | `B-21-DRG` |
| CLAIM | `dischargeDate` | `B-21-DISCHARGE-DATE` |
| CLAIM | `lengthOfStay` | `B-21-LOS` |
| CLAIM | `lifetimeReserveDays` | `B-21-LTR-DAYS` |
| CLAIM | `reviewCode` | `B-21-REVIEW-CODE` |
| PROVIDER | `bedSize` | `P-NEW-BED-SIZE` |
| PROVIDER | `bundleModel1Discount` | `P-MODEL1-BUNDLE-DISPRCNT` |
| PROVIDER | `capitalCostToChargeRatio` | `P-NEW-CAPI-CSTCHG-RATIO` |
| PROVIDER | `capitalExceptionPaymentRate` | `P-NEW-CAPI-EXCEPTIONS` |
| PROVIDER | `capitalIndirectMedicalEducationRatio` | `P-NEW-CAPI-IME` |
| PROVIDER | `costOfLivingAdjustment` | `P-NEW-COLA` |
| PROVIDER | `hrrAdjustment` | `P-NEW-HOSP-HRR-ADJUSTMT` |
| PROVIDER | `internsToBedsRatio` | `P-NEW-INTERN-RATIO` |
| PROVIDER | `lowVolumeAdjustmentFactor` | `P-LV-ADJ-FACTOR` |
| PROVIDER | `medicaidRatio` | `P-NEW-MEDICAID-RATIO` |
| PROVIDER | `oldCapitalHoldHarmlessRate` | `P-NEW-CAPI-OLD-HARM-RATE` |
| PROVIDER | `operatingCostToChargeRatio` | `P-NEW-CCR` |
| PROVIDER | `passThroughAmountForDirectMedicalEducation` | `P-NEW-PASS-AMT-DIR-MED-ED` |
| PROVIDER | `passThroughAmountForOrganAcquisition` | `P-NEW-PASS-AMT-ORGAN-ACQ` |
| PROVIDER | `passThroughTotalAmount` | `P-NEW-PASS-AMT-PLUS-MISC` |
| PROVIDER | `ppsFacilitySpecificRate` | `P-NEW-CMI-ADJ-CPD` |
| PROVIDER | `supplementalSecurityIncomeRatio` | `P-NEW-SSI-RATIO` |
| PROVIDER | `uncompensatedCareAmount` | `P-UNCOMP-CARE-AMOUNT` |
| PROVIDER | `vbpAdjustment` | `P-NEW-VAL-BASED-PURCH-ADJUST` |
| PROVIDER | `providerCcn` | `P-NEW-PROVIDER-NO` |
| PROVIDER | `countyCode` | `P-NEW-COUNTY-CODE` |
| PROVIDER | `effectiveDate` | `P-NEW-EFF-DATE` |
| PROVIDER | `fiscalYearBeginDate` | `P-NEW-FY-BEGIN-DATE` |
| PROVIDER | `providerType` | `P-NEW-PROVIDER-TYPE` |
| PROVIDER | `stateCode` | `P-NEW-STATE-CODE` |
| PROVIDER | `capitalPpsPaymentCode` | `P-NEW-CAPI-PPS-PAY-CODE` |
| PROVIDER | `cbsaActualGeographicLocation` | `P-NEW-CBSA-GEO-LOC` |
| PROVIDER | `cbsaWageIndexLocation` | `P-NEW-CBSA-RECLASS-LOC` |
| PROVIDER | `cbsaStandardizedAmountLocation` | `P-NEW-CBSA-STAND-AMT-LOC` |
| PROVIDER | `hospitalQualityIndicator` | `P-NEW-CBSA-HOSP-QUAL-IND` |
| PROVIDER | `hrrParticipantIndicator` | `P-NEW-HOSP-READMISSION-REDU` |
| PROVIDER | `hacReductionParticipantIndicator` | `P-HAC-REDUC-IND` |
| PROVIDER | `vbpParticipantIndicator` | `P-NEW-VAL-BASED-PURCH-PARTIPNT` |
| PROVIDER | `waiverIndicator` | `P-NEW-WAIVER-CODE` |
| PROVIDER | `newHospital` | `P-NEW-CAPI-NEW-HOSP` |
| PROVIDER | `supplementalWageIndexIndicator` | `P-NEW-SUPP-WI-IND` |
| PROVIDER | `supplementalWageIndex` | `P-NEW-SUPP-WI` |

## Still required

- Resolve or explicitly justify the FY2021.5 versus FY2021.6 baseline before any GO decision.
- Explain seven differences, twenty-seven Java nulls and four unmapped outputs in each of the five retained comparisons; null is not zero.
- Complete F1–F4 at the agreed matched-version scope; five generated cases are not broad payment verification.
- Obtain fresh CI evidence for these fail-closed harness changes.

No signing, activation, attempt consumption, model calls or Phase 2 execution. Fresh validation is CI-only.
