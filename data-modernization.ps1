param(
  [ValidateSet("build", "verify", "semantic-core", "oracle-postgresql-proof", "stored-logic", "db2-semantic", "oracle-source", "live", "live-postgres", "live-oracle", "live-all", "sign")][string]$Command = "verify",
  [string]$LegacyRoot = $env:CARDDEMO_UPSTREAM_ROOT
)
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
if ([string]::IsNullOrWhiteSpace($LegacyRoot)) { $LegacyRoot = Join-Path (Split-Path $ProjectDir -Parent) "carddemo-upstream" }
function Run-Python { Invoke-FactoryDarkPython @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }

if ($Command -eq "build") {
  Run-Python -m lightyear_data build --legacy-root $LegacyRoot --output-root $ProjectDir
} elseif ($Command -eq "verify") {
  $Output = Join-Path $ProjectDir "work\data-modernization-verify"
  if (Test-Path $Output) { Remove-Item -Recurse -Force $Output }
  Run-Python -m lightyear_data build --legacy-root $LegacyRoot --output-root $Output
  Run-Python -m lightyear_data validate --project-root $Output
  Run-Python -m lightyear_data verify-offline --project-root $Output
  $ExpectedFiles = @(
    "canonical/authfrds.model.json"
    "source/authfrds.dcl-contract.json"
    "source/authfrds.embedded-sql.json"
    "mappings/authfrds-postgresql.json"
    "mappings/authfrds-oracle.json"
    "fixtures/authfrds.fixtures.json"
    "postgres/authfrds.sql"
    "oracle/authfrds.sql"
    "receipts/authfrds.offline.receipt.json"
    "receipts/authfrds.oracle-offline.receipt.json"
    "receipts/authfrds.target-plan.json"
    "semantic-core/database-semantic-core.json"
    "semantic-core/authfrds.canonical-schema.json"
    "semantic-core/authfrds.profile-contract.json"
    "semantic-core/authfrds.schema-transformation-plan.json"
    "semantic-core/authfrds.compatibility-ledger.json"
    "semantic-core/authfrds.adapter-conformance.receipt.json"
  )
  foreach ($Relative in $ExpectedFiles) {
    $Expected = Join-Path (Join-Path $ProjectDir "data-modernization") $Relative
    $Actual = Join-Path (Join-Path $Output "data-modernization") $Relative
    if (-not (Test-Path $Actual) -or (Get-FileHash $Expected).Hash -ne (Get-FileHash $Actual).Hash) {
      throw "Generated data artifact differs: $Relative"
    }
  }
  Run-Python -m lightyear_data verify-semantic-core --project-root $Output
  Run-Python -m lightyear_data verify-oracle-postgresql-proof --project-root $ProjectDir
  Run-Python -m lightyear_data verify-stored-logic-qualification --project-root $ProjectDir
  Run-Python -m lightyear_data verify-db2-semantic-adapter --project-root $ProjectDir
  Run-Python -m lightyear_data verify-oracle-source-qualification --project-root $ProjectDir
  Write-Host "AUTHFRDS database semantic core, adapters, ledger, fixtures, and receipts are deterministic."
} elseif ($Command -eq "semantic-core") {
  Run-Python -m lightyear_data verify-semantic-core --project-root $ProjectDir
} elseif ($Command -eq "oracle-postgresql-proof") {
  Run-Python -m lightyear_data verify-oracle-postgresql-proof --project-root $ProjectDir
} elseif ($Command -eq "stored-logic") {
  Run-Python -m lightyear_data verify-stored-logic-qualification --project-root $ProjectDir
} elseif ($Command -eq "db2-semantic") {
  Run-Python -m lightyear_data verify-db2-semantic-adapter --project-root $ProjectDir
} elseif ($Command -eq "oracle-source") {
  Run-Python -m lightyear_data verify-oracle-source-qualification --project-root $ProjectDir
} elseif ($Command -in @("live", "live-postgres")) {
  Run-Python -m lightyear_data verify-docker --target postgresql --project-root $ProjectDir
} elseif ($Command -eq "live-oracle") {
  Run-Python -m lightyear_data verify-docker --target oracle --project-root $ProjectDir
} elseif ($Command -eq "live-all") {
  Run-Python -m lightyear_data verify-docker --target all --project-root $ProjectDir
} else {
  if ([string]::IsNullOrWhiteSpace($env:FACTORYDARK_DATA_EQUIVALENCE_KEY)) { throw "Set FACTORYDARK_DATA_EQUIVALENCE_KEY" }
  $Receipt = Join-Path $ProjectDir "work\data-modernization\live-multi-target.receipt.json"
  $Output = Join-Path $ProjectDir "work\data-modernization\live-multi-target.signed.receipt.json"
  if (-not (Test-Path $Receipt)) {
    $Receipt = Join-Path $ProjectDir "work\data-modernization\live-postgresql.receipt.json"
    $Output = Join-Path $ProjectDir "work\data-modernization\live-postgresql.signed.receipt.json"
  }
  Run-Python -m lightyear_data sign --receipt $Receipt --output $Output
}
