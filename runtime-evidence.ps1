$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $projectDir "src"
. (Join-Path $projectDir "python-runtime.ps1")
Set-Location $projectDir

$action = if ($args.Count -gt 0) { $args[0] } else { "build" }
if ($action -eq "build") {
    Invoke-FactoryDarkPython -m lightyear_runtime build
} elseif ($action -eq "verify") {
    $generated = Join-Path $projectDir "work/runtime-evidence-verify/runtime.snapshot.json.gz"
    New-Item -ItemType Directory -Force (Split-Path -Parent $generated) | Out-Null
    Invoke-FactoryDarkPython -m lightyear_runtime build --output $generated
    Invoke-FactoryDarkPython -m lightyear_runtime validate --snapshot $generated
    Invoke-FactoryDarkPython -m lightyear_runtime validate
    Invoke-FactoryDarkPython -m lightyear_runtime compare `
        --expected (Join-Path $projectDir "knowledge/runtime/runtime.snapshot.json.gz") `
        --actual $generated
    & (Join-Path $projectDir "zosmf-adapter.ps1") verify
} else {
    Write-Error "Usage: .\runtime-evidence.ps1 [build|verify]"
}
