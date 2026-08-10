$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
& py -3.11 -m carddemo_oracle @args
exit $LASTEXITCODE

