param(
    [Parameter(Position = 0)]
    [string]$Action = "verify-hardening",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Remaining
)
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Tool = Join-Path $ProjectDir "tools/cloudbank_ms66_dual_lane.py"
Invoke-FactoryDarkPython $Tool $Action @Remaining
exit $LASTEXITCODE
