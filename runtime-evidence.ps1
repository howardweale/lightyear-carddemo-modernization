$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $projectDir "src"
Set-Location $projectDir

$action = if ($args.Count -gt 0) { $args[0] } else { "build" }
if ($action -eq "build") {
    python -m lightyear_runtime build
} elseif ($action -eq "verify") {
    $generated = Join-Path $projectDir "work/runtime-evidence-verify/runtime.snapshot.json.gz"
    New-Item -ItemType Directory -Force (Split-Path -Parent $generated) | Out-Null
    python -m lightyear_runtime build --output $generated
    python -m lightyear_runtime validate --snapshot $generated
    python -m lightyear_runtime validate
    python -m lightyear_runtime compare `
        --expected (Join-Path $projectDir "knowledge/runtime/runtime.snapshot.json.gz") `
        --actual $generated
} else {
    Write-Error "Usage: .\runtime-evidence.ps1 [build|verify]"
}
