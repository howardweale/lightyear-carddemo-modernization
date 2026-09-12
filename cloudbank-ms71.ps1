param(
    [Parameter(Position = 0)] [string]$Action = "--help",
    [Parameter(ValueFromRemainingArguments = $true)] [string[]]$Remaining
)
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools/cloudbank_ms71.py") $Action @Remaining
exit $LASTEXITCODE
