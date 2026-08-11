$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $projectDir "src"
Set-Location $projectDir

$action = if ($args.Count -gt 0) { $args[0] } else { "simulate" }
if ($action -eq "simulate") {
    $output = if ($args.Count -gt 1) { $args[1] } else {
        Join-Path $projectDir "work/zosmf-simulator/intcalc.runtime.snapshot.json.gz"
    }
    python -m lightyear_runtime simulate-zosmf --output $output
} elseif ($action -eq "verify") {
    $generated = Join-Path $projectDir "work/zosmf-adapter-verify/intcalc.runtime.snapshot.json.gz"
    New-Item -ItemType Directory -Force (Split-Path -Parent $generated) | Out-Null
    python -m lightyear_runtime simulate-zosmf --output $generated
    python -m lightyear_runtime validate --snapshot $generated
    python -m lightyear_runtime compare `
        --expected (Join-Path $projectDir "knowledge/runtime/zosmf/intcalc.runtime.snapshot.json.gz") `
        --actual $generated
    Write-Output "z/OSMF simulator, adapter mapping, and trust boundary are deterministic."
} else {
    Write-Error "Usage: .\zosmf-adapter.ps1 [simulate [output]|verify]"
}
