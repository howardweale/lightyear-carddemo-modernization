# MS87 native journey replay evidence

Two consecutive replays passed the declared deterministic gates on local Oracle 26ai Free and PostgreSQL 15.19. Each replay reproduced the known timestamp and locking findings, confirmed bounded operations equivalence, recorded zero interventions outside designed stops and cleaned up completely. The timestamp decision remains open.

| Entry point | Run | UTC start | UTC finish |
|---|---|---|---|
| Windows | `journey-5c1edbbd4e954c2bbc2feea90e462d5a` | 2026-09-26 21:47:40 | 2026-09-26 22:06:54 |
| Linux / WSL Ubuntu | `journey-cab8521ea79446b5bf6232392e4ae04a` | 2026-09-26 22:08:05 | 2026-09-26 22:26:58 |

Both entry points used the same Docker Desktop host. This is cross-platform entry-point validation, not independent replication on different infrastructure. Together they recorded twelve native executions, twelve passing gates and one hundred signed journal events. Replay used zero model calls.

## Files and independent review

- [Evidence archive](evidence.zip): raw observations, catalogs, row differences, execution logs, inputs, signed journals, authorizations and receipts.
- [Publication receipt](receipt.json): archive hash, authority hash and bound run identities.
- [Public verification key](authority.public.pem): local operator authority; no private key is included.
- [MS87 milestone](../../milestones/MS-87/MS-87.md): results and limits.
- [Operational guide](../../../factory/idempiere/ms86-journeys/README.md): prerequisites, run lifecycle, decisions and recovery.

The compact archive contains content-addressed blobs. Duplicate gzip files may differ only in their four timestamp-header bytes; the manifest retains those bytes separately. Repeated native JSON table and catalog sections are stored once and restored in their original order. Verification requires the reconstructed length and SHA-256 of every original file to match before checking any signature or gate. No observation or raw difference is normalized by this storage encoding.

From the repository root with the control-tower dependencies installed:

```powershell
$env:PYTHONPATH = 'src'
python tools/publish_native_journeys.py verify --output docs/calibration/idempiere-native-journeys
```

This is an offline evidence check. It does not require Docker, database credentials or external network access. It extracts temporary files, verifies their exact original bytes, validates the authorization and journal chains, checks the installed implementation against the recorded hashes and recomputes all six gates for each run. Only Python checkout line-ending differences are accepted in implementation hash checks. Temporary disk use exceeds the compressed archive size.

The separately reviewed receipt and public key are the trust anchor. Local signatures provide integrity and attribution; `independently_attested` remains false. Replacing both files with another authority is not proof of the original operator's identity.

## What passed, and what remains open

The two deterministic business projections are identical. Both receipts report `known_findings_reproduced: true`, `bounded_operations_equivalence: true`, `unattended_run: true` and `error: null`. Their state is `halted-for-decision`, because the shipment timestamp question has not been answered. No acceptance of timestamp loss was invented.

Oracle still loses fractional shipment time and still raises the archived `firstOnly()` locking diagnostic. Boundary equivalence therefore stays false. Full application equivalence, schema equivalence and platform qualification also stay false.

The declaration hash is `0e6d2d6cb5703866867989deff5a2c870b2a535da21df6213fa50fafd517ebda`. The plan hash is `299d3e03573cfaa15fffb18ee7d5010141c1e8731f7fbd4f2aaed15a79a01e0f`.

Development failures remain failed in local history and are not counted as acceptance replays. Fault-injection tests used real isolated Docker workers for cancellation, timeout and killed-container cleanup; those are lifecycle fixtures, not additional business evidence. No GCP resources were started.
