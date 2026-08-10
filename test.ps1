$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
& py -3.11 -m unittest discover -s (Join-Path $PSScriptRoot "tests") -v
exit $LASTEXITCODE

