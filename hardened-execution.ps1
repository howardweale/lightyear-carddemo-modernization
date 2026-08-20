$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $projectDir "src"
. (Join-Path $projectDir "python-runtime.ps1")
Set-Location $projectDir

$action = if ($args.Count -gt 0) { $args[0] } else { "build" }
if ($action -eq "build") {
    Invoke-FactoryDarkPython -m lightyear_execution build
    exit $LASTEXITCODE
} elseif ($action -eq "verify") {
    $generated = Join-Path $projectDir "work/hardened-execution-verify/conformance.receipt.json"
    New-Item -ItemType Directory -Force (Split-Path -Parent $generated) | Out-Null
    Invoke-FactoryDarkPython -m lightyear_execution build --output $generated
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Invoke-FactoryDarkPython -m lightyear_execution validate --receipt $generated
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Invoke-FactoryDarkPython -m lightyear_execution validate-evidence --receipt $generated | Out-Null
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Invoke-FactoryDarkPython -m lightyear_execution validate
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $canonical = (Get-FileHash (Join-Path $projectDir "factory/execution/conformance.receipt.json") -Algorithm SHA256).Hash
    $actual = (Get-FileHash $generated -Algorithm SHA256).Hash
    if ($canonical -ne $actual) { Write-Error "Generated conformance receipt differs from canonical" }
    Write-Host "Hardened execution policy, OCI invocation, and conformance receipt are deterministic."
} elseif ($action -eq "probe") {
    $runtime = if ($args.Count -gt 1) { $args[1] } else { "docker" }
    Invoke-FactoryDarkPython -m lightyear_execution probe --runtime $runtime
    exit $LASTEXITCODE
} elseif ($action -eq "admitted-run") {
    $runtime = if ($args.Count -gt 1) { $args[1] } else { "docker" }
    $runId = if ($args.Count -gt 2) { $args[2] } else { "hardened-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") }
    if ([string]::IsNullOrWhiteSpace($env:LIGHTYEAR_WORK_ORDER_SIGNING_KEY)) {
        Write-Error "Set LIGHTYEAR_WORK_ORDER_SIGNING_KEY to at least 32 bytes"
    }
    if ([string]::IsNullOrWhiteSpace($env:LIGHTYEAR_IDENTITY_SIGNING_KEY)) {
        Write-Error "Set LIGHTYEAR_IDENTITY_SIGNING_KEY to at least 32 bytes"
    }
    $evidenceDir = Join-Path $projectDir "work/hardened-execution-runs/$runId"
    $signedOrder = Join-Path $evidenceDir "signed-work-order.json"
    $factoryReceipt = Join-Path $projectDir "work/factory-runs/$runId/receipt.json"
    New-Item -ItemType Directory -Force $evidenceDir | Out-Null
    Invoke-FactoryDarkPython -m lightyear_execution sign-work-order `
        --work-order (Join-Path $projectDir "factory/work-orders/intcalc-repair.example.json") `
        --issuer "operator:release" --key-id "lightyear-release-operator" --output $signedOrder
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Invoke-FactoryDarkPython -m lightyear_factory run `
        --signed-work-order $signedOrder --source-root $projectDir `
        --runs-root (Join-Path $projectDir "work/factory-runs") `
        --graph (Join-Path $projectDir "knowledge/graph.snapshot.json.gz") `
        --provider local --execution-runtime $runtime --run-id $runId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Invoke-FactoryDarkPython -m lightyear_execution validate-evidence --receipt $factoryReceipt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Invoke-FactoryDarkPython -m lightyear_audit build `
        --execution-receipt $factoryReceipt `
        --output (Join-Path $evidenceDir "audit.snapshot.json.gz") `
        --dossier-json (Join-Path $evidenceDir "release-dossier.json") `
        --dossier-markdown (Join-Path $evidenceDir "release-dossier.md")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "SIGNED_WORK_ORDER=$signedOrder"
    Write-Host "FACTORY_EXECUTION_RECEIPT=$factoryReceipt"
    Write-Host "LIVE_AUDIT_SNAPSHOT=$(Join-Path $evidenceDir 'audit.snapshot.json.gz')"
    Write-Host "LIVE_RELEASE_DOSSIER=$(Join-Path $evidenceDir 'release-dossier.json')"
} else {
    Write-Error "Usage: .\hardened-execution.ps1 [build|verify|probe [docker|podman]|admitted-run [docker|podman] [run-id]]"
}
