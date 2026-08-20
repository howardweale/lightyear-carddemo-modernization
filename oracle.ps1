$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
. (Join-Path $PSScriptRoot "python-runtime.ps1")
Invoke-FactoryDarkPython -m carddemo_oracle @args
exit $LASTEXITCODE
