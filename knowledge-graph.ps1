$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$LegacyCommit = "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }
$LegacyRoot = if ($args.Count -gt 1) { $args[1] } elseif ($env:CARDDEMO_UPSTREAM_ROOT) { $env:CARDDEMO_UPSTREAM_ROOT } else { "" }
$ManagedLegacyRoot = $false

if (-not $LegacyRoot -and (Test-Path (Join-Path $ProjectDir "..\carddemo-upstream\app"))) {
    $LegacyRoot = (Resolve-Path (Join-Path $ProjectDir "..\carddemo-upstream")).Path
}
if (-not $LegacyRoot) {
    $LegacyRoot = Join-Path $ProjectDir "work\carddemo-upstream"
    $ManagedLegacyRoot = $true
    if (-not (Test-Path (Join-Path $LegacyRoot ".git"))) {
        & git -c core.autocrlf=false -c core.eol=lf clone --filter=blob:none --no-checkout `
            https://github.com/aws-samples/aws-mainframe-modernization-carddemo.git `
            $LegacyRoot
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & git -C $LegacyRoot config --local core.autocrlf false
    & git -C $LegacyRoot config --local core.eol lf
    & git -C $LegacyRoot -c core.autocrlf=false -c core.eol=lf checkout --detach --force $LegacyCommit
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
function Run-Python { Invoke-FactoryDarkPython @args }
$Manifest = Join-Path $ProjectDir "knowledge\mappings\carddemo-intcalc.json"
$CicsVsamManifest = Join-Path $ProjectDir "knowledge\mappings\carddemo-cics-vsam-account-view.json"
$AsmManifest = Join-Path $ProjectDir "knowledge\mappings\carddemo-asm-date-format.json"
$ImsManifest = Join-Path $ProjectDir "knowledge\mappings\carddemo-ims-expired-authorization-purge.json"
$DataManifest = Join-Path $ProjectDir "knowledge\mappings\carddemo-db2-authfrds.json"
$Snapshot = Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz"
$Receipt = Join-Path $ProjectDir "knowledge\graph.receipt.json"
$Ontology = Join-Path $ProjectDir "knowledge\ontology\relationships.json"
$EvidencePack = Join-Path $ProjectDir "knowledge\evidence\source.pack.json.gz"
$EvidenceReceipt = Join-Path $ProjectDir "knowledge\evidence\source.receipt.json"
$Capabilities = Join-Path $ProjectDir "knowledge\capabilities\mainframe-readiness.json"
$CicsVsamReceipt = Join-Path $ProjectDir "readiness\cics-vsam\readiness-receipt.json"
$AsmReceipt = Join-Path $ProjectDir "readiness\asm-date\readiness-receipt.json"
$ImsReceipt = Join-Path $ProjectDir "readiness\ims-expiry\readiness-receipt.json"
$PliFragment = Join-Path $ProjectDir "extensions\pli\pli.fragment.json"
$ExtensionCatalog = Join-Path $ProjectDir "extensions\catalog.json"
$PostgresDataReceipt = Join-Path $ProjectDir "data-modernization\receipts\authfrds.offline.receipt.json"
$OracleDataReceipt = Join-Path $ProjectDir "data-modernization\receipts\authfrds.oracle-offline.receipt.json"
$CampaignReceipt = Join-Path $ProjectDir "extensions\adapters\campaign\campaign.receipt.json"

if ($Action -eq "build") {
    Run-Python -m lightyear_knowledge_graph build `
        --legacy-root $LegacyRoot --modern-root $ProjectDir --manifest $Manifest `
        --manifest $CicsVsamManifest --manifest $AsmManifest --manifest $ImsManifest --manifest $DataManifest `
        --ontology $Ontology --evidence-pack $EvidencePack --evidence-receipt $EvidenceReceipt `
        --output $Snapshot --receipt $Receipt --legacy-commit $LegacyCommit `
        --modern-commit repository-content
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph capabilities --graph $Snapshot `
        --cics-vsam-receipt $CicsVsamReceipt --asm-receipt $AsmReceipt `
        --ims-receipt $ImsReceipt --pli-fragment $PliFragment `
        --extension-catalog $ExtensionCatalog --postgres-data-receipt $PostgresDataReceipt `
        --oracle-data-receipt $OracleDataReceipt --campaign-receipt $CampaignReceipt `
        --output $Capabilities
    exit $LASTEXITCODE
}
if ($Action -eq "verify") {
    $Generated = Join-Path $ProjectDir "work\knowledge-graph-verify"
    New-Item -ItemType Directory -Force -Path $Generated | Out-Null
    $GeneratedSnapshot = Join-Path $Generated "graph.snapshot.json.gz"
    $GeneratedReceipt = Join-Path $Generated "graph.receipt.json"
    $GeneratedEvidencePack = Join-Path $Generated "source.pack.json.gz"
    $GeneratedEvidenceReceipt = Join-Path $Generated "source.receipt.json"
    $GeneratedCapabilities = Join-Path $Generated "mainframe-readiness.json"
    Run-Python -m lightyear_knowledge_graph build `
        --legacy-root $LegacyRoot --modern-root $ProjectDir --manifest $Manifest `
        --manifest $CicsVsamManifest --manifest $AsmManifest --manifest $ImsManifest --manifest $DataManifest `
        --ontology $Ontology --evidence-pack $GeneratedEvidencePack `
        --evidence-receipt $GeneratedEvidenceReceipt `
        --output $GeneratedSnapshot --receipt $GeneratedReceipt --legacy-commit $LegacyCommit `
        --modern-commit repository-content
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph capabilities --graph $GeneratedSnapshot `
        --cics-vsam-receipt $CicsVsamReceipt --asm-receipt $AsmReceipt `
        --ims-receipt $ImsReceipt --pli-fragment $PliFragment `
        --extension-catalog $ExtensionCatalog --postgres-data-receipt $PostgresDataReceipt `
        --oracle-data-receipt $OracleDataReceipt --campaign-receipt $CampaignReceipt `
        --output $GeneratedCapabilities
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph validate --graph $GeneratedSnapshot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph validate-evidence `
        --graph $GeneratedSnapshot --evidence-pack $GeneratedEvidencePack
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph gaps --graph $GeneratedSnapshot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph compare-evidence-packs `
        --expected $EvidencePack --actual $GeneratedEvidencePack
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph compare-snapshots `
        --expected $Snapshot --actual $GeneratedSnapshot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ((Get-FileHash $Receipt).Hash -ne (Get-FileHash $GeneratedReceipt).Hash) {
        throw "Knowledge graph receipt is stale; run .\knowledge-graph.ps1 build"
    }
    if ((Get-FileHash $EvidenceReceipt).Hash -ne (Get-FileHash $GeneratedEvidenceReceipt).Hash) {
        throw "Source evidence receipt is stale; run .\knowledge-graph.ps1 build"
    }
    if ((Get-FileHash $Capabilities).Hash -ne (Get-FileHash $GeneratedCapabilities).Hash) {
        throw "Capability analysis is stale; run .\knowledge-graph.ps1 build"
    }
    Write-Host "Knowledge graph snapshot is deterministic, current, and policy-complete."
    exit 0
}
Write-Error "Usage: .\knowledge-graph.ps1 [build|verify] [optional-carddemo-upstream-root]"
exit 2
