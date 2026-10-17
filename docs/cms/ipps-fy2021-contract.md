# IPPS FY2021 calling contract — F0

Public CMS software, independently tested. This is an interface investigation,
not a verified payment specification or CMS endorsement. All probe claims and
provider inputs are generated; no patient or claims data is used.

## Source bindings and entry points

The downloaded FY2021.5 mainframe release is
`files-fy-20215-software-release.zip`, SHA-256
`83aeeb51bab7f8410756f57504590d741f8d4c02c3db74bf8cce6b98886bc7af`.
The PC installer is a different artifact and does not supply this source.

The callable entry is `PPOPN215`; `PPMGR215` is the file-oriented batch manager.
`PPOPN215` loads or accepts provider and wage tables and calls `PPDRV215`.
`PPDRV215` selects the fiscal-year calculation module; FY2021 uses `PPCAL215`.
Calls use named data items holding module names, not exclusively literal CALL
operands. A literal-only call scan is insufficient to establish completeness.
The file named `PPCAL04E` declares program ID `PPCAL04D`; filename alone is not
a reliable program identifier.

`PPOPN215` takes eight by-reference arguments, in this order:

| Position | Record | Purpose |
|---|---|---|
| 1 | BILL-DATA-2021 | Generated claim inputs |
| 2 | PPS-DATA | Return code and primary pricing outputs |
| 3 | PRICER-OPT-VERS-SW | Table-loading option and version information |
| 4 | PPS-ADDITIONAL-VARIABLES | Detailed operating, capital and adjustment outputs |
| 5 | PPHOLDAR-HOLD-AREA | Shared calculation workspace, from the supplied copybook |
| 6 | PROV-RECORD-FROM-USER | Caller-supplied provider record, 80 + 80 + 150 bytes |
| 7 | MSAX-TABLE-FROM-USER | Caller-supplied legacy MSA table |
| 8 | CBSA-TABLE-FROM-USER | Caller-supplied CBSA table |

Option `A` supplies all tables; `P` supplies the provider and lets the module
load wage tables. Other modes use its file-loading path. A future driver must
verify actual table buffer lengths and signed DISPLAY encoding, not assume the
Java JSON is a byte-compatible record. The COBOL wrapper's caller-table
declarations and internal table capacities require specific adapter review.

## Claim inputs

The COBOL billing record carries a ten-character NPI, six-character provider
number, two-digit review code, three-digit DRG, three-digit length of stay and
covered days, two-digit lifetime-reserve days, and an eight-digit discharge
date. Covered charges have seven integral digits and two fractional digits.
It also has 25 seven-character procedure slots, 25 seven-character diagnosis
slots, four two-character demonstration slots, ten eleven-character national
drug code slots, and five two-character condition-code slots.

The current Java API accepts more expansive layouts: charges have nine integral
digits, condition codes allow 25 entries of two to seven characters, and drug
codes allow up to 449 entries. A matched FY2021 comparison must restrict itself
to the intersection of these domains; do not silently truncate arrays or money.

## Provider and wage inputs

The provider record includes identifying and effective/fiscal/termination
dates; waiver, provider-type and state indicators; geographic, reclassified and
standardized-amount locations; hospital-quality and special-wage indicators;
cost-of-living, intern-to-bed, bed-count, cost-to-charge, SSI and Medicaid
ratios; hospital-specific and capital parameters; pass-through amounts; VBP,
readmission, bundle, HAC and EHR adjustments; uncompensated-care and low-volume
amounts; county and prior-year supplemental wage index.

FY2021 tables present in the source archive include `CBSA212`, `DRGSX211`,
`RATEX213`, `HOUTI212`, `NTECH211`, `PREV200`, `RUFL200` and `MIDNIGHT`.
`CBSA212` and `MSAX045` are data records, not COBOL programs. The other table
members are embedded through COPY where applicable. The PC package also has
`PROVFILE` and `CBSAXFILE`; their existence is not evidence of a portable
provider-file format or a validated GnuCOBOL loader.

Two requirements were observed when constructing generated Java inputs:
FY2021 needs the prior-year wage-index indicator and a positive supplemental
wage index; a non-new hospital needs a compatible capital payment code, and
the readmission participation flag must agree with its numeric adjustment.
An HTTP 200 response with an unpaid return code is not a successful priced case.
The initial fixture refusals are retained separately from the final smoke.

## Outputs and return codes

`PPS-DATA` returns the pricing return code, wage index, outlier days, average
length of stay and cutoff, operating IME adjustment, total payment,
hospital-specific and federal-specific operating portions, operating outlier
payment, regular and lifetime-reserve days used, operating DSH adjustment and
calculation version. Detailed outputs include capital payment components,
DRG weight, threshold/cost variables, new-technology and islet additions,
low-volume amounts, uncompensated-care and quality/readmission adjustments.

Codes below 50 describe paid outcomes; codes 50–99 describe refusals. Relevant
examples are normal payment (00), DRG payment with the per-diem condition (14),
provider lookup failure (51 in COBOL), invalid wage index (52), invalid DRG
(54), date eligibility failure (55), invalid stay (56), invalid review code
(57), capital/provider adjustment failure (65), and invalid VBP flag (68).
The latest Java descriptions are not a substitute for a version-matched code
catalogue; for example, return-code semantics and input domains have evolved.

## Observed Java interface

Executable: `ipps-pricer-application-2.14.1.jar`, SHA-256
`ed9b69d7e6ac04d7cceb846420a42685722719434c0e999d673167edf9e32458`.
CMS documents Java 17; this local F0 smoke used the existing Corretto 21.0.10
runtime with a 512 MiB heap. No runtime was installed or machine setting changed.

The executable is a REST service. The observed OpenAPI document exposes
`POST /v2/price-claim`, accepting `claimData` and `providerData`. Its response
includes `calculationVersion`, `paymentData`, `returnCodeData` and
`additionalCalculationVariables`. The bundled usage text mentions an unversioned
path; the probe used the actual versioned path from the running server.
`GET /openapi.json`, supported-years and table endpoints are also present.
This is a locally executed JAR, not automation of the CMS Web Pricer website.

Only FY2021 was enabled. All five final generated claims were accepted and paid;
the executable reports calculation version **2021.6**, while the available
COBOL source identifies **2021.5**. This version difference must be resolved or
explicitly bounded before any conversion-equivalence claim. Five Java results
alone establish neither COBOL agreement nor payment correctness.
