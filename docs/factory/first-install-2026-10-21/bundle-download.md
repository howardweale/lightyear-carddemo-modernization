# Download and stage the exact approved CI bundle

These steps only download, verify and extract. They do not install or start Tower.
Use the final PR comment's full commit, manifest SHA-256, ZIP SHA-256, workflow run
ID and artifact ID together. The artifact name must be
`factory-first-install-<full-commit>`. Approval does not transfer to another head,
run or artifact. Do not use a moving branch name, the latest artifact, or a digest
read from the downloaded manifest as the expected digest. Expired artifacts require
a new reviewed artifact; do not silently rebuild or substitute one.

In your own PowerShell terminal, use an existing authenticated GitHub CLI and the
existing metadata Python below. This procedure neither installs dependencies nor
starts a login. Set `$Repo` to a separate clean checkout of the approved commit;
the two dirty working trees are unsuitable. Fill the five placeholders from the
single final review comment after approving them. The helper uses only Python's
standard library and `gh api`; it never executes bundle contents.

```powershell
$ErrorActionPreference = 'Stop'
$Commit = '<approved-full-commit>'
$ManifestSHA256 = '<approved-manifest-sha256>'
$ZipSHA256 = '<approved-zip-sha256>'
$RunID = '<approved-workflow-run-id>'
$ArtifactID = '<approved-artifact-id>'
$ArtifactName = "factory-first-install-$Commit"
$Repo = '<separate-clean-checkout-at-approved-commit>'
$MetadataPython = 'C:\Users\howar\OneDrive\Documents\ChatGPT\lightyear-carddemo-modernization\work\idempiere-runtime-evidence\work\native-venv\Scripts\python.exe'
if ($Commit -cnotmatch '^[0-9a-f]{40}$' -or $ManifestSHA256 -cnotmatch '^[0-9a-f]{64}$' -or $ZipSHA256 -cnotmatch '^[0-9a-f]{64}$') { throw 'Fill exact approved identifiers' }
$CheckedHead = git -C $Repo rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $CheckedHead.Trim() -cne $Commit) { throw 'Wrong checkout' }
$CheckoutStatus = git -C $Repo status --porcelain
if ($LASTEXITCODE -ne 0 -or $CheckoutStatus) { throw 'Checkout is not clean' }
$StageParent = Join-Path $env:LOCALAPPDATA 'LightyearBundleStaging'
New-Item -ItemType Directory -Path $StageParent -Force | Out-Null
$Stage = Join-Path $StageParent ($Commit + '-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $Stage) { throw 'Staging destination must be new' }
& $MetadataPython -I -B (Join-Path $Repo 'tools\factory_install\stage_bundle.py') --commit $Commit --run-id $RunID --artifact-id $ArtifactID --manifest-sha256 $ManifestSHA256 --zip-sha256 $ZipSHA256 --stage $Stage
if ($LASTEXITCODE -ne 0) { throw 'Download or verification refused; preserve partial staging if present' }
if ((Get-FileHash -LiteralPath (Join-Path $Stage 'manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ManifestSHA256) { throw 'Staged manifest changed' }
```

Before creating `$Stage`, the helper checks the successful workflow's exact source,
repository and artifact identity, the downloaded ZIP digest, the manifest digest,
and every listed file's size and digest. It rejects missing/extra files, duplicate
or unsafe paths, links, encrypted entries and file/directory collisions. It writes
only to the new staging folder. On any failure, preserve the folder for inspection;
do not overlay it or run its contents. The public result names the verified commit,
artifact, digests, file count and staging path.

Stop here. Staging is not installation approval. Use the reviewed installer only
after Howard's exact approval and retain its disabled-task receipt. The subsequent
[operator commands](operator-commands.md) are a separate, private Howard procedure.
