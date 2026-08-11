param(
    [ValidateSet("validate", "evaluate")]
    [string]$Action = "validate",
    [string]$Catalog
)

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $ProjectDir "src"
if (-not $Catalog) {
    $Catalog = Join-Path $ProjectDir "factory/evals/carddemo-v0.12-public.json"
}

if ($Action -eq "validate") {
    & py -3.11 -m lightyear_factory validate-eval --project-root $ProjectDir --catalog $Catalog
    exit $LASTEXITCODE
}

if (-not $env:OPENAI_API_KEY) {
    Write-Error "OPENAI_API_KEY is required for a live model evaluation"
    exit 2
}
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$Output = Join-Path $ProjectDir "work/model-evaluation-$Stamp"
& py -3.11 -m lightyear_factory evaluate `
    --project-root $ProjectDir `
    --catalog $Catalog `
    --output-root $Output `
    --provider openai
if ($LASTEXITCODE -eq 0) {
    Write-Output "MODEL_EVALUATION=$Output"
}
exit $LASTEXITCODE
