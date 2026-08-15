param(
  [ValidateSet("serve", "validate", "events", "verify")][string]$Command = "serve",
  [Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest
)
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectDir "src"
Set-Location $ProjectDir

$versions = @("3.13", "3.12", "3.11", "3.14")
$selected = $null
foreach ($version in $versions) {
  $probeExitCode = 1
  try {
    & py "-$version" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    $probeExitCode = $LASTEXITCODE
  } catch {
    $probeExitCode = 1
  }
  if ($probeExitCode -eq 0) { $selected = "-$version"; break }
}
if (-not $selected) { throw "LIGHTYEAR requires Python 3.11 or newer." }

if ($Command -eq "serve") {
  & py $selected -m lightyear_knowledge_graph serve @Rest
} elseif ($Command -eq "verify") {
  & py $selected -m unittest tests.test_live_control_tower -v
  if ($LASTEXITCODE -eq 0) {
    & py $selected -m lightyear_control_tower validate --database (Join-Path $ProjectDir "work/control-tower/events.sqlite3")
  }
} else {
  & py $selected -m lightyear_control_tower $Command @Rest
}
exit $LASTEXITCODE
