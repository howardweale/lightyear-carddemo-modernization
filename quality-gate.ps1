param(
    [ValidateSet("sign", "validate", "evaluate", "compare")]
    [string]$Action,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $ProjectDir "src"

if ($Action -eq "sign") {
    if ($Arguments.Count -lt 2) { throw "sign requires catalog and envelope paths" }
    $Issuer = if ($Arguments.Count -gt 2) { $Arguments[2] } else { "external-evaluation-controller" }
    & py -3.11 -m lightyear_factory sign-eval-catalog --catalog $Arguments[0] `
        --output $Arguments[1] --issuer $Issuer
} elseif ($Action -eq "validate") {
    if ($Arguments.Count -lt 1) { throw "validate requires an envelope path" }
    & py -3.11 -m lightyear_factory validate-sealed-eval --envelope $Arguments[0]
} elseif ($Action -eq "evaluate") {
    if ($Arguments.Count -lt 1) { throw "evaluate requires an envelope path" }
    $Output = if ($Arguments.Count -gt 1) { $Arguments[1] } else {
        Join-Path $ProjectDir ("work/sealed-evaluation-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))
    }
    & py -3.11 -m lightyear_factory evaluate --project-root $ProjectDir `
        --sealed-envelope $Arguments[0] --output-root $Output --provider openai
    Write-Output "SEALED_EVALUATION=$Output"
} else {
    if ($Arguments.Count -lt 2) { throw "compare requires at least two receipt paths" }
    $ReceiptArgs = @()
    foreach ($Receipt in $Arguments) { $ReceiptArgs += @("--receipt", $Receipt) }
    & py -3.11 -m lightyear_factory compare-evals @ReceiptArgs
}
exit $LASTEXITCODE
