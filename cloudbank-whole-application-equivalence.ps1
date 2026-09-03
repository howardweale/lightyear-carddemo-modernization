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
$Tool = Join-Path $ProjectDir "tools/cloudbank_whole_application_equivalence.py"

switch ($Action) {
    { $_ -in @("build", "verify") } {
        Invoke-FactoryDarkPython $Tool $Action --project-root $ProjectDir
    }
    "verify-source" {
        if ($Remaining.Count -ne 1) { throw "verify-source requires SOURCE_ROOT" }
        Invoke-FactoryDarkPython $Tool verify-source --source-root $Remaining[0]
    }
    "materialize" {
        if ($Remaining.Count -ne 2) { throw "materialize requires SOURCE_ROOT OUTPUT" }
        Invoke-FactoryDarkPython $Tool materialize --project-root $ProjectDir --source-root $Remaining[0] --output $Remaining[1]
    }
    "run" {
        if ($Remaining.Count -ne 7) { throw "run requires SOURCE_ROOT MS61_RECEIPT MS64_RECEIPT ORACLE_OBSERVATION POSTGRESQL_OBSERVATION OUTPUT_ROOT SIGNER" }
        Invoke-FactoryDarkPython $Tool run --project-root $ProjectDir --source-root $Remaining[0] --ms61-receipt $Remaining[1] --ms64-receipt $Remaining[2] --oracle-observation $Remaining[3] --postgresql-observation $Remaining[4] --output-root $Remaining[5] --signer $Remaining[6]
    }
    "verify-receipt" {
        if ($Remaining.Count -ne 1) { throw "verify-receipt requires RECEIPT" }
        Invoke-FactoryDarkPython $Tool verify-receipt --project-root $ProjectDir --receipt $Remaining[0]
    }
    default { throw "Unknown action: $Action" }
}

exit $LASTEXITCODE
