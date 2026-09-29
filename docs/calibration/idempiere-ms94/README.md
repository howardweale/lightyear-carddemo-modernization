# MS94 equipment qualification evidence

**Equipment-04 Stage A is accepted. Stage B has not run.**

Twenty reference passes, 39 intended business-fault rejections and three intended
duplicate-trace execution failures completed all 62 qualification checks.
All 62 signed publications replayed with the unchanged v4 verifier. Signed source
reviews and scope ownership validated; all campaign resources were removed.
See [the signed terminal audit](equipment-04/terminal-audit.json) and
[acceptance](equipment-04/acceptance.json). The references are test equipment,
not autonomous successes. Earlier stopped results below are preserved.

## Equipment-04 full captures

The 62 lossless archives total 5,865,099,558 bytes and are published as assets in
[the MS94 evidence release](https://github.com/howardweale/lightyear-carddemo-modernization/releases/tag/ms94-stage-a-evidence).
They are outside Git history to avoid adding gigabytes to every clone.
[release-assets.json](equipment-04/release-assets.json) lists exact download URLs,
byte counts and SHA-256 hashes; signed per-pair receipts additionally bind each
archive. The frozen-source asset contains the precise implementation required
by the unchanged verifier. Private signing keys and live journals are excluded.

For example, from a repository checkout in PowerShell with Python dependencies
installed and GitHub CLI authenticated when needed:

```powershell
gh release download ms94-stage-a-evidence --pattern ms94-equipment-04-frozen-source.zip --dir work/ms94-replay
Expand-Archive work/ms94-replay/ms94-equipment-04-frozen-source.zip work/ms94-replay/source
$pair = '01'
$publication = "work/ms94-replay/pair-$pair"
New-Item -ItemType Directory -Force $publication | Out-Null
gh release download ms94-stage-a-evidence --pattern "ms94-equipment-04-pair-$pair.zip" --dir $publication
Copy-Item "docs/calibration/idempiere-ms94/equipment-04/publications/$pair/receipt.json" "$publication/receipt.json"
Copy-Item docs/calibration/idempiere-ms94/equipment-04/authority.public.pem "$publication/authority.public.pem"
Copy-Item "$publication/ms94-equipment-04-pair-$pair.zip" "$publication/evidence.zip"
$publication = (Resolve-Path $publication).Path
$source = (Resolve-Path work/ms94-replay/source).Path
$env:PYTHONPATH="$source/src;$source"
Push-Location $source
python -m tools.ms94_publication_v4 --root $source --publication $publication --trusted-key-sha256 c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f
Pop-Location
```

Before extracting the source archive, compare its SHA-256 with the checked-in
asset index (`Get-FileHash -Algorithm SHA256`). Pair archive integrity, signer,
manifest, decoded file hashes, implementation hashes and complete gate equality
are all checked by the verifier. Repeat with pairs 01 through 62. Replay provisions no databases and makes no model calls. Expected negative
verdicts are successful qualification checks, not false positive passes.

## Preserved equipment-01 result

The first frozen Stage A declaration stopped at its first positive control.
Both native application processes exited successfully. The business comparison
had zero unresolved row differences and zero unresolved trace differences.
Oracle supplied lock-wait evidence but no admissible rollback witness;
PostgreSQL supplied both. The complete gate returned `insufficient-evidence`.

This is a stopped equipment qualification, not a factory failure or an
autonomous success. No Stage B pilot or cohort has run. No model calls were made.

## Complete publication

`equipment-01/evidence.zip` is the full, lossless signed publication: 63,305,904
bytes, 7,647 logical files. It contains native catalogs, before/after state and
row files, execution observations, observer samples, pinned implementation and
inputs, authorization, result and cleanup records. Raw application staging,
live journals and private signing keys are excluded. Trusted/redacted execution
observations remain in the archive. Its complete gate was reconstructed and
replayed successfully with the unchanged verifier.

Archive SHA-256:
`d78088e041f229f3ae80267f333a1e1417ee34067f195a92d6785773388c97bc`

Trusted operator public-key SHA-256:
`c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f`

From this repository, with its Python dependencies installed:

```powershell
$env:PYTHONPATH='src;.'
python -m tools.ms94_publication --publication docs/calibration/idempiere-ms94/equipment-01 --trusted-key-sha256 c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f
```

Replay reads captured observations; it creates neither databases nor model
calls. It requires the frozen source hashes. A future implementation change
must use a new declaration; replay this publication from its matching source
revision. The signature establishes operator provenance, not independent
attestation.

## Why it stopped

The Oracle transition into sample 1230 has rollback counter `0 -> 1`, undo
records applied `0 -> 39`, and commit counter `122 -> 123` in the same observed
interval. Observer v3 deliberately requires no intervening commit to attribute
the required rollback witness. See the signed `equipment-01/diagnosis.json` and
the raw observer samples inside the archive. The evidence does not support
silently relaxing that predicate.

The existing 1.5-second pause occurs before rollback. A proposed new reference
also pauses after rollback and before retry, with the same structural requirement
made public to the builder. This is a proposed new declaration, not a repair to
this stopped run. Test observation windows are not production latency claims.

## Other local validation

The five controller-v2 MCP tools were exercised over stdio without a model:
`public_contract`, `public_api`, `deterministic_support`, `check_structure`,
and `compile`. The known reference compiled in an offline isolated container.
All five calls were recorded. This checks development plumbing, not an
autonomous pilot. The combined deterministic regression suite passed 124 tests.
