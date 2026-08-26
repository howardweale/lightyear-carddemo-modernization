param(
  [ValidateSet("verify", "simulate", "live")][string]$Command = "verify",
  [string]$BaseUrl,
  [string]$KeyId,
  [string]$Output
)
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = "$(Join-Path $ProjectDir 'extensions\runtime')$([IO.Path]::PathSeparator)$(Join-Path $ProjectDir 'src')"
. (Join-Path $ProjectDir "python-runtime.ps1")
$Profile = Join-Path $ProjectDir "extensions\adapters\mainframe-access.profile.json"
$Graph = Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz"
function Run-Python { Invoke-FactoryDarkPython @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }

if ($Command -eq "verify") {
  Run-Python -m lightyear_extensions campaign-validate --profile $Profile --graph $Graph --capture-root (Join-Path $ProjectDir "extensions\adapters\campaign")
} elseif ($Command -eq "simulate") {
  if ([string]::IsNullOrWhiteSpace($Output)) { $Output = Join-Path $ProjectDir "work\mainframe-access-simulated" }
  Run-Python -m lightyear_extensions campaign-fixture --profile $Profile --graph $Graph --responses (Join-Path $ProjectDir "extensions\adapters\fixtures\mainframe-access.simulated.responses.json") --output-root $Output
} else {
  if ([string]::IsNullOrWhiteSpace($BaseUrl) -or [string]::IsNullOrWhiteSpace($KeyId)) { throw "Specify -BaseUrl and -KeyId" }
  if ([string]::IsNullOrWhiteSpace($env:LIGHTYEAR_MAINFRAME_BEARER)) { throw "Set LIGHTYEAR_MAINFRAME_BEARER" }
  if ([string]::IsNullOrWhiteSpace($env:LIGHTYEAR_EXTENSION_EVIDENCE_KEY)) { throw "Set LIGHTYEAR_EXTENSION_EVIDENCE_KEY" }
  if ([string]::IsNullOrWhiteSpace($Output)) { $Output = Join-Path $ProjectDir "work\mainframe-access-live" }
  Run-Python -m lightyear_extensions campaign-live --profile $Profile --graph $Graph --base-url $BaseUrl --key-id $KeyId --output-root $Output
}
