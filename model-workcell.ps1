param(
    [ValidateSet("validate", "evaluate", "resume", "transcript")]
    [string]$Action = "validate",
    [string]$Catalog,
    [string]$Output,
    [string]$RunId,
    [switch]$Verifier
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

if ($Action -eq "transcript") {
    if (-not $Output -or -not $RunId) {
        Write-Error "Transcript requires -Output <runs-root> -RunId <run-id>"
        exit 2
    }
    $Audience = @()
    if ($Verifier) {
        $Audience = @("--verifier")
    }
    & py -3.11 -m lightyear_factory transcript `
        --runs-root $Output `
        --run-id $RunId `
        @Audience
    exit $LASTEXITCODE
}

if (-not $env:OPENAI_API_KEY -or
    -not $env:LIGHTYEAR_MODEL_INPUT_USD_PER_MILLION -or
    -not $env:LIGHTYEAR_MODEL_OUTPUT_USD_PER_MILLION) {
    Write-Error "OPENAI_API_KEY and model input/output prices are required for a governed evaluation"
    exit 2
}
if ($Action -eq "resume" -and -not $Output) {
    Write-Error "Resume requires -Output <evaluation-output>"
    exit 2
}
if (-not $Output) {
    $Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $Output = Join-Path $ProjectDir "work/model-evaluation-$Stamp"
}
$Resume = @()
if ($Action -eq "resume") {
    $Resume = @("--resume")
}
& py -3.11 -m lightyear_factory evaluate `
    --project-root $ProjectDir `
    --catalog $Catalog `
    --output-root $Output `
    --provider openai `
    @Resume
$EvaluationCode = $LASTEXITCODE
Write-Output "MODEL_EVALUATION=$Output"
exit $EvaluationCode
