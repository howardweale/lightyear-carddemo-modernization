param(
  [ValidateSet("build", "verify", "live", "resume", "validate-live")]
  [string]$Command = "verify",
  [string]$BaseUrl,
  [string]$KeyId,
  [string]$Output,
  [ValidateSet("bearer-env", "externally-issued-oauth-bearer-env", "mtls-bearer-env")]
  [string]$AuthMode = "bearer-env"
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = "$(Join-Path $ProjectDir 'extensions\runtime')$([IO.Path]::PathSeparator)$(Join-Path $ProjectDir 'src')"
. (Join-Path $ProjectDir "python-runtime.ps1")
$ApplianceProfile = Join-Path $ProjectDir "extensions\adapters\enterprise-appliance.profile.json"
$CampaignProfile = Join-Path $ProjectDir "extensions\adapters\mainframe-access.profile.json"
$Responses = Join-Path $ProjectDir "extensions\adapters\fixtures\enterprise-appliance.simulated.responses.json"
$Faults = Join-Path $ProjectDir "extensions\adapters\fixtures\enterprise-appliance.faults.json"
$Graph = Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz"
$Canonical = Join-Path $ProjectDir "extensions\adapters\appliance"

function Run-Python {
  Invoke-FactoryDarkPython @args
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Build-Appliance([string]$Output) {
  Run-Python -m lightyear_extensions appliance-fixture `
    --appliance-profile $ApplianceProfile `
    --campaign-profile $CampaignProfile `
    --responses $Responses `
    --faults $Faults `
    --graph $Graph `
    --output-root $Output
}

if ($Command -eq "build") {
  New-Item -ItemType Directory -Force -Path $Canonical | Out-Null
  Build-Appliance $Canonical
  exit 0
}

if ($Command -in @("live", "resume")) {
  if (-not $BaseUrl -or -not $KeyId) {
    throw "Live and resume require -BaseUrl and -KeyId"
  }
  if (-not $env:LIGHTYEAR_MAINFRAME_BEARER) { throw "Set LIGHTYEAR_MAINFRAME_BEARER" }
  if (-not $env:LIGHTYEAR_EXTENSION_EVIDENCE_KEY) {
    throw "Set LIGHTYEAR_EXTENSION_EVIDENCE_KEY"
  }
  if (-not $Output) { $Output = Join-Path $ProjectDir "work\enterprise-appliance-live" }
  $LiveArgs = @(
    "-m", "lightyear_extensions", "appliance-live",
    "--appliance-profile", $ApplianceProfile,
    "--campaign-profile", $CampaignProfile,
    "--faults", $Faults,
    "--graph", $Graph,
    "--base-url", $BaseUrl,
    "--key-id", $KeyId,
    "--auth-mode", $AuthMode,
    "--output-root", $Output
  )
  if ($Command -eq "resume") { $LiveArgs += "--resume" }
  if ($env:LIGHTYEAR_MAINFRAME_CA_FILE) {
    $LiveArgs += @("--ca-file", $env:LIGHTYEAR_MAINFRAME_CA_FILE)
  }
  if ($env:LIGHTYEAR_MAINFRAME_CLIENT_CERTIFICATE) {
    $LiveArgs += @("--client-certificate", $env:LIGHTYEAR_MAINFRAME_CLIENT_CERTIFICATE)
  }
  if ($env:LIGHTYEAR_MAINFRAME_CLIENT_KEY) {
    $LiveArgs += @("--client-key", $env:LIGHTYEAR_MAINFRAME_CLIENT_KEY)
  }
  Run-Python @LiveArgs
  exit 0
}

if ($Command -eq "validate-live") {
  if (-not $KeyId -or -not $Output) { throw "validate-live requires -KeyId and -Output" }
  if (-not $env:LIGHTYEAR_EXTENSION_EVIDENCE_KEY) {
    throw "Set LIGHTYEAR_EXTENSION_EVIDENCE_KEY"
  }
  Run-Python -m lightyear_extensions appliance-validate `
    --appliance-profile $ApplianceProfile `
    --campaign-profile $CampaignProfile `
    --graph $Graph `
    --artifact-root $Output `
    --trusted-key-id $KeyId
  exit 0
}

$Generated = Join-Path $ProjectDir "work\enterprise-appliance-verify"
if (Test-Path $Generated) { Remove-Item -Recurse -Force $Generated }
New-Item -ItemType Directory -Force -Path $Generated | Out-Null
Build-Appliance $Generated
Run-Python -m lightyear_extensions appliance-validate `
  --appliance-profile $ApplianceProfile `
  --campaign-profile $CampaignProfile `
  --graph $Graph `
  --artifact-root $Generated
foreach ($Name in @(
  "appliance.receipt.json", "checkpoint.json", "fault-lab.receipt.json",
  "lightyear.cics-cmci.capture.json", "lightyear.db2-zos-catalog.capture.json",
  "lightyear.zosmf-jobs.capture.json"
)) {
  $Expected = Join-Path $Canonical $Name
  $Actual = Join-Path $Generated $Name
  if (-not (Test-Path $Actual) -or (Get-FileHash $Expected).Hash -ne (Get-FileHash $Actual).Hash) {
    throw "Generated enterprise appliance artifact differs: $Name"
  }
}
Run-Python -m unittest extensions.tests.test_enterprise_collection_appliance -v
Write-Host "Enterprise collection, recovery, retention, and fault evidence is deterministic."
