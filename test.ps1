$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
. (Join-Path $PSScriptRoot "python-runtime.ps1")
$Mode = if ($args.Count -gt 0) { $args[0] } else { "complete" }
if ($Mode -eq "unit-only") {
    $env:LIGHTYEAR_ALLOW_MISSING_UPSTREAM = "1"
    Write-Warning "INCOMPLETE: upstream-backed integration tests may be skipped."
}
else {
    Invoke-FactoryDarkPython -m lightyear_common prerequisites --project-root $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Invoke-FactoryDarkPython -m unittest discover -s (Join-Path $PSScriptRoot "tests") -v
exit $LASTEXITCODE
