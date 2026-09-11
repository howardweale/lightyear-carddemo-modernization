$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }

if ($Action -in @("build", "verify-source", "compare", "verify-comparison-source")) {
    if ($args.Count -lt 2) {
        Write-Error "Pinned iDempiere upstream checkout is required for $Action."
        exit 2
    }
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\idempiere_divergence_audit.py") `
        $Action --project-root $ProjectDir --source-root $args[1]
    exit $LASTEXITCODE
}

if ($Action -in @("verify", "verify-comparison")) {
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\idempiere_divergence_audit.py") `
        $Action --project-root $ProjectDir
    exit $LASTEXITCODE
}

Write-Error "Usage: .\idempiere-divergence-audit.ps1 [build|verify|verify-source|compare|verify-comparison|verify-comparison-source] [IDEMPIERE_ROOT]"
exit 2
