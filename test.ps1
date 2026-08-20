$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
. (Join-Path $PSScriptRoot "python-runtime.ps1")
Invoke-FactoryDarkPython -m unittest discover -s (Join-Path $PSScriptRoot "tests") -v
exit $LASTEXITCODE
