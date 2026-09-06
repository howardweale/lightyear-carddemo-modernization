[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Remaining
)
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Tool = Join-Path $ProjectDir "tools/cloudbank_operational_baseline.py"
Invoke-FactoryDarkPython $Tool @Remaining
exit $LASTEXITCODE
