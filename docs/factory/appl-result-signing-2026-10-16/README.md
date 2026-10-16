# APPL-RESULT: Windows Factory signing handoff

Projected after both signatures: **185/227 (81.5%)** of the preserved argued population.

Resolved now: **8/227 (3.5%)**. These requests remain unsigned.

Held out: **TRANREPT/CBTRN03C has zero class matches, so there is no evidence of class generality.** No z/OS-facing acceptance is requested.

This is an evidence-only carve-out from draft #341, based directly on `main`.
It does not require merging #341, #357 or any Solver implementation. The only
non-document change is a CI test of the existing importer's handling of these
packets. Historical class proofs, source, census, matcher and ledger bytes are
copied unchanged. The `.py.txt` files are inert review snapshots, not installed
or imported code. Every contract source points to the carve-out evidence commit,
not to a draft #341 commit. Historical commit references inside archived evidence
describe its provenance; they are not importer dependencies.

## Review before signing

Read the complete 30-member sample for each program:

- [INTCALC: 30 samples, 81-member request](INTCALC/review-before-signing.md)
- [POSTTRAN: 30 samples, 96-member request](POSTTRAN/review-before-signing.md)

Each sample shows the original mutation, replacement, argument and numbered
source context. `audit.json` binds the exact source hash, matcher hash, census,
all member IDs and deterministic sample selection. `class-request.json` preserves
the original sealed class proof alongside the new importable contract. Signing
accepts the full listed class, not just the sampled members. The newly packaged
samples await Howard's review; conversational approval of an earlier sample is
not represented as a signature on these contracts.

| Program | Members | Sample | Expected contract SHA-256 / Tower queue suffix |
|---|---:|---:|---|
| INTCALC | 81 | 30 | `50bbd415d2da34c3786681ad1ad390d9add581ca17137b2d4f35ecb05fe7a51f` |
| POSTTRAN | 96 | 30 | `92c9dab92dfa6db53c1cf72a4784775377a886d81026b67850cbd19f14e806c1` |

The contract files use the Tower's canonical JSON bytes with no trailing newline:
their file SHA-256 equals the queue contract SHA-256. The queue IDs are `factory-`
followed by the corresponding full hash above. Do not import the older #357
contracts, whose hashes and evidence locations differ.

## Preconditions

1. Howard has approved the exact final green commit of this standalone PR, and
   it is reachable from `main`. No merge is performed by these commands.
2. The Windows checkout is clean at that approved commit. All referenced evidence
   commits are reachable from it. The final delivery receipt supplies the full
   approved commit once CI and approval are complete; do not substitute a draft
   head or a commit from #341.
3. Howard has reviewed both samples above before signing.
4. Use the **existing Windows Factory root and installed Python environment**.
   The activation record is `docs/factory/factory-local-activation-2026-10-14.json`,
   port **8769**, recorded trusted head
   `b2553d8c1519e2376904c91c30c8dc476597f24ee795f2a59e6e30cf8d58315a`.
   That is the activation-time head: preserve any later verified journal head;
   never reset trust to the old value. No new root, provisioning, activation,
   service restart or Mac Tower is part of this handoff. Never use B06 port 8768
   or its root.

## Commands for Howard on Windows, after the preconditions hold

Set the four variables to the reviewed final commit, its Windows checkout, the
existing Windows Factory root, and the installed Python executable. Paths are
operator-supplied because the public activation record intentionally omits them.

```powershell
$ApprovedCommit = '<exact-final-green-commit-approved-and-on-main>'
$Checkout = '<existing-Windows-checkout-at-that-commit>'
$FactoryRoot = '<existing-Windows-Factory-root>'
$Python = '<installed-Windows-Tower-Python>'
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $FactoryRoot -PathType Container)) { throw 'Existing Factory root required; do not create one' }
if ((git -C $Checkout rev-parse HEAD).Trim() -ne $ApprovedCommit) { throw 'Wrong checkout commit' }
if (git -C $Checkout status --porcelain) { throw 'Use a clean reviewed checkout' }
git -C $Checkout merge-base --is-ancestor $ApprovedCommit origin/main
if ($LASTEXITCODE -ne 0) { throw 'Approved commit is not verified on fetched main' }
$Packet = Join-Path $Checkout 'docs\factory\appl-result-signing-2026-10-16'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath "$Packet\INTCALC\contract.json").Hash.ToLowerInvariant() -ne '50bbd415d2da34c3786681ad1ad390d9add581ca17137b2d4f35ecb05fe7a51f') { throw 'INTCALC contract hash mismatch' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath "$Packet\POSTTRAN\contract.json").Hash.ToLowerInvariant() -ne '92c9dab92dfa6db53c1cf72a4784775377a886d81026b67850cbd19f14e806c1') { throw 'POSTTRAN contract hash mismatch' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract "$Packet\INTCALC\contract.json"
if ($LASTEXITCODE -ne 0) { throw 'INTCALC import refused; stop' }
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract "$Packet\POSTTRAN\contract.json"
if ($LASTEXITCODE -ne 0) { throw 'POSTTRAN import refused; stop' }
```

In Factory Work queue on 8769, compare both full contract hashes and the 81/96
member counts. Then Howard records each member's outcome and reason and signs
through the existing authenticated UI. No command above signs anything or reads
a private key. Export the signed decisions for separate verification and a new
prospective resolution overlay. Unresolved and unobservable mutants stay in the
denominator; no historical record is rewritten and no release is authorized.
