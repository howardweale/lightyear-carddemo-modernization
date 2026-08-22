$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")

Invoke-FactoryDarkPython -m unittest `
    tests.test_comparator_escape `
    tests.test_trust_boundaries `
    -v
exit $LASTEXITCODE
