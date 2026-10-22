# R3 Stage A: reviewed VM export

Howard runs these steps after reviewing the exact PR commit. Codex does not run
the export, start the VM, access its files, or upload evidence. Stage B remains
blocked until Howard posts the Release asset name and SHA-256 on this PR.

The exporter only runs on `ly-tsql-m0`. Use an existing VM Python environment
with `cryptography`; no installation command is included. It performs signature
verification, file reads and ZIP creation only. It never calls a database,
Docker, a model, a signing key, or a cloud API.

## Exact evidence boundary

- Report **content** SHA-256:
  `97116694c110465c639180a79b3ba3512d44566a49b529d8f24ce7713e69e2ef`.
- Recorder **public-key bytes** SHA-256:
  `f65a408bc46828860fd140518486734879fa9c35aacf2366000e0b1477ae3864`.
- The historical audit counted 1,889 entries in signed `report.files`.
  Adding `report.json` gives exactly **1,890 packaged files**, including all
  108 pair directories and coverage-control evidence. The exporter checks both
  counts and reports the separate SHA-256 of the actual report file bytes.

Only the one directory matching that authenticated report is packaged. Every
file must be in its signed manifest; links, hardlinks, extras, unknown binary
files, credential filenames, private-key markers and credential/token fields
cause refusal. Bounded base64/hex strings and embedded JSON are scanned too.
TDS numeric protocol-token discriminators are retained. The tool does not redact
or rewrite signed evidence to make it pass. A refusal requires investigation.

Hostnames, addresses and project IDs are written to `identifiers.json` for review.
The package command requires its exact review hash and refuses any inventory
change since inspection. Inspect that file before approving retention. The ZIP
contains only `revision-9/<signed evidence path>` entries. Inspection and export
manifests are sidecars, never inserted into the original run directory.

## Inspect on the VM

Use the exact reviewed `tools/export_tsql_r9.py` from this PR. The placeholders
below are operator-selected paths, project and zone; do not substitute a local
attempts 001–010 directory. In PowerShell on the PC:

```powershell
$Project = '<reviewed-project-id>'
$Zone = '<reviewed-vm-zone>'
$Vm = 'ly-tsql-m0'
$ReviewedScript = '<absolute-PC-path-to-reviewed-export_tsql_r9.py>'
# Confirm the selected project/zone/VM identity before issuing any command.
gcloud compute instances describe $Vm --project $Project --zone $Zone --format='value(name,status,zone)'
if ($LASTEXITCODE -ne 0) { throw 'VM identity check failed' }
gcloud compute scp --tunnel-through-iap --project $Project --zone $Zone $ReviewedScript "${Vm}:~/export_tsql_r9.py"
if ($LASTEXITCODE -ne 0) { throw 'Reviewed script copy failed' }
```

In an IAP SSH session (`gcloud compute ssh ly-tsql-m0 --tunnel-through-iap
--project <reviewed-project-id> --zone <reviewed-vm-zone>`), choose a narrow parent
directory containing the retained runs and a fresh output directory outside them:

```bash
python3 -B ~/export_tsql_r9.py inspect \
  --search-root '<retained-run-parent>' --out '<fresh-export-directory>'
# Read <fresh-export-directory>/identifiers.json and inspection.json.
# No ZIP exists yet. Review every hostname/project ID before retaining it.
python3 -B ~/export_tsql_r9.py package \
  --search-root '<same-retained-run-parent>' --out '<same-export-directory>' \
  --reviewed-identifiers-sha256 '<reviewed-identifiers-sha256-from-inspection>'
```

If either command fails or inspection is abandoned, stop the VM from the PC
with the stop-and-confirm commands below; do not upload a partial package.
The package phase repeats all checks,
verifies the actual ZIP members and bytes, and writes `export-manifest.json` with
every file's size/SHA-256 and the package SHA-256. Original receipts stay intact.

## IAP transfer, stop VM, then upload

After the export succeeds, use PowerShell on the PC. Copy only the three named
outputs, never a recursive VM folder. Stop the VM even if transfer fails; a failed
copy can be investigated without leaving it running.

```powershell
$VmOut = '<absolute-reviewed-export-directory-on-VM>'
$ExpectedZipSha = '<full-package-sha256-printed-by-the-VM-exporter>'
if ($ExpectedZipSha -notmatch '^[0-9a-f]{64}$') { throw 'Record the VM export digest first' }
$PcOut = Join-Path $env:USERPROFILE ('Downloads/tsql-r9-export-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $PcOut -ErrorAction Stop | Out-Null
try {
  foreach ($Name in @('tsql-r9-evidence-2026-10-21.zip','export-manifest.json','identifiers.json')) {
    gcloud compute scp --tunnel-through-iap --project $Project --zone $Zone "${Vm}:${VmOut}/${Name}" $PcOut
    if ($LASTEXITCODE -ne 0) { throw "IAP copy failed: $Name" }
  }
} finally {
  gcloud compute instances stop $Vm --project $Project --zone $Zone
  if ($LASTEXITCODE -ne 0) { throw 'VM stop failed; stop it before leaving' }
  $StoppedState = gcloud compute instances describe $Vm --project $Project --zone $Zone --format='value(status)'
  if ($LASTEXITCODE -ne 0 -or "$StoppedState".Trim() -ne 'TERMINATED') { throw 'VM is not confirmed stopped' }
}
$Manifest = Get-Content -LiteralPath (Join-Path $PcOut 'export-manifest.json') -Raw | ConvertFrom-Json
$Zip = Join-Path $PcOut 'tsql-r9-evidence-2026-10-21.zip'
$Actual = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Actual -ne $ExpectedZipSha -or $Actual -ne $Manifest.package_sha256) { throw 'Transferred package digest mismatch' }
$ApprovedCommit = '<exact-reviewed-export-PR-commit>'
gh release create tsql-r9-evidence-2026-10-21 $Zip (Join-Path $PcOut 'export-manifest.json') (Join-Path $PcOut 'identifiers.json') `
  --repo howardweale/lightyear-carddemo-modernization --target $ApprovedCommit `
  --title 'R3 revision-9 evidence export — 2026-10-21' `
  --notes 'Operator-reviewed export of unchanged revision-9 receipts. Not a pglast 7.20 re-verification result.'
if ($LASTEXITCODE -ne 0) { throw 'Release creation failed; inspect it before retrying; never replace assets blindly' }
Write-Output "Asset: tsql-r9-evidence-2026-10-21.zip; SHA-256: $Actual"
```

On refusal or abandoned inspection, run this PC block immediately:

```powershell
gcloud compute instances stop $Vm --project $Project --zone $Zone
if ($LASTEXITCODE -ne 0) { throw 'VM stop failed; stop it before leaving' }
$StoppedState = gcloud compute instances describe $Vm --project $Project --zone $Zone --format='value(status)'
if ($LASTEXITCODE -ne 0 -or "$StoppedState".Trim() -ne 'TERMINATED') { throw 'VM is not confirmed stopped' }
```

Post that asset name, full SHA-256 and Release link on this PR. Stage B will bind
the exact Release asset ID, archive digest and all export-manifest file hashes,
then recompute all 108 pairs under pglast 7.20 in read-only CI. It must publish a
new dated result, including any mismatch or refusal. No old receipt is replaced,
no original result is inherited, and no model/database calls are needed.
