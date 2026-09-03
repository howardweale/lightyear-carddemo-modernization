param(
    [Parameter(Position = 0)]
    [string]$Action = "verify",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Remaining
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Tool = Join-Path $ProjectDir "tools/cloudbank_platform_qualification.py"

switch ($Action) {
    { $_ -in @("build", "verify") } {
        Invoke-FactoryDarkPython $Tool $Action --project-root $ProjectDir
    }
    "preflight" {
        if ($Remaining.Count -ne 2) { throw "preflight requires PROFILE OUTPUT_ROOT" }
        Invoke-FactoryDarkPython $Tool preflight --profile $Remaining[0] --output-root $Remaining[1]
    }
    "admit" {
        if ($Remaining.Count -ne 6) { throw "admit requires MS65_RECEIPT MS66_RECEIPT PROFILE OBSERVATION OUTPUT_ROOT SIGNER" }
        Invoke-FactoryDarkPython $Tool admit --project-root $ProjectDir --ms65-receipt $Remaining[0] --ms66-receipt $Remaining[1] --profile $Remaining[2] --observation $Remaining[3] --output-root $Remaining[4] --signer $Remaining[5]
    }
    "verify-receipt" {
        if ($Remaining.Count -ne 1) { throw "verify-receipt requires RECEIPT" }
        Invoke-FactoryDarkPython $Tool verify-receipt --project-root $ProjectDir --receipt $Remaining[0]
    }
    default { throw "Unknown action: $Action" }
}

exit $LASTEXITCODE
