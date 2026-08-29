$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$Action = if ($args.Count -gt 0) { $args[0] } else { "doctor" }
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
function Run-Python { Invoke-FactoryDarkPython @args }

if ($Action -eq "doctor") {
    Run-Python -m lightyear_knowledge_graph doctor --project-root $ProjectDir
    exit $LASTEXITCODE
}
if ($Action -eq "demo") {
    Run-Python -m lightyear_knowledge_graph doctor --project-root $ProjectDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph demo --project-root $ProjectDir
    exit $LASTEXITCODE
}
if ($Action -eq "explorer") {
    & (Join-Path $ProjectDir "graph-explorer.ps1") @($args | Select-Object -Skip 1)
    exit $LASTEXITCODE
}
if ($Action -eq "pilot") {
    & (Join-Path $ProjectDir "source-only-pilot.ps1") @($args | Select-Object -Skip 1)
    exit $LASTEXITCODE
}
if ($Action -eq "verify") {
    & (Join-Path $ProjectDir "knowledge-graph.ps1") verify
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $ProjectDir "extension-foundation.ps1") verify
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $ProjectDir "pli-conformance.ps1") verify
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $ProjectDir "pli-modernization.ps1") verify
    & (Join-Path $ProjectDir "pli-build-attestation.ps1") verify
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $ProjectDir "composite-estate.ps1") verify
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $ProjectDir "source-only-pilot.ps1") verify
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m unittest tests.test_semantic_inputs tests.test_composite_estate
    exit $LASTEXITCODE
}
Write-Error "Usage: .\lightyear.ps1 [doctor|demo|explorer|pilot|verify]"
exit 2
