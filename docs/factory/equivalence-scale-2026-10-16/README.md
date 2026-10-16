# Equivalence scale — E1 signing and measurement

After the two pending class signatures: **185/227 (81.5%)**, using the preserved #341 measurement.

Resolved now: **8/227 (3.5%)**. No new signed decision is inferred from chat.

Held out: **TRANREPT/CBTRN03C: two compiler identities in 413 sites, zero class matches; no evidence of generality.** CBSTM03A/B have not yet been measured.

| Program | Route | Resolved now | After pending signatures |
|---|---|---:|---:|
| INTCALC | S1 compiler | 4 | 4 |
| INTCALC | S2 signed class | 0 | 81 |
| POSTTRAN | S1 compiler | 3 | 3 |
| POSTTRAN | S2 signed class | 0 | 96 |
| POSTTRAN | S3 solver | 1 | 1 |

The union of exact member IDs has no overlap with the existing eight resolutions.
INTCALC's three unobservable members remain in its denominator. Nine additional
POSTTRAN evidence-gap/survivor members are outside the 227 argued population and
remain in the full mutation denominator. These are different denominators.
Reviewer minutes per 1,000 sites are not measured.

## Signing the two requests

Use `INTCALC-tower-contract.json` and `POSTTRAN-tower-contract.json` beside this
document. Each binds the complete original class packet, its census, and a new
30-member audit with source context. The companion `*-class-request.json` files
retain the exact class proof for the signed review overlay.

The old contracts pointed at measurement commit `7d95d7d`, where the generated
packet files did not yet exist. These contracts bind the identical packet bytes
at publication commit `78be9cafb322b6a9dacaa94fd6027df2aeb605e5`. Measurement head,
matcher, members and class-proof seals stay unchanged. The new audit selection
is explicit; this document does not assert Howard has reviewed this newly
packaged sample or applied a signature.

Import with the **existing Factory root**, then open Factory Work queue on 8769.
These commands prepare unsigned requests; they do not provision, activate or sign.
Do not substitute the B06 root or port 8768.

```powershell
$Repository = 'C:\Users\howar\.codex\worktrees\equivalence-scale\lightyear-carddemo-modernization'
$Packet = Join-Path $Repository 'docs\factory\equivalence-scale-2026-10-16'
# Set $FactoryRoot to the existing provisioned Factory data root.
# Use the installed Tower Python environment as $Python.
& $Python -m lightyear_control_tower.factory_import --repository $Repository --root $FactoryRoot --contract "$Packet\INTCALC-tower-contract.json"
& $Python -m lightyear_control_tower.factory_import --repository $Repository --root $FactoryRoot --contract "$Packet\POSTTRAN-tower-contract.json"
```

In each request, verify the program, twin scope, source/matcher hashes and all
81 or 96 member IDs. Record individual outcomes and reasons through the Tower.
After signing, export the signed decisions and journal with the operator-owned
public trust configuration. `tools.apply_equivalence_reviews` verifies them and
writes a new overlay; the #341 ledger remains unchanged. A class signature does
not authorize a threshold, release, model spend or z/OS-facing claim.

## Work order and gates

E1 adds projection accounting, real committed-blob Tower import tests, immutable
audit packets and the existing full CI pipeline repeated twice. Fresh results
must be reported separately from the historical figures above.

E2 requires byte storage and whole-program control/effects, zero unsupported
constructs for the requested programs, and 1,000 byte-exact differential inputs
per program. E3 analyses cannot claim equivalence until these gates and the
all-killed-mutants rejection checks pass. E3 interval assumptions require their
own scoped signatures. E4 requires 50 schemata/individual build comparisons and
measured speedup. E5 requires real held-out campaigns, not inventories alone.
E6 is a prospective unsigned policy; E7 groups residual evidence without model
calls. None of these stages is represented as completed by E1.

Execution and tests are CI-only. No model calls or main merge are authorized.
Z3 remains pinned to 4.15.3.0 and the existing wheel SHA-256s. All raw #341
evidence, historical scores and requests remain immutable.
