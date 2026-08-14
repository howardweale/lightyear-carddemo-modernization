$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $projectDir "src"
Set-Location $projectDir

$action = if ($args.Count -gt 0) { $args[0] } else { "build" }
if ($action -eq "build") {
    & py -3.11 -m lightyear_audit build
    exit $LASTEXITCODE
} elseif ($action -eq "verify") {
    $verificationDir = Join-Path $projectDir "work/audit-control-tower-verify"
    $generated = Join-Path $verificationDir "audit.snapshot.json.gz"
    $generatedJson = Join-Path $verificationDir "carddemo-intcalc-v0.13-demo.json"
    $generatedMarkdown = Join-Path $verificationDir "carddemo-intcalc-v0.13-demo.md"
    New-Item -ItemType Directory -Force $verificationDir | Out-Null
    & py -3.11 -m lightyear_audit build `
        --output $generated `
        --dossier-json $generatedJson `
        --dossier-markdown $generatedMarkdown
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & py -3.11 -m lightyear_audit validate --snapshot $generated
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & py -3.11 -m lightyear_audit validate
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & py -3.11 -m lightyear_audit compare `
        --expected (Join-Path $projectDir "audit/audit.snapshot.json.gz") `
        --actual $generated
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $canonicalJson = (Get-FileHash (Join-Path $projectDir "audit/dossiers/carddemo-intcalc-v0.13-demo.json") -Algorithm SHA256).Hash
    $actualJson = (Get-FileHash $generatedJson -Algorithm SHA256).Hash
    $canonicalMarkdown = (Get-FileHash (Join-Path $projectDir "audit/dossiers/carddemo-intcalc-v0.13-demo.md") -Algorithm SHA256).Hash
    $actualMarkdown = (Get-FileHash $generatedMarkdown -Algorithm SHA256).Hash
    if ($canonicalJson -ne $actualJson -or $canonicalMarkdown -ne $actualMarkdown) {
        Write-Error "Generated audit dossier differs from the canonical dossier"
    }
    Write-Host "Audit ledger, checkpoint, projections, policy decisions, and dossier are deterministic and valid."
} else {
    Write-Error "Usage: .\audit-control-tower.ps1 [build|verify]"
}
