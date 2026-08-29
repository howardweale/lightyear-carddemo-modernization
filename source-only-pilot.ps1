$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$Action = if ($args.Count -gt 0) { $args[0] } else { "doctor" }
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
function Run-Pilot { Invoke-FactoryDarkPython -m lightyear_pilot --project-root $ProjectDir @args }

if ($Action -in @("doctor", "verify", "compatibility")) {
    Run-Pilot $Action
    exit $LASTEXITCODE
}
if ($Action -eq "rehearse") {
    $Output = if ($args.Count -gt 1) { $args[1] } else { Join-Path $ProjectDir "work\source-only-pilot" }
    Run-Pilot rehearse --output-root $Output
    exit $LASTEXITCODE
}
if ($Action -eq "intake") {
    if ($args.Count -lt 4) { Write-Error "Usage: .\source-only-pilot.ps1 intake SOURCE APPROVAL-ID OUTPUT"; exit 2 }
    New-Item -ItemType Directory -Force -Path $args[3] | Out-Null
    Run-Pilot intake --source-root $args[1] --approval-id $args[2] `
        --source-label "Approved customer source-only intake" `
        --output (Join-Path $args[3] "intake.manifest.json")
    exit $LASTEXITCODE
}
if ($Action -eq "preflight") {
    if ($args.Count -lt 2) { Write-Error "Usage: .\source-only-pilot.ps1 preflight OUTPUT"; exit 2 }
    Run-Pilot preflight --intake (Join-Path $args[1] "intake.manifest.json") `
        --output (Join-Path $args[1] "mainframe.preflight.json")
    exit $LASTEXITCODE
}
if ($Action -eq "dossier") {
    if ($args.Count -lt 2) { Write-Error "Usage: .\source-only-pilot.ps1 dossier OUTPUT"; exit 2 }
    Run-Pilot dossier --intake (Join-Path $args[1] "intake.manifest.json") `
        --preflight (Join-Path $args[1] "mainframe.preflight.json") `
        --output-json (Join-Path $args[1] "pilot.dossier.json") `
        --output-md (Join-Path $args[1] "pilot.dossier.md")
    exit $LASTEXITCODE
}
Write-Error "Usage: .\source-only-pilot.ps1 [doctor|verify|compatibility|rehearse|intake|preflight|dossier]"
exit 2
