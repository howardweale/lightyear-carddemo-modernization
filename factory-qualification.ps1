param(
    [ValidateSet("verify", "qualify", "history")][string]$Action = "verify",
    [string]$Plan,
    [string]$PortfolioRun,
    [string]$Output,
    [string]$LegacyArchive,
    [string[]]$EvaluationReceipt = @()
)

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = "$ProjectDir/src;$ProjectDir/extensions/runtime"
. (Join-Path $ProjectDir "python-runtime.ps1")

if ($Action -eq "verify") {
    foreach ($Catalog in @(
        "intcalc-v0.26-public.json",
        "posttran-v0.26-public.json",
        "creastmt-v0.26-public.json",
        "acctpl1-v0.26-public.json"
    )) {
        Invoke-FactoryDarkPython -m lightyear_factory validate-eval `
            --project-root $ProjectDir `
            --catalog (Join-Path $ProjectDir "factory/evals/$Catalog") | Out-Null
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    Invoke-FactoryDarkPython -m unittest `
        tests.test_multi_workload_qualification `
        tests.test_legacy_model_evidence
    exit $LASTEXITCODE
}

if ($Action -eq "history") {
    if (-not $LegacyArchive -or -not $Output) {
        Write-Error "Historical evidence import requires -LegacyArchive and -Output"
        exit 2
    }
    Invoke-FactoryDarkPython -m lightyear_factory import-legacy-evidence `
        --archive $LegacyArchive `
        --manifest (Join-Path $ProjectDir "factory/qualification/history/v0.12-live-smoke.manifest.json") `
        --output $Output
    exit $LASTEXITCODE
}

if (-not $Plan -or -not $PortfolioRun -or -not $Output -or $EvaluationReceipt.Count -lt 8) {
    Write-Error "Qualification requires a plan, portfolio run, output, and at least eight sealed evaluation receipts"
    exit 2
}
$ReceiptArgs = @()
foreach ($Receipt in $EvaluationReceipt) {
    $ReceiptArgs += @("--evaluation-receipt", $Receipt)
}
Invoke-FactoryDarkPython -m lightyear_factory qualify `
    --manifest (Join-Path $ProjectDir "factory/qualification/manifest.json") `
    --portfolio-plan $Plan `
    --portfolio-run $PortfolioRun `
    --output $Output `
    @ReceiptArgs
exit $LASTEXITCODE
