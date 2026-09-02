$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }
$Remaining = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }
$Tool = Join-Path $ProjectDir "tools\cloudbank_executable_baseline.py"

if ($Action -eq "build" -or $Action -eq "verify") {
    Invoke-FactoryDarkPython $Tool $Action --project-root $ProjectDir
} elseif ($Action -eq "verify-source" -and $Remaining.Count -eq 1) {
    Invoke-FactoryDarkPython $Tool verify-source --source-root $Remaining[0]
} elseif ($Action -eq "source-build" -and $Remaining.Count -eq 3) {
    Invoke-FactoryDarkPython $Tool source-build --source-root $Remaining[0] --output $Remaining[1] --signer $Remaining[2]
} elseif ($Action -eq "oracle-runtime" -and $Remaining.Count -eq 5) {
    Invoke-FactoryDarkPython $Tool oracle-runtime --source-root $Remaining[0] --build-receipt $Remaining[1] `
        --oracle-image-id-sha256 $Remaining[2] --output $Remaining[3] --signer $Remaining[4]
} elseif ($Action -eq "verify-receipt" -and $Remaining.Count -eq 1) {
    Invoke-FactoryDarkPython $Tool verify-receipt --receipt $Remaining[0]
} else {
    Write-Error "Usage: .\cloudbank-executable-baseline.ps1 [build|verify|verify-source SOURCE_ROOT|source-build SOURCE_ROOT OUTPUT SIGNER|oracle-runtime SOURCE_ROOT BUILD_RECEIPT IMAGE_ID_SHA256 OUTPUT SIGNER|verify-receipt RECEIPT]"
    exit 2
}
exit $LASTEXITCODE
